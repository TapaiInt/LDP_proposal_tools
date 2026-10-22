#!/usr/bin/env python3
"""Write the OpenAPI document to api/openapi.json (import it into your agent platform).

    python api/export_openapi.py [--server-url https://tools.example.internal]
Re-run after changing a tool's parameters in integration/tool_api.py.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from api.app import create_app, load_config  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--server-url", default=os.environ.get("PUBLIC_BASE_URL", "https://tools.example.internal"))
a = ap.parse_args()
cfg = load_config({"ALLOW_NO_AUTH": "1", "PUBLIC_BASE_URL": a.server_url})
spec = create_app(cfg).openapi()
out = os.path.join(HERE, "openapi.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(spec, f, indent=2, ensure_ascii=False)
print(f"wrote {out}: {len([p for p in spec['paths'] if p.startswith('/v1/tools/')])} tool operations, server {a.server_url}")
