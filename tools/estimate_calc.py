#!/usr/bin/env python3
"""Deterministic calculator for estimation-agent v3 output.

The sub-agent writes judgments (tasks with O/M/P, overhead percentages, phases,
team plan). This script computes every derived number: PERT, totals, overheads,
18-type roll-up, role hours, schedule, structural checks, revision delta.

Usage:
    python estimate_calc.py estimation_pass2.json -o estimation_derived.json
    python estimate_calc.py new.json --previous old.json -o derived.json
Input may be a raw sub-agent response (first ```json fence is used) or plain JSON.
"""
import argparse
import json
import math
import re
import sys

TYPES = [
    "Discovery / Requirement Analysis", "UI/UX", "Frontend", "Backend", "Database",
    "API Integration", "Third-party Integration", "AI/ML", "RAG", "Testing / QA",
    "DevOps", "Cloud Infrastructure", "Security", "Data Migration", "Documentation",
    "Project Management", "Monitoring / Logging", "Maintenance",
]
DEFAULT_PCT = {"qa": 22, "pm": 8, "uat": 10, "docs": 3}
DERIVED_KEYS = {
    "pert_h", "module_pert_h", "base_dev_design_pert_h", "effort_summary", "effort_by_type",
    "weeks_min", "weeks_likely", "weeks_max", "comparison_to_reference", "total_build_hours",
}
MONEY = re.compile(r"(₹|\bINR\b|\bRs\.?\s?\d|\$\s?\d|\bUSD\b|\blakh\b)", re.I)
Z80 = 0.8416


def load(path):
    text = open(path, encoding="utf-8").read()
    s = text.lstrip()
    if s.startswith("{"):
        return json.loads(s)
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        raise ValueError("no JSON object found")
    return json.loads(text[i:j + 1])


def kind_of(name):
    n = name.lower()
    if "contingency" in n:
        return "cont"
    if "uat" in n:
        return "uat"
    if "project management" in n or n.strip() in ("pm", "pm effort"):
        return "pm"
    if "doc" in n:
        return "docs"
    if "qa" in n or "quality" in n or "test" in n:
        return "qa"
    return "other"


def schedule(phases, phase_hours, fte, hpw, cont_pct):
    """Longest-path schedule. Returns (weeks_with_buffer, per-phase dict, errors)."""
    by_name = {p["name"]: p for p in phases}
    out, errors, visiting = {}, [], set()

    def end_of(name):
        if name in out:
            return out[name]["end"]
        if name in visiting:
            errors.append(f"dependency cycle at phase '{name}'")
            return 0.0
        visiting.add(name)
        p = by_name[name]
        start = max([end_of(d) for d in p.get("depends_on", []) if d in by_name] or [0.0])
        start += float(p.get("lead_time_weeks") or 0)
        cap = sum(fte.get(r, 0.0) for r in p.get("roles", [])) * hpw
        hrs = phase_hours.get(name, 0.0)
        if hrs > 0 and cap <= 0:
            errors.append(f"phase '{name}' has {hrs:.1f} h but zero capacity (roles/FTE missing)")
            dur = 0.0
        else:
            dur = hrs / cap if cap else 0.0
        visiting.discard(name)
        out[name] = {"start": round(start, 2), "weeks": round(dur, 2), "end": start + dur,
                     "hours": round(hrs, 1), "capacity_h_per_week": round(cap, 1)}
        return start + dur

    total = max([end_of(n) for n in by_name] or [0.0])
    for v in out.values():
        v["end"] = round(v["end"], 2)
    return total * (1 + cont_pct / 100.0), out, errors


def compute(est, hpw=None):
    checks, derived = [], {}

    def chk(cid, ok, detail):
        checks.append({"id": cid, "pass": bool(ok), "detail": detail})

    hpw = hpw or (est.get("timeline_notes") or {}).get("productive_hours_per_fte_week") or 35
    tasks, modules = [], []
    for m in est.get("modules", []):
        for t in m.get("tasks", []):
            t = dict(t, module=m["module"])
            O, M, P = (float(t.get(k, 0) or 0) for k in ("optimistic_h", "most_likely_h", "pessimistic_h"))
            t.update(O=O, M=M, P=P, pert=(O + 4 * M + P) / 6, sigma=(P - O) / 6)
            tasks.append(t)
        mt = [t for t in tasks if t["module"] == m["module"]]
        modules.append({"module": m["module"], "tasks": len(mt),
                        "O": sum(t["O"] for t in mt), "M": sum(t["M"] for t in mt),
                        "P": sum(t["P"] for t in mt), "pert": sum(t["pert"] for t in mt)})

    # ---- structural checks
    ids = [t.get("id") for t in tasks]
    chk("S1", len(ids) == len(set(ids)) and all(ids), f"{len(ids)} tasks, ids unique and present")
    bad = [t["id"] for t in tasks if not (t["O"] <= t["M"] <= t["P"])]
    chk("S2", not bad, f"O<=M<=P violated: {bad}" if bad else "O<=M<=P on every task")
    badtype = [t["id"] for t in tasks if t.get("type") not in TYPES]
    chk("S3", not badtype, f"invalid type: {badtype}" if badtype else "all task types valid")
    pnames = {p["name"] for p in est.get("phases", [])}
    roles_planned = {r["role"] for r in est.get("team_plan", [])}
    nophase = [t["id"] for t in tasks if t.get("phase") not in pnames]
    chk("S4", not nophase, f"tasks with missing/unknown phase: {nophase}" if nophase else "every task in a defined phase")
    norole = [t["id"] for t in tasks if t.get("role") not in roles_planned]
    chk("S5", not norole, f"task roles absent from team_plan: {norole}" if norole else "all task roles in team_plan")

    # traceability
    items = {r["id"]: r for r in est.get("requirement_items", [])}
    tids = set(ids)
    orphan = [t["id"] for t in tasks if t.get("origin") == "requirement" and not [r for r in t.get("req_ids", []) if r in items]]
    chk("T1", not orphan, f"requirement-origin tasks without valid req_ids: {orphan}" if orphan else "requirement tasks all traced")
    unsrc = [t["id"] for t in tasks if t.get("origin") not in ("requirement", "inferred_necessary", "buffer")]
    chk("T2", not unsrc, f"tasks with invalid origin: {unsrc}" if unsrc else "all tasks have a valid origin")
    badlink = [r["id"] for r in items.values() if r.get("coverage") in ("covered", "partial")
               and (not r.get("task_ids") or any(x not in tids for x in r["task_ids"]))]
    chk("T3", not badlink, f"covered/partial items with missing tasks: {badlink}" if badlink else "covered items link to real tasks")
    back = [t["id"] for t in tasks for r in t.get("req_ids", [])
            if r in items and t["id"] not in items[r].get("task_ids", [])]
    chk("T4", not back, f"task->item links not mirrored on item: {sorted(set(back))}" if back else "task and item links agree")
    notest = [r["id"] for r in items.values() if r.get("coverage") == "not_estimated"]
    derived["uncovered_requirement_items"] = notest
    chk("T5", True, f"{len(notest)} requirement items marked not_estimated (reported for review)")
    inferred = [t["id"] for t in tasks if t.get("origin") == "inferred_necessary"]
    derived["inferred_tasks"] = inferred

    # sizing
    over = [t["id"] for t in tasks if t["M"] > 40 and not (t.get("notes") or "").strip()]
    small = [t["id"] for t in tasks if t["M"] < 8]
    chk("Z1", not over, f"M>40h without a note: {over}" if over else "no unexplained oversize tasks")
    share = (len(small) / len(tasks)) if tasks else 0
    chk("Z2", share <= 0.10, f"{len(small)} of {len(tasks)} tasks under 8h ({share:.0%}); limit ~10%")

    # ---- totals
    base = {k: sum(t[k] for t in tasks) for k in ("O", "M", "P")}
    base["pert"] = sum(t["pert"] for t in tasks)
    sigma = math.sqrt(sum(t["sigma"] ** 2 for t in tasks))
    ov = []
    kinds = {}
    for o in est.get("overheads", []):
        k = kind_of(o["name"])
        pct = float(o["pct"])
        row = {"name": o["name"], "kind": k, "pct": pct,
               "O": base["O"] * pct / 100, "pert": base["pert"] * pct / 100, "P": base["P"] * pct / 100,
               "reason_if_changed": o.get("reason_if_changed")}
        ov.append(row)
        kinds[k] = row
    chk("O1", all(k in kinds for k in ("qa", "pm", "uat", "docs", "cont")), "all five overhead lines present")
    chg = [o["name"] for o in ov if o["kind"] in DEFAULT_PCT and o["pct"] != DEFAULT_PCT[o["kind"]] and not o["reason_if_changed"]]
    chk("O2", not chg, f"non-default pct without reason: {chg}" if chg else "overhead deviations all justified")
    cont = kinds.get("cont")
    chk("O3", bool(cont) and cont["pct"] >= 6 and (cont["pct"] == 6 or bool(cont["reason_if_changed"])),
        "contingency >= 6% and justified when raised")
    ov_pct = sum(o["pct"] for o in ov)
    total = {k: base[k] * (1 + ov_pct / 100) for k in ("O", "P")}
    total["pert"] = base["pert"] * (1 + ov_pct / 100)
    total["M"] = base["M"] * (1 + ov_pct / 100)
    total["p80"] = (base["pert"] + Z80 * sigma) * (1 + ov_pct / 100)

    # ---- by type
    alloc = {"Testing / QA": ["qa", "uat"], "Project Management": ["pm"], "Documentation": ["docs"]}
    applic = {a["type"]: a for a in est.get("type_applicability", [])}
    chk("A1", set(TYPES) <= set(applic), f"type_applicability missing: {sorted(set(TYPES) - set(applic))}" if not set(TYPES) <= set(applic) else "all 18 types have applicability")
    by_type = []
    for ty in TYPES:
        th = sum(t["pert"] for t in tasks if t.get("type") == ty)
        oh = sum(kinds[k]["pert"] for k in alloc.get(ty, []) if k in kinds)
        ap = applic.get(ty, {})
        by_type.append({"type": ty, "applicability": ap.get("applicability"), "task_hours": th,
                        "overhead_hours": oh, "total_hours": th + oh, "reason": ap.get("reason")})
    mism = [b["type"] for b in by_type if (b["total_hours"] > 0 and b["applicability"] in ("not_applicable", "excluded"))
            or (b["total_hours"] == 0 and b["applicability"] == "in_scope")]
    chk("A2", not mism, f"applicability contradicts hours: {mism}" if mism else "applicability consistent with hours")
    maint = [t["id"] for t in tasks if t.get("type") == "Maintenance"]
    chk("A3", not maint, f"Maintenance tasks in build (not allowed): {maint}" if maint else "no Maintenance tasks in build")
    contingency_h = kinds["cont"]["pert"] if "cont" in kinds else 0.0
    recon = sum(b["total_hours"] for b in by_type) + contingency_h
    chk("A4", abs(recon - total["pert"]) <= 0.1, f"by-type + contingency = {recon:.1f} vs total {total['pert']:.1f}")

    # ---- roles
    role_h = {}
    for t in tasks:
        role_h[t["role"]] = role_h.get(t["role"], 0.0) + t["pert"]
    for k, r in (("qa", "QA Engineer"), ("uat", "QA Engineer"), ("pm", "Project Manager"), ("docs", "Business Analyst")):
        if k in kinds:
            role_h[r] = role_h.get(r, 0.0) + kinds[k]["pert"]
    fte = {r["role"]: float(r.get("fte") or 0) for r in est.get("team_plan", [])}
    team = [{"role": r, "hours": h, "fte": fte.get(r), "phases": next((x.get("phases") for x in est.get("team_plan", []) if x["role"] == r), None)}
            for r, h in sorted(role_h.items())]
    chk("R1", all(r in fte for r in role_h), f"roles with hours but no FTE: {[r for r in role_h if r not in fte]}")

    # ---- schedule (PM overhead runs in parallel; QA/UAT/docs attach to phases by kind)
    phases = est.get("phases", [])
    ph_hours = {}
    for t in tasks:
        ph_hours[t.get("phase")] = ph_hours.get(t.get("phase"), 0.0) + t["pert"]
    for p in phases:
        for k in ("qa", "uat", "docs"):
            pk = {"qa": "qa", "uat": "uat", "docs": "handover"}[k]
            if p.get("kind") == pk and k in kinds:
                ph_hours[p["name"]] = ph_hours.get(p["name"], 0.0) + kinds[k]["pert"]
    for k, pk in (("qa", "qa"), ("uat", "uat"), ("docs", "handover")):
        if k in kinds and not any(p.get("kind") == pk for p in phases):
            chk(f"P-{k}", False, f"no phase of kind '{pk}' to carry the {k.upper()} overhead hours")
    cpct = kinds["cont"]["pct"] if "cont" in kinds else 0
    fO = total["O"] / total["pert"] if total["pert"] else 1.0
    fP = total["P"] / total["pert"] if total["pert"] else 1.0
    w_like, ph_out, errs = schedule(phases, ph_hours, fte, hpw, cpct)
    w_min, _, _ = schedule(phases, {k: v * fO for k, v in ph_hours.items()}, fte, hpw, cpct)
    w_max, _, _ = schedule(phases, {k: v * fP for k, v in ph_hours.items()}, fte, hpw, cpct)
    chk("P1", not errs, "; ".join(errs) if errs else "schedule resolved: no cycles, capacity present")
    lead_missing = [p["name"] for p in phases if p.get("depends_on") and not all(d in pnames for d in p["depends_on"])]
    chk("P2", not lead_missing, f"phases with unknown dependencies: {lead_missing}" if lead_missing else "phase dependencies valid")

    # ---- misc checks
    present = DERIVED_KEYS & set(est.keys())
    for t in est.get("modules", []):
        present |= DERIVED_KEYS & set(t.keys())
        for tk in t.get("tasks", []):
            present |= {"pert_h"} & set(tk.keys())
    chk("D1", not present, f"sub-agent wrote derived fields (ignored): {sorted(present)}" if present else "no derived fields written by sub-agent")
    blob = json.dumps(est, ensure_ascii=False)
    hits = sorted(set(m.group(0) for m in MONEY.finditer(blob)))
    chk("M1", not hits, f"money strings found: {hits}" if hits else "no money values")
    ps = [c.get("price_status") for c in est.get("cost_drivers", [])]
    chk("M2", all(p == "not_estimated" for p in ps), "cost_drivers price_status all not_estimated")

    derived.update({
        "inputs": {"productive_hours_per_fte_week": hpw, "task_count": len(tasks)},
        "tasks": [{"id": t["id"], "module": t["module"], "type": t.get("type"), "role": t.get("role"),
                   "phase": t.get("phase"), "O": t["O"], "M": t["M"], "P": t["P"],
                   "pert": round(t["pert"], 2), "sigma": round(t["sigma"], 2)} for t in tasks],
        "modules": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items()} for m in modules],
        "base": {k: round(v, 1) for k, v in base.items()},
        "overheads": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in o.items()} for o in ov],
        "total": {k: round(v, 1) for k, v in total.items()},
        "by_type": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in b.items()} for b in by_type],
        "team": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()} for r in team],
        "phases": ph_out,
        "timeline": {"weeks_min": round(w_min, 1), "weeks_likely": round(w_like, 1), "weeks_max": round(w_max, 1),
                     "contingency_buffer_pct": cpct},
        "checks": checks,
    })
    return derived


def diff(new, old):
    a = {t["id"]: t for t in old["tasks"]}
    b = {t["id"]: t for t in new["tasks"]}
    return {
        "tasks_added": sorted(set(b) - set(a)),
        "tasks_removed": sorted(set(a) - set(b)),
        "tasks_changed": [{"id": i, "from_pert": a[i]["pert"], "to_pert": b[i]["pert"]}
                          for i in sorted(set(a) & set(b)) if abs(a[i]["pert"] - b[i]["pert"]) > 0.05],
        "hours_delta": round(new["total"]["pert"] - old["total"]["pert"], 1),
        "timeline_delta_weeks": round(new["timeline"]["weeks_likely"] - old["timeline"]["weeks_likely"], 1),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default="estimation_derived.json")
    ap.add_argument("--previous")
    ap.add_argument("--hpw", type=float, help="productive hours per FTE-week (default 35)")
    a = ap.parse_args()
    d = compute(load(a.input), a.hpw)
    if a.previous:
        d["revision_delta"] = diff(d, compute(load(a.previous), a.hpw))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    t, tl = d["total"], d["timeline"]
    fails = [c for c in d["checks"] if not c["pass"]]
    print(f"tasks {d['inputs']['task_count']} | base PERT {d['base']['pert']} h | total O/PERT/P "
          f"{t['O']}/{t['pert']}/{t['P']} h (P80 {t['p80']}) | weeks {tl['weeks_min']}/{tl['weeks_likely']}/{tl['weeks_max']}")
    print(f"checks: {len(d['checks']) - len(fails)}/{len(d['checks'])} pass")
    for c in fails:
        print(f"  FAIL {c['id']}: {c['detail']}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
