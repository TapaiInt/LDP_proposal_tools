#!/usr/bin/env python3
"""Pick the median run from several independent estimator runs and report spread.

Task lists differ between runs, so tasks are never merged. Instead each run is
passed through estimate_calc, runs with blocking failures are set aside, and the
run whose total PERT is the median is selected. Spread is reported per run total
and per module (modules matched by normalised name).

Usage:
    python ensemble_select.py run1.json run2.json run3.json -o estimation_derived.json \
        --report ensemble_report.json
With two eligible runs the higher total is chosen (conservative).
"""
import argparse
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estimate_calc as ec  # noqa: E402

BLOCKING = {"S1", "S2", "S3", "S4", "S5", "T1", "T2", "T3", "T4", "P1", "P2", "A1", "A2", "A3", "A4", "O1", "R1"}
WARN_SPREAD, HIGH_SPREAD = 0.15, 0.30


def norm(name):
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("-o", "--out", default="estimation_derived.json")
    ap.add_argument("--report", default="ensemble_report.json")
    ap.add_argument("--hpw", type=float)
    a = ap.parse_args()
    if len(a.runs) < 2:
        sys.exit("need at least two runs")

    runs = []
    for i, p in enumerate(a.runs):
        try:
            d = ec.compute(ec.load(p), a.hpw)
        except Exception as e:  # unparseable run
            runs.append({"index": i, "path": p, "error": str(e), "blocking_failures": ["PARSE"], "derived": None})
            continue
        bf = [c["id"] for c in d["checks"] if not c["pass"] and c["id"] in BLOCKING]
        runs.append({"index": i, "path": p, "total_pert": d["total"]["pert"], "weeks_likely": d["timeline"]["weeks_likely"],
                     "task_count": d["inputs"]["task_count"], "blocking_failures": bf, "derived": d})

    eligible = [r for r in runs if not r["blocking_failures"]]
    pool = eligible if eligible else [r for r in runs if r["derived"]]
    if not pool:
        sys.exit("no usable run")
    ordered = sorted(pool, key=lambda r: r["total_pert"])
    chosen = ordered[len(ordered) // 2]  # upper median: conservative for an even count
    totals = [r["total_pert"] for r in pool]
    med = statistics.median(totals)
    spread = (max(totals) - min(totals)) / med if med else 0.0

    mods = {}
    for r in pool:
        for m in r["derived"]["modules"]:
            mods.setdefault(norm(m["module"]), {})[r["index"]] = m["pert"]
    module_spread, flags = [], []
    for k, v in mods.items():
        if len(v) < len(pool):
            flags.append(f"module '{k}' present in {len(v)} of {len(pool)} runs")
        if len(v) > 1:
            hi, lo, mid = max(v.values()), min(v.values()), statistics.median(v.values())
            s = (hi - lo) / mid if mid else 0.0
            module_spread.append({"module": k, "min": lo, "max": hi, "spread": round(s, 3)})
            if s > HIGH_SPREAD:
                flags.append(f"module '{k}' spread {s:.0%} across runs")
    level = "high" if spread > HIGH_SPREAD else "warn" if spread > WARN_SPREAD else "ok"
    if len(runs) != len(pool):
        flags.append(f"{len(runs) - len(pool)} run(s) set aside for blocking failures")

    report = {
        "selected": {"index": chosen["index"], "path": chosen["path"], "total_pert": chosen["total_pert"]},
        "runs": [{k: v for k, v in r.items() if k != "derived"} for r in runs],
        "spread_pct": round(spread * 100, 1), "spread_level": level,
        "module_spread": sorted(module_spread, key=lambda x: -x["spread"]),
        "flags": flags,
        "advice": {"ok": "Spread within 15%: accept the median run.",
                   "warn": "Spread 15-30%: accept the median run, list the widest modules in the Review Notes.",
                   "high": "Spread above 30%: scope is probably under-specified; ask discovery questions or send for review before relying on the number."}[level],
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(dict(chosen["derived"], ensemble={"spread_pct": report["spread_pct"], "level": level,
                                                       "selected_path": chosen["path"]}), f, indent=2, ensure_ascii=False)
    with open(a.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"selected {chosen['path']} (total PERT {chosen['total_pert']} h) | spread {report['spread_pct']}% [{level}]")
    for fl in flags:
        print("  flag:", fl)


if __name__ == "__main__":
    main()
