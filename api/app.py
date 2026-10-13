"""HTTP API for the v4 tool layer (FastAPI).

Every tool is a POST endpoint:  POST /v1/tools/<tool_name>  with the tool's arguments as the JSON body.
Responses are always HTTP 200 with {"ok": true|false, ...} for tool-level results, so agent platforms that hide
the body of non-2xx responses still show the tool's error message. Protocol errors use normal HTTP codes:
401 bad or missing key, 413 body too large, 422 body is not a JSON object.

Auth: header `X-API-Key: <key>` or `Authorization: Bearer <key>`. Each key belongs to a tenant; the server prefixes
every run_id with the tenant, so tenants can never read each other's artifacts. Responses show the run_id you sent.

Also: GET /health (no auth), GET /v1/manifest, GET /v1/runs/<run>/artifacts[/<name>], POST /v1/tools/create_download_link
(time-limited signed URL for the workbook/proposal) and GET /d/<token> (the download itself; no key needed).

Run:  uvicorn api.app:create_app --factory --host 0.0.0.0 --port 8080 --workers 2      (from the v4 folder)
Environment: API_KEYS="tenantA:key...,tenantB:key..." (keys >= 16 chars) | LINK_SECRET | PUBLIC_BASE_URL | ARTIFACT_ROOT |
             MAX_BODY_BYTES (default 5 MB) | LINK_TTL_SECONDS (default 900, max 86400) | ALLOW_NO_AUTH=1 (development only)
"""
import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import sys
import time
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "integration"))
import tool_api as ta  # noqa: E402

VERSION = "v4.1"
TENANT_RE = re.compile(r"[A-Za-z0-9-]{1,20}")
log = logging.getLogger("presales.api")
if not log.handlers:                      # structured request log; never contains arguments, content or download tokens
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

mimetypes.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")
mimetypes.add_type("text/markdown", ".md")

DOWNLOAD_TOOL = {
    "description": "Create a time-limited download link for a stored artifact (for example the workbook or proposal) that the end user can open without an API key.",
    "parameters": {"type": "object", "additionalProperties": False, "required": ["run_id", "name"], "properties": {
        "run_id": {"type": "string", "description": "Run identifier"},
        "name": {"type": "string", "description": "Artifact name, e.g. Estimation_Client_V1.0.xlsx"},
        "ttl_seconds": {"type": "integer", "description": "Link lifetime in seconds (default and maximum set by the server)"}}},
}


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def load_config(env=None):
    env = os.environ if env is None else env
    keys = {}
    for part in filter(None, (p.strip() for p in env.get("API_KEYS", "").split(","))):
        tenant, _, key = part.partition(":")
        if not TENANT_RE.fullmatch(tenant) or len(key) < 16:
            raise RuntimeError("API_KEYS entries must look like tenant:key with a tenant of letters, digits or '-' (max 20) and a key of at least 16 characters")
        keys[key] = tenant
    allow = env.get("ALLOW_NO_AUTH") == "1"
    if not keys and not allow:
        raise RuntimeError("API_KEYS is not set. Set API_KEYS=tenant:key,... (or ALLOW_NO_AUTH=1 for local development only)")
    secret = env.get("LINK_SECRET")
    if not secret:
        if not allow:
            raise RuntimeError("LINK_SECRET is not set (needed to sign download links; use a long random string, the same on every worker)")
        secret = secrets.token_hex(32)
    return {"api_keys": keys, "allow_no_auth": allow, "link_secret": secret,
            "public_base_url": env.get("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/"),
            "max_body_bytes": int(env.get("MAX_BODY_BYTES", 5 * 1024 * 1024)),
            "link_ttl": int(env.get("LINK_TTL_SECONDS", 900)), "max_link_ttl": 86400}


def create_app(config: Optional[Dict[str, Any]] = None) -> FastAPI:
    cfg = config or load_config()
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Tenant API key")
    bearer = HTTPBearer(auto_error=False, description="Tenant API key as a bearer token")
    app = FastAPI(title="Presales estimation tools", version=VERSION,
                  description="Tool endpoints for the proposal and estimation agents. See v4/integration/IMPLEMENTATION_GUIDE.md.",
                  servers=[{"url": cfg["public_base_url"]}])

    def auth(key: Optional[str] = Security(api_key_header), cred: Optional[HTTPAuthorizationCredentials] = Security(bearer)) -> str:
        supplied = key or (cred.credentials if cred else None)
        if cfg["allow_no_auth"] and not cfg["api_keys"]:
            return "dev"
        if supplied:
            for k, tenant in cfg["api_keys"].items():
                if hmac.compare_digest(supplied.encode(), k.encode()):
                    return tenant
        raise HTTPException(status_code=401, detail="missing or invalid API key", headers={"WWW-Authenticate": "Bearer"})

    def internal(tenant: str, run_id: Any) -> str:
        if not isinstance(run_id, str) or not ta.RUN_RE.fullmatch(run_id):
            raise ta.ToolError(f"invalid run_id {run_id!r} (letters, digits, _ . - only; max 120)")
        return f"{tenant}__{run_id}"

    def externalize(obj: Any, internal_id: Optional[str], external_id: Optional[str]) -> Any:
        if internal_id is None:
            return obj
        if isinstance(obj, str):
            return obj.replace(internal_id, external_id)
        if isinstance(obj, list):
            return [externalize(x, internal_id, external_id) for x in obj]
        if isinstance(obj, dict):
            return {k: externalize(v, internal_id, external_id) for k, v in obj.items()}
        return obj

    async def json_body(request: Request) -> Dict[str, Any]:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cfg["max_body_bytes"]:
            raise HTTPException(status_code=413, detail=f"body larger than {cfg['max_body_bytes']} bytes")
        raw = await request.body()
        if len(raw) > cfg["max_body_bytes"]:
            raise HTTPException(status_code=413, detail=f"body larger than {cfg['max_body_bytes']} bytes")
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            raise HTTPException(status_code=422, detail="body must be a JSON object")
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="body must be a JSON object")
        return body

    # ---------------- signed download links
    def sign(payload: Dict[str, Any]) -> str:
        p = _b64(json.dumps(payload, separators=(",", ":")).encode())
        sig = _b64(hmac.new(cfg["link_secret"].encode(), p.encode(), hashlib.sha256).digest())
        return f"{p}.{sig}"

    def verify(token: str) -> Optional[Dict[str, Any]]:
        try:
            p, sig = token.split(".")
            good = _b64(hmac.new(cfg["link_secret"].encode(), p.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, good):
                return None
            payload = json.loads(_unb64(p))
            return payload if payload["e"] >= time.time() else None
        except Exception:
            return None

    def create_download_link(tenant: str, run_id: Any, name: Any, ttl_seconds: Any = None) -> Dict[str, Any]:
        ta._path(internal(tenant, run_id), name, must_exist=True)
        ttl = int(ttl_seconds) if ttl_seconds else cfg["link_ttl"]
        ttl = max(30, min(ttl, cfg["max_link_ttl"]))
        exp = int(time.time()) + ttl
        token = sign({"t": tenant, "r": run_id, "n": name, "e": exp})
        return {"ok": True, "name": name, "url": f"{cfg['public_base_url']}/d/{token}", "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(exp)), "ttl_seconds": ttl}

    # ---------------- tool endpoints (one per tool; OpenAPI carries each tool's real parameter schema)
    def make_endpoint(name: str):
        async def endpoint(request: Request, tenant: str = Depends(auth)):
            t0 = time.time()
            body = await json_body(request)
            ext_run = body.get("run_id")
            try:
                if name == "create_download_link":
                    result = await run_in_threadpool(create_download_link, tenant, body.get("run_id"), body.get("name"), body.get("ttl_seconds"))
                    int_run = None
                else:
                    args = dict(body)
                    int_run = internal(tenant, ext_run) if "run_id" in args else None
                    if int_run:
                        args["run_id"] = int_run
                    result = await run_in_threadpool(ta.call, name, args)
            except ta.ToolError as e:
                result, int_run = {"ok": False, "error": str(e)}, None
            result = externalize(result, int_run, ext_run)
            log.info(json.dumps({"tool": name, "tenant": tenant, "run": ext_run, "ok": bool(result.get("ok")), "ms": int((time.time() - t0) * 1000)}))
            return JSONResponse(result)
        endpoint.__name__ = name
        return endpoint

    all_tools = dict(ta.TOOLS)
    all_tools["create_download_link"] = (None, DOWNLOAD_TOOL["description"], DOWNLOAD_TOOL["parameters"])
    for tool_name, (_, desc, schema) in all_tools.items():
        app.add_api_route(
            f"/v1/tools/{tool_name}", make_endpoint(tool_name), methods=["POST"], name=tool_name, operation_id=tool_name,
            summary=tool_name, description=desc, tags=["tools"],
            responses={200: {"description": "Tool result. Always 200; check `ok`.", "content": {"application/json": {"schema": {
                "type": "object", "properties": {"ok": {"type": "boolean"}, "error": {"type": "string"}}, "required": ["ok"], "additionalProperties": True}}}}},
            openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}})

    # ---------------- other routes
    @app.get("/health", tags=["ops"], include_in_schema=False)
    def health():
        try:
            os.makedirs(ta._root(), exist_ok=True)
            probe = os.path.join(ta._root(), f".probe-{os.getpid()}")
            open(probe, "w").close()
            os.remove(probe)
            writable = True
        except OSError:
            writable = False
        return JSONResponse({"status": "ok" if writable else "degraded", "version": VERSION, "tools": len(all_tools), "artifact_root_writable": writable},
                            status_code=200 if writable else 503)

    @app.get("/v1/manifest", tags=["ops"])
    def manifest(tenant: str = Depends(auth)):
        m = ta.manifest()
        m["tools"].append({"name": "create_download_link", "description": DOWNLOAD_TOOL["description"], "parameters": DOWNLOAD_TOOL["parameters"]})
        return m

    @app.get("/v1/runs/{run_id}/artifacts", tags=["artifacts"])
    def list_run(run_id: str, tenant: str = Depends(auth)):
        try:
            res = ta.list_artifacts(internal(tenant, run_id))
        except ta.ToolError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return externalize(res, internal(tenant, run_id), run_id)

    @app.get("/v1/runs/{run_id}/artifacts/{name}", tags=["artifacts"])
    def download(run_id: str, name: str, tenant: str = Depends(auth)):
        try:
            path = ta._path(internal(tenant, run_id), name, must_exist=True)
        except ta.ToolError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return FileResponse(path, filename=name, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream")

    @app.get("/d/{token}", include_in_schema=False)
    def signed_download(token: str):
        p = verify(token)
        if not p:
            log.info(json.dumps({"download": None, "ok": False}))
            raise HTTPException(status_code=404, detail="link invalid or expired")
        try:
            path = ta._path(f"{p['t']}__{p['r']}", p["n"], must_exist=True)
        except ta.ToolError:
            log.info(json.dumps({"download": p["n"], "tenant": p["t"], "run": p["r"], "ok": False}))
            raise HTTPException(status_code=404, detail="link invalid or expired")
        log.info(json.dumps({"download": p["n"], "tenant": p["t"], "run": p["r"], "ok": True}))
        return FileResponse(path, filename=p["n"], media_type=mimetypes.guess_type(p["n"])[0] or "application/octet-stream",
                            headers={"Cache-Control": "no-store"})

    return app
