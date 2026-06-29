---
name: api-schema-extraction
description: Extract the schema of a LIVE API into a compact extraction map that drives the Bronze→Silver→Gold medallion. Reads the running mock OmniHR + Harvest API (GET /openapi.json plus a sample page per endpoint), identifies each entity and its grain, maps every JSON field to a Snowflake column type and its JSON path (including NESTED paths like position.name and user.id), flags primary/foreign keys, and writes build/extraction_map.json — the input the medallion-build skill turns into Bronze/Silver/Gold SQL. This is step ① of the DEMO (live mock_api) path. Use when the presenter starts the live medallion demo on the DEMO connection (sevenpeaks_partner_demo).
tools:
- read_file
- write_file
- run_shell_command
---

# When to Use

- The presenter is running the **DEMO path** (live mock API + External Access) on the
  `sevenpeaks_partner_demo` connection and wants CoCo to **extract the API schema live**, then build the
  medallion from it — instead of running the prebuilt `src/*.sql` by hand.
- The mock OmniHR + Harvest API is up and reachable over its HTTPS tunnel
  (`examples/hris_people/deployed_app/mock_api/serve_eai.sh start`).
- Keywords: extract the API, schema, OpenAPI, endpoints, OmniHR, Harvest, "build the medallion from the API",
  Bronze, live extract, DEMO path.

This skill **only** produces `build/extraction_map.json`. It does NOT write SQL or touch Snowflake — the
**`medallion-build`** skill (step ②) consumes the map and authors Bronze/Silver/Gold SQL for your review.
The **7ptrial** (trial / no-EAI) path skips this skill entirely and uses `trial-seed-bronze` instead.

# Prerequisites

1. **The mock API is reachable.** The presenter ran `mock_api/serve_eai.sh start`, which prints the tunnel
   URL (e.g. `https://<you>.ngrok-free.app`). Confirm `GET <url>/` returns the endpoint index and
   `GET <url>/openapi.json` returns the OpenAPI document.
2. **A build dir.** Generated artifacts live in `examples/hris_people/deployed_app/build/` (git-ignored). Create it if missing.
3. **The golden reference (optional, for sanity-checking).** The hand-built demo's authoritative shapes are
   `src/02_bronze.sql` (the 33-endpoint registry) and `src/03_silver.sql` (typed tables + the nested
   field-path map). Use them to confirm your extraction matches the known-good schema — but extract from the
   **live API**, do not copy these files.

# Workflows

## 1. Read the live API surface

> **Fetch with `curl` (raw HTTP via `run_shell_command`) — NOT a web-page / "read this URL" tool, and NOT
> `localhost`.** These endpoints return **JSON**, which an HTML content-reader mangles or refuses; and a free
> `*.ngrok-free.*` domain serves an HTML browser-warning interstitial to browser-like clients. Always send the
> `ngrok-skip-browser-warning` header + a non-browser `User-Agent` (the same trick `SP_INGEST_BRONZE` uses) so
> you get the JSON body, not HTML. Extract from the **live tunnel URL**, not localhost — localhost samples
> don't demonstrate the live extraction.

```bash
BASE="https://<your-tunnel-host>"        # the live ngrok/cloudflare URL serve_eai.sh printed (NOT localhost)
H=(-H 'ngrok-skip-browser-warning: true' -H 'User-Agent: cortex-extract')
curl -s "${H[@]}" "$BASE/openapi.json" > build/openapi.json   # the full schema (JSON)
curl -s "${H[@]}" "$BASE/"                                      # endpoint index + row counts
```

- The mock API exposes **33 endpoints, one per entity** — 18 OmniHR (`/api/v1/...`, DRF envelope
  `{count,next,previous,results}`) and 15 Harvest (`/v2/...`, envelope `{<resource>:[...], pagination}`).
- **If a fetch still returns HTML** (an interstitial, or the read-tool insists on parsing it as a page),
  either switch to a Cloudflare quick tunnel (`serve_eai.sh --cloudflare`, no interstitial) **or** fall back
  to **landing a sample into Bronze first** (a one-page `SP_INGEST_BRONZE` call — it sends the skip header
  through Snowflake's egress) and inspect `SELECT PAYLOAD FROM BRONZE.<t> LIMIT 1`; the VARIANT *is* the raw
  schema. Either source yields the same map.

## 2. Pull one sample page per endpoint → see the real JSON shape

```bash
curl -s "${H[@]}" "$BASE/api/v1/employees?page=1&page_size=3"   # OmniHR, NESTED headline resource
curl -s "${H[@]}" "$BASE/v2/time_entries?per_page=3"            # Harvest, NESTED headline resource
```

Most endpoints are **flat snake_case**. Two headline resources are **nested** so the
"raw nested JSON → flatten into Silver" step is visible:
- `employees`: `position.name`, `department.name`, `work_location.name`, `reporting_manager.id`, `system_id`.
- `time_entries`: `user.id`, `project.id`, `task.id`, `billable`.

## 3. Identify entity, grain, and the envelope per endpoint

For each endpoint record: `source` (omnihr/harvest), `api_path`, `table` (UPPERCASE), one-line `grain`, and
the `envelope` (`results` for OmniHR, the resource key for Harvest, or a bare array). The element inside the
list is **one row** of that table.

## 4. Map every field → Snowflake type + JSON path

For each leaf field emit a column: `{ name (UPPERCASE), type, json_path, pk?, fk? }`.

| JSON value | Snowflake `type` | Notes |
|---|---|---|
| id / primary key | `NUMBER(38,0)` | set `"pk": true` |
| foreign key (e.g. `user.id`) | match parent pk type | set `"fk": "<TABLE>"`; `json_path` is the nested path |
| short code / status / category | `VARCHAR(20..100)` | |
| name / free text | `VARCHAR(80..200)` | |
| email | `VARCHAR(150)` | |
| integer count | `NUMBER(38,0)` | |
| money / rate | `NUMBER(p,s)` (e.g. `NUMBER(12,2)`) | |
| decimal hours | `NUMBER(5,2)` | |
| boolean | `BOOLEAN` | |
| ISO date | `DATE` | |
| ISO datetime | `TIMESTAMP_NTZ` | |

- **`json_path`** is `lower(column)` for flat endpoints; for the nested ones use the dotted path
  (`position.name`, `user.id`). This is exactly the OmniHR/Harvest → warehouse lineage that becomes the
  Silver field-map. Record it even when it equals `lower(column)` — the map is the lineage.
- Flag foreign keys from name + nesting (`user.id` on `time_entries` → `EMPLOYEES`; `*_ID` columns).

## 5. Write build/extraction_map.json and hand off

Shape (one object per endpoint):

```json
{
  "extracted_from": "https://<tunnel-host>",
  "tables": [
    {
      "source": "omnihr", "api_path": "/api/v1/employees", "table": "EMPLOYEES",
      "grain": "one row per employee", "envelope": "results", "nested": true,
      "columns": [
        { "name": "EMPLOYEE_ID", "type": "NUMBER(38,0)", "json_path": "id", "pk": true },
        { "name": "EMAIL", "type": "VARCHAR(150)", "json_path": "work_email" },
        { "name": "TITLE", "type": "VARCHAR(150)", "json_path": "position.name" },
        { "name": "MANAGER_ID", "type": "NUMBER(38,0)", "json_path": "reporting_manager.id", "fk": "EMPLOYEES" }
      ]
    }
  ]
}
```

Print a short summary (N endpoints, which are nested, total columns) and tell the presenter the map is ready
for **`medallion-build`** (step ②). See `references/field_path_extraction.md` for the nested-path walkthrough.

# Best Practices

- **Extract from the live API, not the reference SQL.** The point of the DEMO is showing CoCo read a real
  API. Use `src/02_bronze.sql` / `src/03_silver.sql` only to confirm you landed the same 33 tables.
- **UPPERCASE** table/column names; keep `json_path` in the API's original casing (lineage).
- **Always record `json_path`** — flat or nested. It is the single source of the Silver flatten.
- **Find the foreign keys.** A coherent medallion needs `TIME_ENTRIES.EMPLOYEE_ID → EMPLOYEES`,
  `PROJECT_ID → PROJECTS`, etc. Infer them from nested `*.id` and `*_ID` columns.
- **Don't invent fields.** Map only what `/openapi.json` and the sample pages show.
- **Stop at the map.** Authoring SQL and running it (with review hooks) is `medallion-build`'s job.

# Examples

## Example 1: Start the live demo

Presenter: "The API is up — extract the schema and let's build the medallion." (on `sevenpeaks_partner_demo`)

CoCo: curls `/openapi.json` + a sample page for each of the 33 endpoints, identifies `EMPLOYEES`
(grain: one employee; nested) and `TIME_ENTRIES` (nested) plus 31 flat entities, maps each field to a type +
`json_path` (capturing `position.name`, `user.id`), flags PKs/FKs, writes `build/extraction_map.json`, and
reports "33 endpoints (2 nested), 18 OmniHR + 15 Harvest — ready for medallion-build."

## Example 2: Agent can't reach the tunnel

CoCo lands a single sample page into `BRONZE.EMPLOYEES` via `SP_INGEST_BRONZE`, inspects
`SELECT PAYLOAD FROM BRONZE.EMPLOYEES LIMIT 1`, derives the nested field paths from the VARIANT, and builds
the same extraction map from the landed raw JSON.

# References

- `references/field_path_extraction.md` — the nested-JSON → Silver field-path walkthrough (the employees /
  time_entries headline resources) and the JSON→Snowflake type rules in full.
