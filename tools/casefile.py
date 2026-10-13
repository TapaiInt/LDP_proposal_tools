#!/usr/bin/env python3
"""Case file for one opportunity: the single place that survives context resets.

Commands:
    casefile.py init   <case.json> --client NAME [--source FILE ...] [--kind raw_requirement|business_proposal]
    casefile.py set    <case.json> KEY VALUE        (dotted key, VALUE parsed as JSON when possible)
    casefile.py log-qa <case.json> --id Q1 --question TEXT --asked-by master|estimation-agent --answer TEXT [--effect TEXT]
    casefile.py register <case.json> --name NAME --file PATH   (records sha256 so later edits are detectable)
    casefile.py verify <case.json>                              (re-hash registered files; exit 1 on mismatch)
    casefile.py show   <case.json>
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

STATES = ("draft", "delivery_reviewed", "approved")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, d):
    d["updated"] = now()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("case")
    s.add_argument("--client", required=True)
    s.add_argument("--source", nargs="*", default=[])
    s.add_argument("--kind", default="raw_requirement")
    s = sub.add_parser("set")
    s.add_argument("case")
    s.add_argument("key")
    s.add_argument("value")
    s = sub.add_parser("log-qa")
    s.add_argument("case")
    for k in ("--id", "--question", "--asked-by", "--answer"):
        s.add_argument(k, required=True)
    s.add_argument("--effect", default=None)
    s = sub.add_parser("register")
    s.add_argument("case")
    s.add_argument("--name", required=True)
    s.add_argument("--file", required=True)
    s = sub.add_parser("verify")
    s.add_argument("case")
    s = sub.add_parser("show")
    s.add_argument("case")
    a = ap.parse_args()

    if a.cmd == "init":
        d = {"client": a.client, "created": now(), "input_kind": a.kind, "source_files": a.source,
             "switches": {}, "scope_confirmed": False, "estimate_state": "draft", "version": "1.0",
             "technology": {"classification": "to_be_confirmed", "detail": None},
             "discovery": {"qa_log": []}, "files": {}, "decisions": [], "notes": []}
        save(a.case, d)
        print("initialised", a.case)
        return
    d = load(a.case)
    if a.cmd == "set":
        try:
            val = json.loads(a.value)
        except ValueError:
            val = a.value
        if a.key == "estimate_state" and val not in STATES:
            sys.exit(f"estimate_state must be one of {STATES}")
        node = d
        parts = a.key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
        save(a.case, d)
    elif a.cmd == "log-qa":
        d["discovery"]["qa_log"].append({"id": a.id, "question": a.question, "asked_by": a.asked_by,
                                         "answer": a.answer, "effect": a.effect, "at": now()})
        save(a.case, d)
    elif a.cmd == "register":
        d["files"][a.name] = {"path": a.file, "sha256": sha(a.file), "bytes": os.path.getsize(a.file), "registered_at": now()}
        save(a.case, d)
        print(a.name, d["files"][a.name]["sha256"][:12])
    elif a.cmd == "verify":
        bad = []
        for name, f in d["files"].items():
            if not os.path.exists(f["path"]):
                bad.append(f"{name}: missing {f['path']}")
            elif sha(f["path"]) != f["sha256"]:
                bad.append(f"{name}: changed since registration")
        print("OK: all registered files unchanged" if not bad else "\n".join(bad))
        sys.exit(1 if bad else 0)
    elif a.cmd == "show":
        print(json.dumps(d, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
