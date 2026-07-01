---
name: api-schema-extraction
description: Extract a source schema into a compact extraction map that drives the Bronze→Silver→Gold medallion. Works on BOTH the live mock_api path (reads the running OmniHR + Harvest API — GET /openapi.json plus a sample page per endpoint) AND the offline seeder path (reads the already-seeded Bronze VARIANT / schema_spec.json, no tunnel). Identifies each entity and its grain, maps every JSON field to a Snowflake column type and its JSON path (including NESTED paths like position.name and user.id), flags primary/foreign keys, and writes build/extraction_map.json — the input the medallion-build skill turns into Bronze/Silver/Gold SQL. This is step ① of the medallion demo. Always delegates the map build to a dedicated extraction subagent.
tools:
- read_file
- write_file
- run_shell_command
- task
- ask_user_question
---

# When to Use

- The user wants Cortex Code to **extract the schema** and then build the medallion from it — instead of
  running the prebuilt `src/*.sql` by hand. Runs on **either path**:
  - **Live-API path** (account can create an External Access Integration + the mock OmniHR + Harvest API is up
    over its HTTPS tunnel, `examples/hris_people/deployed_app/mock_api/serve_eai.sh start`) — extract live.
  - **Offline seeder path** (trial account, no EAI): Bronze has already been seeded by `trial-seed-bronze`
    (`seed_bronze.sh`); extract the same map from the seeded Bronze VARIANT / `schema_spec.json`.
- Keywords: extract the schema, OpenAPI, endpoints, OmniHR, Harvest, "build the medallion from the API",
  Bronze, live extract, offline extract, seeder path, extraction map.

This skill **only** produces `build/extraction_map.json`. It does NOT write SQL or touch Snowflake state — the
**`medallion-build`** skill (step ②) consumes the map and authors Bronze/Silver/Gold SQL for your review.
Run everything on the **user's currently-active connection**; for any `snow` CLI step use their default
connection (shown as `<your-connection>`) — never assume a specific account.

# The dedicated extraction subagent (always delegate)

**Do not build the map inline.** This skill ALWAYS delegates the map build to a dedicated `Task` subagent
(`subagent_type: generalPurpose`) so the step is deterministic and keeps the main context lean. The subagent
reads the source, maps every field, writes `build/extraction_map.json`, and reports a short summary. It has
two modes:

- **live** — a tunnel `BASE` URL is available: it curls `/openapi.json` + a sample page per endpoint,
  cross-checked with `src/02_bronze.sql` + `src/03_silver.sql`.
- **offline** — no tunnel; Bronze already seeded: it reads `SELECT PAYLOAD FROM BRONZE.<t> LIMIT 1` per table
  + `src/02_bronze.sql` + `src/03_silver.sql` (and/or `schema_spec.json`).

The full, ready-to-use subagent prompt (with the `MODE` switch, source list, output contract, and report
checklist) is in **`references/extraction_subagent.md`** — invoke the `task` tool with that prompt, filling in
`MODE` and (for live) the `BASE` URL. Both modes emit the **identical** map shape.

# Prerequisites

1. **Pick the mode.** If the mock API is reachable over a tunnel → **live**. If you're on a trial/offline
   account and `seed_bronze.sh` has loaded Bronze → **offline**. If unsure which, ask via `ask_user_question`.
2. **A build dir.** Generated artifacts live in `examples/hris_people/deployed_app/build/` (git-ignored).
   Create it if missing.
3. **Source is available for the chosen mode:**
   - live: `GET <tunnel>/` returns the endpoint index and `GET <tunnel>/openapi.json` returns the OpenAPI doc.
   - offline: `SELECT PAYLOAD FROM DEMO_EMPLOYEE_APP.BRONZE.EMPLOYEES LIMIT 1` returns raw JSON (Bronze seeded),
     or fall back to `examples/hris_people/schema_spec.json`.
4. **The golden reference** (both modes, for exact names/types): `src/02_bronze.sql` (the 33-endpoint registry)
   and `src/03_silver.sql` (typed tables + the nested field-path map). Confirm the extraction matches these.

# Workflows

## 0. Delegate to the extraction subagent (required)

Invoke the `task` tool once, `subagent_type: generalPurpose`, with the prompt in
`references/extraction_subagent.md`. Set `MODE=live` (and `BASE=<tunnel url>`) or `MODE=offline`. When it
returns, validate the JSON yourself (see step 5) before handing off.

## 1. (live mode) Read the live API surface

> **The subagent fetches with `curl` (raw HTTP) — NOT a web-page reader, and NOT `localhost`.** These
> endpoints return **JSON**, which an HTML reader mangles; and a free `*.ngrok-free.*` domain serves an HTML
> interstitial to browser-like clients. Always send `ngrok-skip-browser-warning: true` + a non-browser
> `User-Agent`. Extract from the **live tunnel URL**, not localhost.

```bash
BASE="https://<your-tunnel-host>"        # the live ngrok/cloudflare URL serve_eai.sh printed (NOT localhost)
H=(-H 'ngrok-skip-browser-warning: true' -H 'User-Agent: cortex-extract')
curl -s "${H[@]}" "$BASE/openapi.json" > build/openapi.json   # the full schema (JSON)
curl -s "${H[@]}" "$BASE/"                                      # endpoint index + row counts
```

- **33 endpoints, one per entity** — 18 OmniHR (`/api/v1/...`, DRF envelope `{count,next,previous,results}`)
  and 15 Harvest (`/v2/...`, envelope `{<resource>:[...], pagination}`).

## 1b. (offline mode) Read the seeded Bronze surface

No tunnel. Bronze was loaded by `seed_bronze.sh`; the raw JSON *is* the schema:

```sql
SELECT PAYLOAD FROM DEMO_EMPLOYEE_APP.BRONZE.EMPLOYEES LIMIT 1;      -- nested (position.name, ...)
SELECT PAYLOAD FROM DEMO_EMPLOYEE_APP.BRONZE.TIME_ENTRIES LIMIT 1;   -- nested (user.id, project.id, ...)
```

If Bronze is not yet loaded, read `examples/hris_people/schema_spec.json` (its `api_field` is the `json_path`,
dotted for nested like `department.name`).

## 2. Pull one sample per nested endpoint → see the real JSON shape

Most endpoints are **flat snake_case**. Two headline resources are **nested** so the
"raw nested JSON → flatten into Silver" step is visible:
- `employees`: `position.name`, `department.name`, `work_location.name`, `reporting_manager.id`, `system_id`.
- `time_entries`: `user.id`, `project.id`, `task.id`, `billable`.

## 3. Identify entity, grain, and the envelope per endpoint

For each endpoint record: `source` (omnihr/harvest), `api_path`, `table` (UPPERCASE), one-line `grain`, and
the `envelope` (`results` for OmniHR, the resource key for Harvest, or a bare array).

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
  (`position.name`, `user.id`). This is the OmniHR/Harvest → warehouse lineage that becomes the Silver
  field-map. Record it even when it equals `lower(column)` — the map is the lineage.
- Flag foreign keys from name + nesting (`user.id` on `time_entries` → `EMPLOYEES`; `*_ID` columns).

## 5. Validate build/extraction_map.json and hand off

Shape (one object per endpoint):

```json
{
  "extracted_from": "https://<tunnel-host>   OR   offline: seeded BRONZE + src reference",
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

Confirm 33 tables, exactly 2 nested (`EMPLOYEES`, `TIME_ENTRIES`), ~261 columns, then report the map is ready
for **`medallion-build`** (step ②). See `references/field_path_extraction.md` for the nested-path walkthrough.

# Best Practices

- **Always delegate to the extraction subagent** (`references/extraction_subagent.md`); never build the map
  inline. This is what makes the step deterministic on both paths.
- **Converge on the reference SQL for exact names/types.** In live mode the point is showing CoCo read a real
  API; use `src/02_bronze.sql` / `src/03_silver.sql` to confirm you landed the same 33 tables. In offline mode
  they are the primary source for column names/types alongside the seeded Bronze VARIANT.
- **UPPERCASE** table/column names; keep `json_path` in the original JSON casing (lineage).
- **Always record `json_path`** — flat or nested. It is the single source of the Silver flatten.
- **Find the foreign keys** (`TIME_ENTRIES.EMPLOYEE_ID → EMPLOYEES`, `PROJECT_ID → PROJECTS`, …).
- **Don't invent fields.** Map only what the source (OpenAPI / sample page / Bronze VARIANT / `03_silver.sql`)
  shows.
- **Stop at the map.** Authoring SQL and running it (with review hooks) is `medallion-build`'s job.

# Examples

## Example 1: Live path

User (mock API up over the tunnel): "Extract the schema and let's build the medallion." CoCo invokes the
extraction subagent with `MODE=live, BASE=<tunnel url>`; it curls `/openapi.json` + a sample page per
endpoint, identifies `EMPLOYEES` + `TIME_ENTRIES` (nested) plus 31 flat entities, maps each field to a type +
`json_path`, flags PKs/FKs, writes `build/extraction_map.json`, and reports "33 endpoints (2 nested), 18
OmniHR + 15 Harvest — ready for medallion-build."

## Example 2: Offline / seeder path

User on a trial account after `seed_bronze.sh` loaded Bronze: "Extract the schema so I can review the layers."
CoCo invokes the extraction subagent with `MODE=offline`; it reads `SELECT PAYLOAD FROM BRONZE.EMPLOYEES` +
`SELECT PAYLOAD FROM BRONZE.TIME_ENTRIES` for the nested shapes, cross-checks `src/02`/`src/03`, and writes the
**same** `build/extraction_map.json` (`extracted_from: "offline: seeded BRONZE + src reference"`) — ready for
`medallion-build`'s Silver + Gold review hooks.

# References

- `references/extraction_subagent.md` — the dedicated extraction subagent's reusable prompt (live + offline
  modes), the output contract, and the post-run validation checklist.
- `references/field_path_extraction.md` — the nested-JSON → Silver field-path walkthrough (the employees /
  time_entries headline resources) and the JSON→Snowflake type rules in full.
