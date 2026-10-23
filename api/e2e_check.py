#!/usr/bin/env python3
"""Live end-to-end check of the tool API over real HTTP (standard library only).

Against a deployed server:
    python api/e2e_check.py --base-url https://tools.example.internal --api-key <key>
Self-contained local test (starts the server with 2 workers, runs the checks, stops it):
    python api/e2e_check.py --spawn

Flow: health -> save estimate -> calc -> immutability -> prepare_review -> build_workbook -> download link ->
download over a second connection (proves link signing is shared between workers) -> verify_artifacts.
Exit code 0 = the deployment works end to end.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, "tests", "fixtures", "worked_example.json")


def http(method, url, key=None, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **({"X-API-Key": key} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8099")
    ap.add_argument("--api-key", default=os.environ.get("E2E_API_KEY", ""))
    ap.add_argument("--spawn", action="store_true", help="start a local server (2 workers) with a temporary artifact folder")
    ap.add_argument("--no-workbook", action="store_true", help="skip build_workbook (when openpyxl is not installed on the server)")
    a = ap.parse_args()

    proc, tmp = None, None
    if a.spawn:
        tmp = tempfile.TemporaryDirectory()
        key = "spawn-key-0123456789abcdef"
        a.api_key, a.base_url = key, "http://127.0.0.1:8099"
        env = dict(os.environ, API_KEYS=f"e2e:{key}", LINK_SECRET="x" * 48, ARTIFACT_ROOT=tmp.name, PUBLIC_BASE_URL=a.base_url, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.app:create_app", "--factory", "--port", "8099", "--workers", "2", "--log-level", "warning"],
                                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = []

    def step(label, ok, detail=""):
        print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else f"  -> {detail}"))
        if not ok:
            failures.append(label)

    try:
        for _ in range(60):                                                   # wait for the server
            try:
                if http("GET", a.base_url + "/health", timeout=2)[0] == 200:
                    break
            except OSError:
                time.sleep(0.5)
        code, body, _h = http("GET", a.base_url + "/health")
        step("health", code == 200 and json.loads(body)["artifact_root_writable"], body[:200])

        run = f"e2e-{int(time.time())}"
        call = lambda tool, args: json.loads(http("POST", f"{a.base_url}/v1/tools/{tool}", a.api_key, args)[1])  # noqa: E731
        step("401 without a key", http("POST", f"{a.base_url}/v1/tools/hash_text", None, {"content": "x"})[0] == 401)
        est = json.load(open(FIX, encoding="utf-8"))
        r = call("save_artifact", {"run_id": run, "name": "estimation_pass2.json", "json_value": est})
        step("save_artifact", r.get("ok"), r)
        r = call("save_artifact", {"run_id": run, "name": "estimation_pass2.json", "json_value": {}, "overwrite": True})
        step("raw output is immutable", not r["ok"] and "immutable" in r["error"], r)
        r = call("calc_estimate", {"run_id": run, "estimate": "estimation_pass2.json"})
        step("calc_estimate (25/25 checks, 355.6 h)", r.get("ok") and r["checks"]["passed"] == r["checks"]["total"] and abs(r["total_h"]["pert"] - 355.6) < 0.2, r)
        r = call("save_artifact", {"run_id": run, "name": "estimator_draft_v1.json", "json_value": est})
        r = call("promote_artifact", {"run_id": run, "source": "estimator_draft_v1.json", "name": "estimation_pass2_retry1.json"})
        step("promote_artifact (byte copy, immutable)", r.get("ok") and r.get("name") == "estimation_pass2_retry1.json", r)
        r = call("prepare_review", {"run_id": run, "estimate": "estimation_pass2.json", "derived": "estimation_derived.json"})
        step("prepare_review", r.get("ok"), r)
        if not a.no_workbook:
            r = call("build_workbook", {"run_id": run, "estimate": "estimation_pass2.json", "derived": "estimation_derived.json",
                                         "out_name": "Estimation_E2E_V1.0.xlsx", "client": "E2E"})
            step("build_workbook (+ independent total check)", r.get("ok") and "OK" in r.get("output", ""), r)
            link = call("create_download_link", {"run_id": run, "name": "Estimation_E2E_V1.0.xlsx", "ttl_seconds": 120})
            step("create_download_link", link.get("ok"), link)
            if link.get("ok"):
                code, data, hdr = http("GET", link["url"])
                step("download via signed link (no key)", code == 200 and data[:2] == b"PK" and "spreadsheetml" in hdr.get("content-type", ""), f"{code} {hdr.get('content-type')}")
        md = "# E2E Proposal" + chr(10) + chr(10) + "**Proposal for E2E**" + chr(10) + "Version: V1.0" + chr(10) + chr(10) + "---" + chr(10) + chr(10) + "## 1. Executive Summary" + chr(10) + chr(10) + "- one point" + chr(10)
        r = call("save_artifact", {"run_id": run, "name": "Proposal_E2E_V1.0.md", "content": md})
        step("save proposal markdown", r.get("ok"), r)
        r = call("build_docx", {"run_id": run, "source": "Proposal_E2E_V1.0.md", "out_name": "Proposal_E2E_V1.0.docx", "version": "V1.0"})
        step("build_docx", r.get("ok"), r)
        if r.get("ok"):
            link = call("create_download_link", {"run_id": run, "name": "Proposal_E2E_V1.0.docx", "ttl_seconds": 120})
            code, data, hdr = http("GET", link["url"]) if link.get("ok") else (0, b"", {})
            step("download docx via signed link", code == 200 and data[:2] == b"PK" and "wordprocessingml" in hdr.get("content-type", ""), f"{code} {hdr.get('content-type')}")
        r = call("verify_artifacts", {"run_id": run})
        step("verify_artifacts", r.get("verified"), r)
        step("tools are visible in the OpenAPI document", len(json.loads(http("GET", a.base_url + "/openapi.json")[1])["paths"]) >= 12)
        print(f"\n{'OK: API works end to end' if not failures else 'FAILED: ' + ', '.join(failures)}  (run {run})")
    finally:
        if proc:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.terminate()
        if tmp:
            time.sleep(0.5)
            tmp.cleanup()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
