#!/usr/bin/env python3
"""Build the reviewer's input: the estimate WITHOUT the estimator's reasoning, plus calculator numbers.

The reviewer must judge the estimate independently, so these fields are removed:
task `notes`, requirement-item `note`, `confidence`, `answered_questions[].effect_on_estimate`,
`calibration_ref`, `closest_reference`, overhead `reason_if_changed`, `self_check`, `risks[].mitigation`.

Usage:
    python prepare_review.py estimation_pass2.json estimation_derived.json -o review_input.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estimate_calc as ec  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("estimate")
    ap.add_argument("derived")
    ap.add_argument("-o", "--out", default="review_input.json")
    a = ap.parse_args()
    est = ec.load(a.estimate)
    der = json.load(open(a.derived, encoding="utf-8"))

    for m in est.get("modules", []):
        m.pop("calibration_ref", None)
        m.pop("confidence", None)
        for t in m.get("tasks", []):
            t.pop("notes", None)
    for r in est.get("requirement_items", []):
        r.pop("note", None)
    for o in est.get("overheads", []):
        o.pop("reason_if_changed", None)
    for r in est.get("risks", []):
        r.pop("mitigation", None)
    for k in ("confidence", "self_check", "revision"):
        est.pop(k, None)
    est.get("understanding", {}).pop("closest_reference", None)
    for q in est.get("answered_questions", []):
        q.pop("effect_on_estimate", None)

    keep = {"base": der["base"], "total": der["total"],
            "overheads": [{k: o[k] for k in ("name", "pct", "pert")} for o in der["overheads"]],
            "by_type": der["by_type"], "team": der["team"], "timeline": der["timeline"], "phases": der["phases"],
            "tasks": der["tasks"], "modules": der["modules"]}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"estimate": est, "calculator": keep}, f, indent=2, ensure_ascii=False)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
