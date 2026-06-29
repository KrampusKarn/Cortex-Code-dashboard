---
name: medallion-build
description: Generate the Bronze→Silver→Gold medallion SQL from a live extraction map, ONE LAYER AT A TIME, pausing at a confirm-and-proceed hook after each layer so the presenter reviews (and can revise) the schema before it runs. Authors build/bronze.sql (External Access ingest of the OmniHR+Harvest API into raw VARIANT), build/silver.sql (typed tables + the nested-JSON flatten/field-map), and build/gold.sql (1:1 pass-through views + curated analytics views the dashboard reads). This is step ② of the DEMO (live mock_api) path, after api-schema-extraction. Use when the presenter has build/extraction_map.json and wants CoCo to build the medallion with per-layer review.
tools:
- read_file
- write_file
- run_shell_command
---

# When to Use

- Step ② of the **DEMO path** (connection `sevenpeaks_partner_demo`): `build/extraction_map.json` exists
  (from `api-schema-extraction`) and the presenter wants CoCo to **build the medallion**, reviewing each
  layer before it runs.
- The whole point is to **showcase how easily Cortex Code stands up a medallion** — generate the SQL, let a
  human eyeball Bronze, then Silver, then Gold, tweak anything, and only then implement.
- Keywords: medallion, Bronze, Silver, Gold, flatten, build the warehouse, ELT, generate the SQL, review.

This skill generates SQL into `build/` and runs it **only after you approve each layer**. The Cortex Analyst
semantic view + the document Search are step ③ (`cortex-analyst-search`); deploying the app is step ④
(`dashboard-compose`). The **7ptrial** path does not use this skill — it loads Bronze from the seeder and
runs the committed `src/03→04.sql` as-is (`trial-seed-bronze`).

# The review hook (apply to EVERY layer — Bronze, Silver, AND Gold)

**There are three separate stops — Bronze, then Silver, then Gold — each its own review.** Do exactly one
layer at a time: generate it, run the loop below, and only after it is approved and run do you generate the
**next** layer and stop again. Never generate or run Silver and Gold together, and never run a layer the user
has not explicitly picked **1) Run it** for. (Silver is the one most worth reviewing — its typed columns and
the nested flatten paths are what the presenter most wants to control.)

For each layer, follow this loop — never run a layer's SQL before the presenter approves it:

1. **Generate** the layer file into `examples/hris_people/deployed_app/build/` (`bronze.sql`, then
   `silver.sql`, then `gold.sql`).
2. **Present** a tight summary: what schemas/tables/views it creates, the column→type→json_path decisions
   that matter (especially the nested flatten paths), and the file path to open.
3. **STOP and offer explicit numbered choices.** End the message with this menu, then wait — do not run
   anything yet:
   > **Review `build/<layer>.sql`. Reply with:**
   > **1) Run it** · **2) Revise** (tell me what to change) · **3) Show full SQL** · **4) Skip this layer**
4. **Act on the reply.** `1` → run it against `sevenpeaks_partner_demo`, show the result (row counts / object
   list), advance to the next layer. `2` → edit just this layer's file per the feedback, then re-present the
   menu. `3` → print the full file, then re-present the menu. `4` → skip it (state the consequence). Never
   advance until the current layer is approved — Silver needs Bronze, Gold needs Silver.

(Cortex Code skills can't render buttons; the menu is plain text and the user replies in chat. Always present
the numbered options rather than deciding for them.)

# Prerequisites

1. `build/extraction_map.json` from `api-schema-extraction`.
2. The PUBLIC app/RAG layer exists: run `src/00_setup.sql` once (database `DEMO_EMPLOYEE_APP`, warehouses
   `DEMO_EMPLOYEE_APP` + `DEMO_WH`, schema, chat/document tables). For a clean "build from empty" demo, run
   `src/reset_for_coco.sql` first (drops only BRONZE/SILVER/GOLD; keeps PUBLIC + the app).
3. The mock API is up over its tunnel (Bronze ingest needs it). `mock_api/serve_eai.sh start` prints the host.
4. **Golden references** to converge on (read, don't copy): `src/02_bronze.sql`, `src/03_silver.sql`,
   `src/04_gold.sql`. `references/layer_patterns.md` has copy-ready skeletons keyed to the extraction map.

# Workflows

## Layer 1 — Bronze (raw VARIANT landing + live ingest)  → review hook

Generate `build/bronze.sql` from the map:
- `CREATE SCHEMA IF NOT EXISTS BRONZE / SILVER / GOLD`.
- The egress **network rule** `BRONZE.OMNI_HARVEST_EGRESS` + **external access integration**
  `OMNI_HARVEST_EAI` (Bronze ingest reaches the tunnel through these).
- `BRONZE.BRONZE_ENDPOINTS (SOURCE, API_PATH, TABLE_NAME)` — one row per `tables[]` entry in the map.
- `BRONZE.SP_INGEST_BRONZE` (paginated pull → `BRONZE.<table>(PAYLOAD VARIANT, _SOURCE, _PATH, _LOADED_AT)`)
  and `BRONZE.SP_INGEST_ALL_BRONZE(BASE_URL)` (loops the registry). See `references/layer_patterns.md`.

**Review hook (present the numbered menu, then wait).** On **1) Run it**, run `build/bronze.sql`, then point the rule at the live host and ingest:
```sql
ALTER NETWORK RULE BRONZE.OMNI_HARVEST_EGRESS SET VALUE_LIST = ('<your-tunnel-host>');
CALL BRONZE.SP_INGEST_ALL_BRONZE('https://<your-tunnel-host>');
SELECT * FROM BRONZE.BRONZE_INGEST_LOG ORDER BY ROW_COUNT DESC;   -- every endpoint non-zero
```
(`serve_eai.sh start --set-rule` can set the rule for you.) Confirm `SELECT PAYLOAD FROM BRONZE.EMPLOYEES
LIMIT 1` shows the raw nested JSON before moving on.

## Layer 2 — Silver (typed tables + flatten the nested JSON)  → review hook

Generate `build/silver.sql` from the map:
- One typed `CREATE TABLE IF NOT EXISTS SILVER.<table> (...)` per entity, columns + types from the map.
- `SILVER.SILVER_FIELD_MAP (SILVER_TABLE, COLUMN_NAME, JSON_PATH)` — a row for **every column whose
  `json_path` ≠ `lower(column)`** (i.e. the nested `EMPLOYEES`/`TIME_ENTRIES` paths). Flat columns are left
  out; the flatten falls back to `lower(column)`.
- `SILVER.SP_FLATTEN(TABLE_NAME)` (builds `INSERT OVERWRITE … SELECT PAYLOAD:<path>::<type> AS <col>` from
  INFORMATION_SCHEMA + the field-map; skips empty Bronze) and `SILVER.SP_BUILD_SILVER()` (loops the registry).

**Review hook (present the numbered menu, then wait).** On **1) Run it**, run `build/silver.sql`, then:
```sql
CALL SILVER.SP_BUILD_SILVER();
SELECT EMPLOYEE_ID, FIRST_NAME, EMAIL, TITLE, DEPARTMENT FROM SILVER.EMPLOYEES ORDER BY EMPLOYEE_ID LIMIT 5;
```
This is the layer most worth a **review session** — the typed schema and the flatten paths are what the
presenter most wants to control. If a type/width/path is off, revise `build/silver.sql` and re-flatten.

## Layer 3 — Gold (the read surface the dashboard queries)  → review hook

Generate `build/gold.sql`:
- **Entity pass-throughs**: `CREATE OR REPLACE VIEW GOLD.<ENTITY> AS SELECT * FROM SILVER.<ENTITY>` — one per
  table the dashboard needs (so the app's `SCH="GOLD"` resolves everything).
- **Curated analytics views**: at minimum `GOLD.EMPLOYEE_360` (the canonical employee dimension the sidebar /
  exec tabs / org tree read) plus the rollups the dashboard uses (`HEADCOUNT_BY_DEPARTMENT`, utilization,
  `LEAVE_SUMMARY`, …). Match the view names in `src/04_gold.sql` — the committed `app/streamlit_app.py`
  queries them by name.

**Review hook (present the numbered menu, then wait).** On **1) Run it**, run `build/gold.sql`, then spot-check
`SELECT * FROM GOLD.EMPLOYEE_360 LIMIT 5;`. When Gold is approved, hand off to **`cortex-analyst-search`**
(step ③) for the semantic view + document Search, then **`dashboard-compose`** (step ④) to deploy the app.

# Best Practices

- **One layer, one hook.** Never generate-and-run all three silently — the review gates are the demo.
- **Generate into `build/`, never overwrite `src/`.** The committed `src/02→05.sql` are the golden reference
  and the 7ptrial path; clobbering them breaks attendees.
- **Converge on the reference shapes.** Names like `GOLD.EMPLOYEE_360`, `GOLD.HEADCOUNT_BY_DEPARTMENT`,
  `SP_BUILD_SILVER` are queried by the committed app — keep them identical so the dashboard lights up.
- **The field-map is only the nested columns.** Don't list flat columns in `SILVER_FIELD_MAP`; the flatten
  defaults to `lower(column)`.
- **Idempotent SQL** (`IF NOT EXISTS` / `CREATE OR REPLACE`) so re-running a revised layer never drops data.
- **Run as `ACCOUNTADMIN`** (External Access + owner's rights), on `sevenpeaks_partner_demo`.

# Examples

## Example 1: Build the medallion with review

Presenter: "Map's ready — build it, but let me see each layer."

CoCo: generates `build/bronze.sql`, summarizes (3 schemas, EAI, 33-endpoint registry, 2 ingest procs),
**stops** — "open `build/bronze.sql`; run it?" On approve, runs it, points the rule at the tunnel, calls
`SP_INGEST_ALL_BRONZE`, shows the ingest log. Then `build/silver.sql` (24 typed tables, 15 field-map rows for
the 2 nested endpoints), **stops**; on approve runs it and calls `SP_BUILD_SILVER`. Then `build/gold.sql`
(pass-throughs + `EMPLOYEE_360` + rollups), **stops**; on approve runs it and verifies `EMPLOYEE_360`.

## Example 2: Presenter wants a wider salary column

At the Silver hook the presenter says "make `BASE_SALARY` `NUMBER(12,2)`." CoCo edits only that column in
`build/silver.sql`, re-presents the diff, and on approval re-runs Silver — Bronze and Gold untouched.

# References

- `references/layer_patterns.md` — copy-ready SQL skeletons for each layer (Bronze ingest procs, the Silver
  flatten proc + field-map, Gold views), parameterized by the extraction map and keyed to the golden `src/`.
