# The dedicated extraction subagent

`api-schema-extraction` **always** delegates the map build to a `Task` subagent
(`subagent_type: generalPurpose`). This keeps the main context lean and makes the step
deterministic and reproducible across runs. The subagent does the mechanical work — read the
source, map every field, emit `build/extraction_map.json` — and reports a short summary back.

The subagent has **two modes**, selected by how Bronze will be filled:

| Mode | When | Source it reads |
|---|---|---|
| **live** | live-API path (account can create an EAI + the mock API is up over a tunnel) | `GET <tunnel>/openapi.json` + one sample page per endpoint, cross-checked with `src/02_bronze.sql` + `src/03_silver.sql` |
| **offline** | seeder path (trial / no EAI) — Bronze already seeded by `seed_bronze.sh` | `SELECT PAYLOAD FROM BRONZE.<t> LIMIT 1` per table + `src/02_bronze.sql` + `src/03_silver.sql` (and/or `examples/hris_people/schema_spec.json`) |

Both modes emit the **identical** `build/extraction_map.json` shape and hand off to `medallion-build`.

## How to invoke

Call the `task` tool once with `subagent_type: generalPurpose` and the prompt template below,
filling in `MODE` and (for live) the tunnel `BASE` URL. Do **not** build the map inline in the
main thread — always delegate. After it returns, validate the JSON (table count, nested tables,
column count) before handing off.

## Prompt template (fill the bracketed values)

```
You are the dedicated extraction subagent for step ① (api-schema-extraction) of a Snowflake
medallion demo. Produce ONE artifact: build/extraction_map.json
(examples/hris_people/deployed_app/build/extraction_map.json). Do NOT write SQL or touch Snowflake state.

MODE = [live | offline]

## Source by mode
- MODE=live: the mock OmniHR+Harvest API is reachable at BASE=[https://<tunnel-host>]. It returns JSON only
  with headers:  -H 'ngrok-skip-browser-warning: true' -H 'User-Agent: cortex-extract'
  - GET $BASE/            -> endpoint index (33 endpoints: 18 omnihr /api/v1/..., 15 harvest /v2/...)
  - GET $BASE/openapi.json -> full schema; save to build/openapi.json
  - Fetch a sample page for the two NESTED headline resources to confirm shape:
    GET $BASE/api/v1/employees?page=1&page_size=3   and   GET $BASE/v2/time_entries?per_page=3
  - Spot-fetch 2-3 flat endpoints to confirm flat snake_case.
- MODE=offline: NO tunnel. Bronze is already seeded. Read the real JSON shape from the VARIANT:
    SELECT PAYLOAD FROM DEMO_EMPLOYEE_APP.BRONZE.<TABLE> LIMIT 1   (read-only) for the nested tables
    (EMPLOYEES, TIME_ENTRIES) and a few flat ones. If Bronze is not yet loaded, fall back to
    examples/hris_people/schema_spec.json (its `api_field` is the json_path, dotted for nested).

## Ground truth for exact names/types (BOTH modes — the mock API is generated from these)
- src/02_bronze.sql — BRONZE_ENDPOINTS registry: the 33 (source, api_path, table) rows + envelope style
  (OmniHR envelope = `results`; Harvest envelope = the resource key).
- src/03_silver.sql — (a) typed SILVER.* CREATE TABLEs = exact UPPERCASE column names + Snowflake types;
  (b) SILVER.SILVER_FIELD_MAP inserts = the nested json_path for columns whose path != lower(column)
  (e.g. position.name, department.name, work_location.name, reporting_manager.id, user.id, project.id,
  task.id, billable). Flat columns map by lower(column).

## Method
1. Confirm the source is reachable for the chosen MODE (curl liveness, or SELECT PAYLOAD, or read schema_spec.json).
2. Parse src/02_bronze.sql for the 33 (source, api_path, table) rows.
3. Parse src/03_silver.sql: per table, columns (name + type), PK (the id/primary key column -> "pk": true),
   FKs (EMPLOYEE_ID/user.id -> EMPLOYEES, PROJECT_ID -> PROJECTS, TASK_ID -> TASKS, CLIENT_ID -> CLIENTS,
   manager -> EMPLOYEES, etc. -> "fk": "<TABLE>").
4. Set json_path per column: SILVER_FIELD_MAP path when present (nested, keep original JSON casing);
   otherwise lower(COLUMN_NAME).

## Output (write build/extraction_map.json, valid JSON)
{
  "extracted_from": "[<tunnel url>  OR  offline: seeded BRONZE + src reference]",
  "tables": [
    { "source":"omnihr", "api_path":"/api/v1/employees", "table":"EMPLOYEES",
      "grain":"one row per employee", "envelope":"results", "nested":true,
      "columns":[
        {"name":"EMPLOYEE_ID","type":"NUMBER(38,0)","json_path":"id","pk":true},
        {"name":"TITLE","type":"VARCHAR(150)","json_path":"position.name"},
        {"name":"MANAGER_ID","type":"NUMBER(38,0)","json_path":"reporting_manager.id","fk":"EMPLOYEES"}
      ] }
  ]
}
All 33 tables present. UPPERCASE table/column names; json_path in original JSON casing. Only fields that
exist in src/03_silver.sql (do not invent).

## Report back
total endpoints, omnihr vs harvest counts, which tables are nested, total column count, the MODE used and
`extracted_from`, and confirm the file was written. Flag any 02_bronze table with no CREATE TABLE in 03_silver.
```

## After the subagent returns
Validate before handing to `medallion-build`:
- 33 tables, exactly 2 nested (`EMPLOYEES`, `TIME_ENTRIES`), ~261 columns.
- `EMPLOYEES` shows nested `json_path`s (`position.name`, `department.name`, `reporting_manager.id`).
- Then report: "N endpoints (2 nested), 18 OmniHR + 15 Harvest — ready for medallion-build."
