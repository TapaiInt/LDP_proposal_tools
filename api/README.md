# Tool API (HTTP)

The v4 tool layer as a small HTTP service, for agent platforms whose tools can only call HTTP APIs. Setup and platform wiring are in `../integration/IMPLEMENTATION_GUIDE.md`; this page is the reference.

## Quick start

```bash
cd v4
cp api/.env.example api/.env                      # set API_KEYS, LINK_SECRET, PUBLIC_BASE_URL
docker compose -f api/docker-compose.yml up -d --build
python api/e2e_check.py --base-url https://<host> --api-key <key>      # expect: OK: API works end to end
```
Local self-test without a server of your own: `python api/e2e_check.py --spawn`.

## Endpoints

| Method and path | Auth | Purpose |
|---|---|---|
| `POST /v1/tools/<tool_name>` | key | Run a tool; body = the tool's arguments (JSON object). 12 tools, see below |
| `GET /v1/manifest` | key | Tool names, descriptions and parameter schemas |
| `GET /v1/runs/<run_id>/artifacts` | key | List a run's artifacts |
| `GET /v1/runs/<run_id>/artifacts/<name>` | key | Download an artifact |
| `GET /d/<token>` | none (signed) | Download via a link from `create_download_link` |
| `GET /health` | none | `{"status":"ok","artifact_root_writable":true,...}`; 503 when the store is not writable |
| `GET /openapi.json`, `/docs` | none | OpenAPI document and interactive docs |

**Tools:** `save_artifact`, `get_artifact`, `list_artifacts`, `verify_artifacts`, `calc_estimate`, `ensemble_select`, `prepare_review`, `build_workbook`, `check_consistency`, `get_module`, `create_download_link`, `hash_text`.

## Conventions

- **Auth:** `X-API-Key: <key>` or `Authorization: Bearer <key>`. Each key belongs to one tenant. The service prefixes every `run_id` with the tenant internally and shows you the `run_id` you sent, so tenants cannot reach each other's files.
- **Responses:** tool calls always return **HTTP 200** with `{"ok": true|false, ...}`; failures carry `"error"`. Protocol errors: 401 (key), 413 (body over `MAX_BODY_BYTES`), 422 (body is not a JSON object).
- **Artifacts, not arguments:** save a large JSON once (`save_artifact`), then pass its name. Tools return compact summaries. Raw agent outputs (`estimation_pass*`, `estimation_revision*`, `reviewer_findings*`, `scope_summary*`) are immutable and hash-registered; `verify_artifacts` detects any change.
- **Concurrency:** safe for parallel saves (ensemble runs) and several workers or replicas on one shared volume: files are created exclusively, replaced atomically, and the hash registry is one small file per artifact.

## Examples

```bash
H='-H Content-Type:application/json -H X-API-Key:YOUR_KEY'
B=https://tools.example.internal

curl $H -d '{"run_id":"acme-20261013","name":"estimation_pass2.json","json_value":{...}}' $B/v1/tools/save_artifact
curl $H -d '{"run_id":"acme-20261013","estimate":"estimation_pass2.json"}'              $B/v1/tools/calc_estimate
curl $H -d '{"run_id":"acme-20261013","estimate":"estimation_pass2.json","derived":"estimation_derived.json","out_name":"Estimation_Acme_V1.0.xlsx","client":"Acme"}' $B/v1/tools/build_workbook
curl $H -d '{"run_id":"acme-20261013","name":"Estimation_Acme_V1.0.xlsx","ttl_seconds":600}' $B/v1/tools/create_download_link
```

## Configuration (environment)

| Variable | Required | Meaning |
|---|---|---|
| `API_KEYS` | yes | `tenant:key,tenant2:key2`; tenant = letters, digits, `-` (max 20); key at least 16 characters |
| `LINK_SECRET` | yes | Signs download links; identical on every worker and replica |
| `PUBLIC_BASE_URL` | recommended | Used in download links and the OpenAPI `servers` entry (default `http://localhost:8080`) |
| `ARTIFACT_ROOT` | no | Artifact folder (default `./artifacts`; `/data/artifacts` in the image) |
| `MAX_BODY_BYTES` | no | Request body limit (default 5 MB) |
| `LINK_TTL_SECONDS` | no | Default link lifetime (900; maximum 86,400) |
| `ALLOW_NO_AUTH=1` | no | **Development only**: no key needed, random link secret |

The service refuses to start without `API_KEYS` and `LINK_SECRET` (unless `ALLOW_NO_AUTH=1`).

## Operations

- **Logs:** one JSON line per request (`tool`, `tenant`, `run`, `ok`, `ms`; downloads log the file name). Arguments, artifact content and download tokens are never logged; the uvicorn access log is off for that reason.
- **Scaling:** add workers (`--workers`) or replicas behind a load balancer; all must mount the same artifact volume and share `LINK_SECRET`. The calculator and workbook tools are CPU-light (typically under a second).
- **Security:** run behind TLS; restrict network access to the platform; one key per tenant; rotate keys by adding the new `tenant:key` and removing the old one (comma-separated list); the container runs as a non-root user with a read-only root filesystem.
- **Retention:** artifacts contain client documents. Define how long runs are kept and delete old `ARTIFACT_ROOT/<tenant>__<run_id>` folders accordingly.
- **Updating the OpenAPI file:** `python api/export_openapi.py --server-url https://<host>` after changing any tool parameter in `integration/tool_api.py`.

## Tests

`python -m unittest tests.test_api -v` (in-process, 14 tests: auth, isolation, signed links, limits, OpenAPI, concurrency) and `python api/e2e_check.py --spawn` (real HTTP, two workers).
