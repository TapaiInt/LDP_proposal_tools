#!/usr/bin/env python3
"""Platform tool layer: JSON-in / JSON-out wrappers over the v4 scripts, on a per-run artifact store.

Why artifacts: the estimator's JSON can be 50-100 KB. Passing it through an LLM as tool arguments is slow,
costly and a corruption risk. Tools therefore work on NAMED ARTIFACTS stored under ARTIFACT_ROOT/<run_id>/,
and return only compact summaries. Save a sub-agent's raw reply once (save_artifact), then refer to it by name.

Entry points
    from tool_api import call;  call("calc_estimate", {"run_id": "r1", "estimate": "estimation_pass2.json"})
    echo '{"tool": "calc_estimate", "args": {...}}' | python tool_api.py          (stdin -> stdout JSON)
    python tool_api.py --manifest > manifest.json                                  (tool definitions for the platform)
Environment: ARTIFACT_ROOT (default ./artifacts).
Every call returns a dict with "ok": true/false; errors never raise to the caller.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(HERE, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)
import estimate_calc as ec  # noqa: E402
from ensemble_select import BLOCKING  # noqa: E402

IMMUTABLE_PREFIXES = ("estimation_pass", "estimation_revision", "reviewer_findings", "scope_summary")
ADVISORY = {"Z1", "Z2", "O2", "O3", "D1", "T5", "M2", "M1"}
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\- ]{0,120}")
RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,120}")      # fullmatch is always used; room for a tenant prefix


class ToolError(Exception):
    pass


# ------------------------------------------------------------------ store helpers
def _root():
    return os.path.abspath(os.environ.get("ARTIFACT_ROOT", "./artifacts"))


def _run_dir(run_id, create=True):
    if not isinstance(run_id, str) or not RUN_RE.fullmatch(run_id) or ".." in run_id:
        raise ToolError(f"invalid run_id {run_id!r} (letters, digits, _ . - only)")
    d = os.path.join(_root(), run_id)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def _path(run_id, name, must_exist=False):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or ".." in name or name.endswith(".tmp"):
        raise ToolError(f"invalid artifact name {name!r}")
    p = os.path.join(_run_dir(run_id), name)
    if must_exist and not os.path.exists(p):
        raise ToolError(f"artifact not found: {name}. Available: {_visible(run_id)}")
    return p


def _visible(run_id):
    return sorted(f for f in os.listdir(_run_dir(run_id)) if not f.startswith("_") and not f.endswith(".tmp"))


# The registry is one small sidecar file per artifact (_reg/<name>.json). No shared file is read-modified-written,
# so parallel saves (ensemble runs) and several server processes cannot lose each other's entries.
def _reg_dir(run_id):
    d = os.path.join(_run_dir(run_id), "_reg")
    os.makedirs(d, exist_ok=True)
    return d


def _registry(run_id):
    out = {}
    d = _reg_dir(run_id)
    for f in os.listdir(d):
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out[f[:-5]] = json.load(fh)
            except ValueError:
                pass
    return out


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _tmp_suffix():
    return f".{os.getpid()}.{threading.get_ident()}.tmp"


def _register(run_id, name):
    p = _path(run_id, name)
    info = {"sha256": _sha(p), "bytes": os.path.getsize(p), "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dst = os.path.join(_reg_dir(run_id), name + ".json")
    tmp = dst + _tmp_suffix()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(info, f)
    os.replace(tmp, dst)
    return info


def _immutable(name):
    return name.startswith(IMMUTABLE_PREFIXES)


def _write_text(run_id, name, text, overwrite):
    """Create exclusively unless overwrite is allowed (then replace atomically). Immutable names never overwrite."""
    p = _path(run_id, name)
    if os.path.exists(p) and _immutable(name):
        raise ToolError(f"{name} is a raw agent output and is immutable; save under a new name (for example a new run suffix)")
    if overwrite and not _immutable(name):
        tmp = p + _tmp_suffix()
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, p)
        return p
    try:
        with open(p, "x", encoding="utf-8", newline="") as f:      # exclusive create: atomic, no race on "already exists"
            f.write(text)
    except FileExistsError:
        raise ToolError(f"{name} already exists" + ("; raw agent outputs are immutable" if _immutable(name) else "; pass overwrite=true to replace it"))
    return p


def _py(script, *args):
    p = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", cwd=TOOLS_DIR, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# ------------------------------------------------------------------ tools
def save_artifact(run_id, name, content=None, json_value=None, overwrite=False):
    """Store text or JSON under a name and record its sha256. Raw agent outputs are immutable."""
    if (content is None) == (json_value is None):
        raise ToolError("provide exactly one of content (string) or json_value (object)")
    text = content if content is not None else json.dumps(json_value, ensure_ascii=False, indent=2)
    _write_text(run_id, name, text, overwrite)
    info = _register(run_id, name)
    return {"name": name, **info}


def get_artifact(run_id, name, offset=0, max_chars=20000):
    """Read a text artifact (sliced). Binary artifacts return metadata only."""
    p = _path(run_id, name, must_exist=True)
    if name.lower().endswith((".xlsx", ".docx", ".pdf", ".png", ".zip")):
        return {"name": name, "binary": True, "bytes": os.path.getsize(p), "sha256": _sha(p)}
    text = open(p, encoding="utf-8").read()
    return {"name": name, "offset": offset, "total_chars": len(text), "truncated": offset + max_chars < len(text),
            "text": text[offset:offset + max_chars]}


def list_artifacts(run_id):
    d = _run_dir(run_id)
    reg = _registry(run_id)
    return {"run_id": run_id, "artifacts": [
        {"name": f, "bytes": os.path.getsize(os.path.join(d, f)), "registered": f in reg}
        for f in _visible(run_id)]}


def verify_artifacts(run_id):
    """Re-hash every registered artifact; reports any that changed or vanished since saving."""
    bad = []
    for name, info in _registry(run_id).items():
        p = os.path.join(_run_dir(run_id), name)
        if not os.path.exists(p):
            bad.append({"name": name, "problem": "missing"})
        elif _sha(p) != info["sha256"] and _immutable(name):
            bad.append({"name": name, "problem": "changed after saving (raw agent output must never be edited)"})
    return {"verified": not bad, "problems": bad}


def _load_estimate(run_id, name):
    """Load an estimate artifact; name the file and say whether it looks cut off when the JSON is invalid."""
    p = _path(run_id, name, must_exist=True)
    try:
        return ec.load(p)
    except ValueError as e:
        text = open(p, encoding="utf-8").read().rstrip()
        hint = "it looks cut off (does not end with a closing brace); ask the estimator to re-send the complete package" if not text.endswith(("}", "```"))             else "it was edited or malformed; ask the estimator to re-send the complete package"
        raise ToolError(f"{name} is not valid JSON ({e}); {len(text)} characters, ends with {text[-40:]!r}: {hint}, saved under a new name")


def _shape_problems(est):
    """Structural problems that would crash the calculator (a list of objects containing text, a missing list...)."""
    if not isinstance(est, dict):
        return ["the estimate is not a JSON object"]
    out = []

    def objects(key, required=()):
        v = est.get(key)
        if v is None:
            return []
        if not isinstance(v, list):
            out.append(f"`{key}` must be a list")
            return []
        good = []
        for i, item in enumerate(v):
            if not isinstance(item, dict):
                out.append(f"`{key}[{i}]` must be an object, found text or a number: {str(item)[:60]!r}")
            else:
                good.append(item)
                out.extend(f"`{key}[{i}]` has no `{r}`" for r in required if r not in item)
        return good

    objects("modules", ("module",))
    for mi, m in enumerate(est.get("modules") or []):
        if not isinstance(m, dict):
            continue
        tasks = m.get("tasks", [])
        if not isinstance(tasks, list):
            out.append(f"`modules[{mi}].tasks` must be a list")
            continue
        for ti, t in enumerate(tasks):
            if not isinstance(t, dict):
                out.append(f"`modules[{mi}].tasks[{ti}]` must be an object, found: {str(t)[:60]!r}")
    for key in ("overheads", "phases", "team_plan", "requirement_items"):
        objects(key)
    if not out and not any(isinstance(m, dict) and m.get("tasks") for m in est.get("modules") or []):
        out.append("the estimate has no tasks: it is a partial package or a revision patch; a complete package (modules with tasks, requirement_items, type_applicability, team_plan, phases) is required")
    return out


def calc_estimate(run_id, estimate, previous=None, hours_per_fte_week=None, out="estimation_derived.json", include_derived=False):
    """Run the calculator on an estimate artifact. Writes the derived artifact; returns a compact summary."""
    est = _load_estimate(run_id, estimate)
    problems = _shape_problems(est)
    if problems:
        raise ToolError(f"{estimate} has the wrong shape; fix the JSON and save it under a new name: " + "; ".join(problems[:8]))
    d = ec.compute(est, hours_per_fte_week)
    if previous:
        d["revision_delta"] = ec.diff(d, ec.compute(_load_estimate(run_id, previous), hours_per_fte_week))
    _write_text(run_id, out, json.dumps(d, indent=2, ensure_ascii=False), overwrite=True)
    _register(run_id, out)
    failed = [c for c in d["checks"] if not c["pass"]]
    res = {
        "ok": not [c for c in failed if c["id"] in BLOCKING],
        "derived_artifact": out,
        "blocking_failures": [c for c in failed if c["id"] in BLOCKING],
        "advisory_failures": [c for c in failed if c["id"] not in BLOCKING],
        "checks": {"passed": len(d["checks"]) - len(failed), "total": len(d["checks"])},
        "task_count": d["inputs"]["task_count"],
        "base_pert_h": d["base"]["pert"],
        "total_h": {"optimistic": d["total"]["O"], "pert": d["total"]["pert"], "pessimistic": d["total"]["P"], "p80": d["total"]["p80"]},
        "overheads": [{"name": o["name"], "pct": o["pct"], "pert_h": o["pert"]} for o in d["overheads"]],
        "weeks": d["timeline"],
        "team": [{"role": t["role"], "hours": t["hours"], "fte": t["fte"]} for t in d["team"]],
        "uncovered_requirement_items": d["uncovered_requirement_items"],
        "inferred_tasks": d["inferred_tasks"],
    }
    if previous:
        res["revision_delta"] = d["revision_delta"]
    if include_derived:
        res["derived"] = d
    return res


def ensemble_select(run_id, runs, out="estimation_derived.json", report="ensemble_report.json", select_as="estimation_pass2.json"):
    """Pick the median run among several estimator runs; copies it byte-for-byte to select_as (immutable)."""
    if not isinstance(runs, list) or len(runs) < 2:
        raise ToolError("runs must be a list of at least two artifact names")
    paths = [_path(run_id, r, must_exist=True) for r in runs]
    rep_p, out_p = _path(run_id, report), _path(run_id, out)
    code, so, se = _py("ensemble_select.py", *paths, "-o", out_p, "--report", rep_p)
    if code != 0:
        raise ToolError(f"ensemble_select failed: {se or so}")
    rep = json.load(open(rep_p, encoding="utf-8"))
    chosen = os.path.basename(rep["selected"]["path"])
    dst = _path(run_id, select_as)
    if os.path.exists(dst):
        if _sha(dst) != _sha(os.path.join(_run_dir(run_id), chosen)):
            raise ToolError(f"{select_as} already exists with different content")
    else:
        shutil.copyfile(os.path.join(_run_dir(run_id), chosen), dst)
    _register(run_id, select_as)
    _register(run_id, out)
    _register(run_id, report)
    return {"ok": True, "selected": chosen, "selected_as": select_as, "spread_pct": rep["spread_pct"], "spread_level": rep["spread_level"],
            "advice": rep["advice"], "flags": rep["flags"], "widest_modules": rep["module_spread"][:5],
            "runs": [{k: r.get(k) for k in ("path", "total_pert", "weeks_likely", "task_count", "blocking_failures")} for r in rep["runs"]]}


def prepare_review(run_id, estimate, derived, out="review_input.json", include_content=False):
    """Create the reviewer's input (estimate without the estimator's reasoning, plus calculator numbers)."""
    code, so, se = _py("prepare_review.py", _path(run_id, estimate, True), _path(run_id, derived, True), "-o", _path(run_id, out))
    if code != 0:
        raise ToolError(f"prepare_review failed: {se or so}")
    _register(run_id, out)
    res = {"ok": True, "artifact": out, "bytes": os.path.getsize(_path(run_id, out))}
    if include_content:
        res["content"] = open(_path(run_id, out), encoding="utf-8").read()
    return res


def build_workbook(run_id, estimate, derived, out_name, client="", version="1.0", state="draft", draft="", sources="",
                   clarifications=None, check=True):
    """Build the estimation workbook (.xlsx) from the estimate and derived artifacts."""
    if not out_name.lower().endswith(".xlsx"):
        raise ToolError("out_name must end with .xlsx")
    args = [_path(run_id, estimate, True), _path(run_id, derived, True), "-o", _path(run_id, out_name),
            "--client", client, "--version", version, "--state", state]
    if draft:
        args += ["--draft", draft]
    if sources:
        args += ["--sources", sources]
    if clarifications:
        if isinstance(clarifications, str) and not clarifications.lower().endswith(".json"):
            raise ToolError("clarifications must be a list of Q&A objects or the name of a .json artifact (for example clarifications.json), not " + repr(clarifications))
        if isinstance(clarifications, list):
            save_artifact(run_id, "clarifications.json", json_value=clarifications, overwrite=True)
            clarifications = "clarifications.json"
        args += ["--clarifications", _path(run_id, clarifications, True)]
    if check:
        args.append("--check")
    code, so, se = _py("build_workbook.py", *args)
    if code != 0 and "MISMATCH" not in so:
        raise ToolError(f"build_workbook failed: {se or so}")
    _register(run_id, out_name)
    return {"ok": code == 0, "artifact": out_name, "bytes": os.path.getsize(_path(run_id, out_name)), "output": so}


def check_consistency(run_id, forbid="", expose_hours=False, estimate="", derived=""):
    """Run the scripted X-checks over the run's artifacts (Proposal_*.md, Presales_Review_Notes_*.md, Estimation_*.xlsx, ...)."""
    args = ["--dir", _run_dir(run_id)]
    if estimate:
        args += ["--estimate", os.path.basename(_path(run_id, estimate, must_exist=True))]
    if derived:
        args += ["--derived", os.path.basename(_path(run_id, derived, must_exist=True))]
    if forbid:
        args += ["--forbid", forbid]
    if expose_hours:
        args.append("--expose-hours")
    code, so, se = _py("check_consistency.py", *args)
    p = os.path.join(_run_dir(run_id), "consistency_report.json")
    if not os.path.exists(p):
        raise ToolError(f"check_consistency produced no report: {se or so}")
    res = json.load(open(p, encoding="utf-8"))
    _register(run_id, "consistency_report.json")
    return {"ok": code == 0,
            "failures": [r for r in res if not r["pass"] and r["level"] == "fail"],
            "warnings": [r for r in res if not r["pass"] and r["level"] == "warn"],
            "passed": [r["id"] for r in res if r["pass"]]}


def hash_text(content):
    """sha256 of a string (for the case record when a platform stores artifacts elsewhere)."""
    return {"sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(), "chars": len(content)}


MASTER_DIR = os.path.normpath(os.path.join(HERE, "..", "master"))


def get_module(name):
    """Return one of the master's loadable modules: proposal_template, quality_gate, fault_tolerance."""
    allowed = sorted(os.path.splitext(f)[0] for f in os.listdir(MASTER_DIR) if f.endswith(".md"))
    if name not in allowed:
        raise ToolError(f"unknown module {name!r}; available: {allowed}")
    with open(os.path.join(MASTER_DIR, name + ".md"), encoding="utf-8") as f:
        return {"name": name, "text": f.read()}


# ------------------------------------------------------------------ registry of tools (also feeds the manifest)
def _p(**props):
    required = [k for k, v in props.items() if v.pop("_req", False)]
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


S = lambda desc, req=False, **kw: dict({"type": "string", "description": desc, "_req": req}, **kw)  # noqa: E731
TOOLS = {
    "save_artifact": (save_artifact, "Store text or a JSON object as a named artifact in the run's folder and record its sha256. Raw agent outputs (estimation_pass*, estimation_revision*, reviewer_findings*, scope_summary*) are immutable. Use this once for each sub-agent reply, then refer to it by name.",
                      _p(run_id=S("Run identifier, e.g. client-date", True), name=S("Artifact name, e.g. estimation_pass2.json", True),
                         content=S("Text to store (exactly one of content or json_value)"), json_value={"type": "object", "description": "JSON object to store", "_req": False},
                         overwrite={"type": "boolean", "description": "Replace an existing non-immutable artifact", "_req": False})),
    "get_artifact": (get_artifact, "Read a text artifact (sliced by offset and max_chars). Binary files return metadata only.",
                     _p(run_id=S("Run identifier", True), name=S("Artifact name", True), offset={"type": "integer", "_req": False}, max_chars={"type": "integer", "_req": False})),
    "list_artifacts": (list_artifacts, "List artifacts in a run.", _p(run_id=S("Run identifier", True))),
    "verify_artifacts": (verify_artifacts, "Re-hash registered artifacts; reports any raw agent output that changed after saving.", _p(run_id=S("Run identifier", True))),
    "calc_estimate": (calc_estimate, "Run the deterministic calculator on an estimate artifact: PERT, totals, overheads, by-type, team hours, timeline, 25 structural checks. Writes the derived artifact and returns a compact summary. Use after every estimator output; blocking failures mean the estimate must be retried.",
                      _p(run_id=S("Run identifier", True), estimate=S("Artifact name of the estimator JSON (raw reply with a ```json fence is accepted)", True),
                         previous=S("Artifact name of the previous estimate, for a revision delta"), hours_per_fte_week={"type": "number", "_req": False},
                         out=S("Derived artifact name (default estimation_derived.json)"), include_derived={"type": "boolean", "_req": False})),
    "ensemble_select": (ensemble_select, "Given several independent estimator runs (artifact names), select the median run, copy it byte-for-byte to select_as, write the derived artifact and a spread report.",
                        _p(run_id=S("Run identifier", True), runs={"type": "array", "items": {"type": "string"}, "description": "Artifact names of the runs", "_req": True},
                           out=S("Derived artifact name"), report=S("Report artifact name"), select_as=S("Name for the selected raw estimate (default estimation_pass2.json)"))),
    "prepare_review": (prepare_review, "Create the reviewer input: the estimate without the estimator's reasoning, plus calculator numbers.",
                       _p(run_id=S("Run identifier", True), estimate=S("Estimate artifact name", True), derived=S("Derived artifact name", True),
                          out=S("Output artifact name"), include_content={"type": "boolean", "description": "Also return the JSON text", "_req": False})),
    "build_workbook": (build_workbook, "Build the estimation workbook (.xlsx) with live formulas from the estimate and derived artifacts; verifies totals independently.",
                       _p(run_id=S("Run identifier", True), estimate=S("Estimate artifact name", True), derived=S("Derived artifact name", True),
                          out_name=S("Workbook artifact name ending in .xlsx, e.g. Estimation_Client_V1.0.xlsx", True), client=S("Client name"), version=S("Version"),
                          state=S("Estimate state", enum=["draft", "delivery_reviewed", "approved"]), draft=S("Comma-separated failed blocking check ids; stamps the workbook DRAFT"),
                          sources=S("Source document names"), clarifications={"type": ["array", "string", "null"], "description": "List of Q&A objects, or the name of a JSON artifact", "_req": False},
                          check={"type": "boolean", "_req": False})),
    "check_consistency": (check_consistency, "Run the scripted consistency checks over the run's artifacts. Needs Proposal_*.md, Presales_Review_Notes_*.md, Estimation_*.xlsx, the estimate and the derived artifact saved in the run. Returns failures and warnings.",
                          _p(run_id=S("Run identifier", True), forbid=S("Comma-separated names of other clients that must not appear"), expose_hours={"type": "boolean", "_req": False},
                             estimate=S("Final estimate artifact name (default: newest complete revision, retry or pass 2)"), derived=S("Derived artifact name (default estimation_derived.json)"))),
    "hash_text": (hash_text, "sha256 of a string.", _p(content=S("Text", True))),
    "get_module": (get_module, "Load one of the master agent's instruction modules by name: proposal_template (load at the start of proposal construction), quality_gate (load at finalisation), fault_tolerance (load only for exceptional inputs).",
                   _p(name=S("Module name", True, enum=["proposal_template", "quality_gate", "fault_tolerance"]))),
}


_TRUE, _FALSE = {"true", "1", "yes", "y"}, {"false", "0", "no", "n"}


def _coerce_value(spec, value):
    """Form-based platforms send every value as a string. Convert it to the schema's type; returns (keep, value)."""
    if not isinstance(value, str):
        return True, value
    types = spec.get("type")
    types = types if isinstance(types, list) else [types]
    s = value.strip()
    if "string" in types:
        if s[:1] in ("[", "{") and ("array" in types or "object" in types):
            try:
                return True, json.loads(s)
            except ValueError:
                pass
        return True, value
    if s == "":
        return False, None
    t = types[0]
    try:
        if t == "integer":
            return True, int(float(s))
        if t == "number":
            return True, float(s)
        if t == "boolean":
            if s.lower() in _TRUE:
                return True, True
            if s.lower() in _FALSE:
                return True, False
            raise ValueError
        if t in ("object", "array"):
            try:
                v = json.loads(s)
            except ValueError:
                if t == "array":
                    return True, [x.strip() for x in s.split(",") if x.strip()]
                raise
            if not isinstance(v, list if t == "array" else dict):
                raise ValueError
            return True, v
    except ValueError:
        raise ToolError(f"cannot read {value!r} as {t}")
    return True, value


def _coerce_args(name, args):
    """Make string-typed arguments match the tool's schema; drop empty optional values so the defaults apply."""
    schema = TOOLS[name][2]
    props, required = schema["properties"], set(schema.get("required", []))
    out = {}
    for k, v in (args or {}).items():
        spec = props.get(k)
        if spec is None:
            out[k] = v
            continue
        if k not in required and (v is None or (isinstance(v, str) and v.strip() == "")):
            continue
        keep, v = _coerce_value(spec, v)
        if keep:
            out[k] = v
    return out


def _where(e):
    tb = traceback.extract_tb(e.__traceback__)
    return f" (at {os.path.basename(tb[-1].filename)}:{tb[-1].lineno})" if tb else ""


def call(name, args=None):
    if name not in TOOLS:
        return {"ok": False, "error": f"unknown tool {name!r}", "tools": sorted(TOOLS)}
    try:
        res = TOOLS[name][0](**_coerce_args(name, args))
        return dict({"ok": True}, **res) if "ok" not in res else res
    except ToolError as e:
        return {"ok": False, "error": str(e)}
    except TypeError as e:
        return {"ok": False, "error": f"bad arguments for {name}: {e}{_where(e)}"}
    except Exception as e:  # never raise to the platform
        return {"ok": False, "error": f"{type(e).__name__}: {e}{_where(e)}"}


def manifest():
    return {"version": "v4", "artifact_root_env": "ARTIFACT_ROOT",
            "tools": [{"name": n, "description": d, "parameters": s} for n, (_, d, s) in TOOLS.items()]}


def main():
    if "--manifest" in sys.argv:
        print(json.dumps(manifest(), indent=2))
        return
    req = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(call(req.get("tool", ""), req.get("args", {})), ensure_ascii=False))


if __name__ == "__main__":
    main()
