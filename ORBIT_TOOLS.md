# Orbit tool configuration — 13 tools

Base URL: `https://ldp-proposal-tools.onrender.com`

## Same for every tool

| Orbit step | Setting |
|---|---|
| 3 Source | **External API**, method `POST`, URL `<base>/v1/tools/<tool_name>` |
| Headers | `Content-Type: application/json` and `X-API-Key: <key only, not "presales:key">` (store as an Orbit secret) |
| Body | One JSON object built from the input fields. **Omit optional fields the user left empty** (do not send `""` or `null`). |
| 6 Output | Shape **JSON**, produced **Verbatim** (not AI summary), pass the whole body to the agent. |

Every response is HTTP 200 with `{"ok": true|false, ...}`. On failure the body is `{"ok": false, "error": "..."}`.
`run_id` and artifact names allow letters, digits, `_`, `.`, `-` only. Use `<Client>-<YYYYMMDD>` as `run_id`.
Parameter types: `*` = required. If Orbit has no boolean or number type, leave those optional fields out and the defaults apply.

---

## 1. save_artifact
Store text or JSON under a name; records its sha256. Names starting `estimation_pass`, `estimation_revision`, `reviewer_findings`, `scope_summary` are **immutable** (a second save fails).

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `name`* | text | e.g. `estimation_pass2.json` |
| `content` | text | The file text. For JSON, send the JSON as a string. **Exactly one of `content` / `json_value`.** |
| `json_value` | object | Only if Orbit has an object type. Do not send it together with `content`. |
| `overwrite` | boolean | Default false. Ignored for immutable names. |

Orbit tip: expose only `run_id`, `name`, `content`, `overwrite`. Sending an empty `content` together with `json_value` fails.

Output: `ok`, `name`, `sha256`, `bytes`, `saved_at`.

## 2. get_artifact
Read a text artifact in slices. Binary files (`.xlsx`, `.docx`, `.pdf`, `.png`, `.zip`) return metadata only.

| Input | Type |
|---|---|
| `run_id`* | text |
| `name`* | text |
| `offset` | integer (default 0) |
| `max_chars` | integer (default 20000) |

Output: `ok`, `name`, `offset`, `total_chars`, `truncated`, `text`. Binary: `ok`, `name`, `binary: true`, `bytes`, `sha256`.

## 3. list_artifacts
Input: `run_id`*.
Output: `ok`, `run_id`, `artifacts[]` of `{name, bytes, registered}`.

## 4. verify_artifacts
Re-hashes registered files; flags any raw agent output edited after saving.
Input: `run_id`*.
Output: `ok` (call succeeded), `verified` (true when nothing changed), `problems[]` of `{name, problem}`. Read `verified`, not just `ok`.

## 5. calc_estimate
The calculator: PERT, totals, overheads, by-type, team hours, timeline and 25 structural checks. Writes the derived artifact.

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `estimate`* | text | Artifact name of the estimator JSON, e.g. `estimation_pass2.json` |
| `previous` | text | Earlier estimate artifact, for a revision delta |
| `hours_per_fte_week` | number | Default 35. Leave out unless INT confirms another value. |
| `out` | text | Derived artifact name, default `estimation_derived.json` |
| `include_derived` | boolean | Default false (keeps the reply small) |

Output: `ok` (false when a blocking check fails), `derived_artifact`, `blocking_failures[]`, `advisory_failures[]`, `checks{passed,total}`, `task_count`, `base_pert_h`, `total_h{optimistic,pert,pessimistic,p80}`, `overheads[]`, `weeks`, `team[]`, `uncovered_requirement_items`, `inferred_tasks`, and `revision_delta` when `previous` is given.

## 6. ensemble_select
Picks the median of several estimator runs; copies it byte-for-byte to `select_as`; writes the derived file and a spread report. Not needed in the single-agent edition.

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `runs`* | array of text | At least 2 artifact names |
| `out` | text | Default `estimation_derived.json` |
| `report` | text | Default `ensemble_report.json` |
| `select_as` | text | Default `estimation_pass2.json` |

Output: `ok`, `selected`, `selected_as`, `spread_pct`, `spread_level`, `advice`, `flags`, `widest_modules[]`, `runs[]`.

## 7. prepare_review
Builds the reviewer's input: the estimate without the estimator's reasoning, plus calculator numbers.

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `estimate`* | text | e.g. `estimation_pass2.json` |
| `derived`* | text | e.g. `estimation_derived.json` |
| `out` | text | Default `review_input.json` |
| `include_content` | boolean | Send `true` so the JSON text comes back in `content` |

Output: `ok`, `artifact`, `bytes`, and `content` when requested.

## 8. build_workbook
Builds the `.xlsx` with live formulas and verifies totals independently.

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `estimate`* | text | Final estimate artifact |
| `derived`* | text | `estimation_derived.json` |
| `out_name`* | text | Must end `.xlsx`, e.g. `Estimation_Acme_V1.0.xlsx` |
| `client` | text | |
| `version` | text | Default `1.0` |
| `state` | text | `draft`, `delivery_reviewed` or `approved` (default `draft`) |
| `draft` | text | Comma-separated failed blocking check ids; stamps the workbook DRAFT |
| `sources` | text | Source document names |
| `clarifications` | array or text | Q&A list, or the name of a JSON artifact |
| `check` | boolean | Default true (independent total check) |

Output: `ok` (false on a total mismatch), `artifact`, `bytes`, `output`.

## 9. check_consistency
Runs the scripted X1–X15 checks. Needs `Proposal_*.md`, `Presales_Review_Notes_*.md`, `Estimation_*.xlsx`, the estimate and derived files already saved in the run.

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `forbid` | text | Comma-separated other client names that must not appear |
| `expose_hours` | boolean | Only if hours are intentionally in the proposal |

Output: `ok`, `failures[]`, `warnings[]`, `passed[]` (check ids). Also writes `consistency_report.json`.

## 10. hash_text
Input: `content`* (text). Output: `ok`, `sha256`, `chars`. Smoke test: `{"content":"abc"}` returns `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`.

## 11. get_module
Input: `name`* — one of `proposal_template`, `quality_gate`, `fault_tolerance`.
Output: `ok`, `name`, `text` (the module's instructions).

## 12. create_download_link
Time-limited link to a stored file that opens without an API key.

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `name`* | text | e.g. `Estimation_Acme_V1.0.xlsx` |
| `ttl_seconds` | integer | Default 900, min 30, max 86400 |

Output: `ok`, `name`, `url`, `expires_at`, `ttl_seconds`. The link uses `PUBLIC_BASE_URL`.

## 13. build_docx
Converts the client proposal markdown into a Word `.docx` in INT's proposal style (A4, Calibri, navy headings, cover page, version table, running header and footer with page numbers).

| Input | Type | Notes |
|---|---|---|
| `run_id`* | text | |
| `source`* | text | The proposal markdown artifact, e.g. `Proposal_Acme_Quotation_V1.0.md` (must end `.md`) |
| `out_name`* | text | Must end `.docx`, e.g. `Proposal_Acme_Quotation_V1.0.docx` |
| `version` | text | Shown in the page header, e.g. `V1.0`. Default: read from the cover page line `Version: V1.0` |

Output: `ok`, `artifact`, `bytes`, `output` (counts of headings, tables, list items). Then call `create_download_link` for the `.docx`.

---

## Which agent gets which tool

| Tool | Master | Estimator | Reviewer |
|---|---|---|---|
| save_artifact, get_artifact, list_artifacts, verify_artifacts | yes | save_artifact only | no |
| calc_estimate | yes | yes (self-check loop) | no |
| prepare_review, build_workbook, build_docx, check_consistency, get_module, create_download_link, hash_text | yes | no | no |
| ensemble_select | yes (only for ensemble 3) | no | no |

## Register in this order
1. `hash_text`, then `get_module` (smoke test)
2. `save_artifact`, `get_artifact`, `calc_estimate`
3. `prepare_review`, `build_workbook`, `build_docx`, `check_consistency`, `create_download_link`
4. `list_artifacts`, `verify_artifacts`, `ensemble_select`

---

# Orbit "Register API tool" form (mesh · integration)

This form sends **every key on every call** ("model fills" ticked = the model may overwrite the default). So an optional field you add is always sent. Add only the keys listed here, with exactly these defaults. Anything not listed keeps the server default.

## Fields that are the same for all 12 tools
| Field | Value |
|---|---|
| Tool name | the exact name below (the prompts call these names) |
| Slug | the form auto-prefixes it (`proposal_hash_text`). Edit it to equal the tool name if it allows; otherwise see "Slug" note below |
| Description | one or two sentences, what it does and when to call it (see the table). Replace the placeholder "Look up a CRM contact" |
| URL | `https://ldp-proposal-tools.onrender.com/v1/tools/<tool_name>` (the tool name must be at the end) |
| Method | **POST** (GET would send a query string; the API needs a JSON body) |
| Authentication | API key in a header, header name `X-API-Key`, secret = the key only (no `presales:`) |
| Static headers | `Content-Type: application/json` |
| Paths to keep | leave empty (whole response) |
| Response shape | optional, e.g. `{"ok": "boolean", "...": "..."}` (documentation only) |
| Max calls per turn | `0` (unlimited), or `40` as a safety cap |
| Timeout (ms) | `60000`; `120000` for `build_workbook` and `check_consistency` |

## Request parameters per tool (key = default, ✔ = model fills)
| Tool | Keys |
|---|---|
| `hash_text` | `content` = "" ✔ |
| `get_module` | `name` = "quality_gate" ✔ |
| `save_artifact` | `run_id` ✔, `name` ✔, `content` ✔, `overwrite` = false ✔ (see "Typed values") |
| `get_artifact` | `run_id` ✔, `name` ✔ |
| `list_artifacts` | `run_id` ✔ |
| `verify_artifacts` | `run_id` ✔ |
| `calc_estimate` | `run_id` ✔, `estimate` ✔, `previous` = "" ✔ (empty means no revision delta) |
| `prepare_review` | `run_id` ✔, `estimate` ✔, `derived` = "estimation_derived.json" ✔, `include_content` = true (not model-filled) |
| `build_workbook` | `run_id` ✔, `estimate` ✔, `derived` = "estimation_derived.json" ✔, `out_name` ✔, `client` ✔, `version` = "1.0" ✔, `state` = "draft" ✔, `draft` = "" ✔, `sources` = "" ✔, `clarifications` = "" ✔ |
| `check_consistency` | `run_id` ✔, `forbid` = "" ✔, `estimate` = "" ✔ (final estimate file name), `derived` = "estimation_derived.json" ✔ |
| `create_download_link` | `run_id` ✔, `name` ✔ |
| `build_docx` | `run_id` ✔, `source` ✔, `out_name` ✔, `version` = "" ✔ |
| `ensemble_select` | skip for now: it needs a list (`runs`), and a text-only form cannot send one. Not needed for ensemble 1 or the single-agent edition |

## Typed values
Orbit sends every value as a string (`"35"`, `"true"`, `"0"`). The server converts them to the schema's types (integers, numbers, booleans, JSON lists and objects, comma-separated lists) and ignores empty optional values, so the defaults apply. Needs the tool API version that contains `_coerce_args` in `integration/tool_api.py`; redeploy after pulling it.
Errors now name the failing file and line, and a malformed estimate (a list that holds text instead of objects) is reported with the exact path, e.g. `modules[1].tasks[0] must be an object`.

## clarifications for build_workbook
A text-only form cannot send a list. Before calling `build_workbook`, the master saves the Q&A list with `save_artifact` as `clarifications.json` (content = the JSON text) and passes `clarifications` = `clarifications.json`.

## Size cap
"Paths to keep" empty = whole response but **size-capped**. Large replies, mainly `prepare_review` with `include_content` and `get_artifact`, may be cut. Find the cap in the live test. If `prepare_review` content is cut, have the reviewer read `review_input.json` in slices with `get_artifact` (`offset`) instead.

## Slug
If the agent sees `proposal_hash_text` instead of `hash_text`, the prompts' tool names will not match. Either set the slug to the exact tool name, or add a line to the master prompt: "tool names carry the prefix `proposal_`".

## Descriptions to paste
| Tool | Description |
|---|---|
| `hash_text` | sha256 of a string. Use as a connectivity check. |
| `get_module` | Load a master instruction module: proposal_template (start of proposal construction), quality_gate (finalisation), fault_tolerance (exceptional inputs only). |
| `save_artifact` | Store text or JSON as a named file in the run folder and record its sha256. Names starting estimation_pass, estimation_revision, reviewer_findings, scope_summary are immutable. |
| `get_artifact` | Read a stored text file. Binary files return metadata only. |
| `list_artifacts` | List the files stored for a run. |
| `verify_artifacts` | Re-hash stored files and report any raw agent output changed after saving. Read `verified`. |
| `calc_estimate` | Deterministic calculator: PERT, totals, overheads, team hours, timeline and 25 structural checks for an estimate file. Use after every estimate; `previous` adds a revision delta. |
| `prepare_review` | Build the reviewer input: the estimate without the estimator's reasoning, plus calculator numbers. |
| `build_workbook` | Build the .xlsx estimation workbook with live formulas and verify its totals. |
| `check_consistency` | Run scripted consistency checks across the proposal, review notes, workbook and estimate files in the run. |
| `create_download_link` | Create a time-limited download link for a stored file, usable without an API key. |
| `build_docx` | Convert the client proposal markdown (Proposal_*.md) into a Word .docx in INT's proposal style. Call after the proposal text is final and the consistency checks have run. |
