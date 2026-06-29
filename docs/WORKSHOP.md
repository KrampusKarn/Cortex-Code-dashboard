# Workshop: Build a Snowflake medallion + Cortex assistants, live with Cortex Code

A facilitator's run-of-show. The arc: *the presenter builds the Employee 360 medallion live from a real API
(the **DEMO** path), while attendees follow along on their trial accounts (the **7ptrial** path) and land at
the same dashboard.*

## Learning objectives

By the end, participants can:
1. Explain the **Bronze → Silver → Gold** medallion and the two Cortex assistants (Search over docs, Analyst
   over a semantic view).
2. Watch Cortex Code **extract a live API**, then **generate the medallion SQL** with a review hook at each
   layer.
3. Reproduce the build on a trial account (no External Access) via the offline seeder.
4. Deploy the Streamlit app and verify both assistants answer.

## Audience & prerequisites

- Data/analytics engineers and solution architects comfortable with SQL and the terminal.
- Each participant needs: a Snowflake account with **Cortex enabled**, the **`snow` CLI** authenticated with a
  `7ptrial` connection, **Python 3.9+** with `pip install -r requirements.txt`, and this repo cloned.
- Pre-flight (the day before): `snow connection test -c 7ptrial` and
  `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;` (plus
  `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';` if models are region-limited).
- The **presenter only** needs the `sevenpeaks_partner_demo` connection and the mock API + tunnel
  (`mock_api/serve_eai.sh`).

## Agenda (~3 hours)

| Time | Segment | Mode |
|---|---|---|
| 0:00–0:20 | **Why** — the medallion + Cortex assistants, and the "Cortex Code builds it" idea | talk |
| 0:20–1:10 | **Live build (DEMO path)** — presenter drives skills ①→④, reviewing each layer | demo |
| 1:10–1:20 | Break | — |
| 1:20–2:30 | **Lab (7ptrial path)** — participants reproduce it on a trial account | hands-on |
| 2:30–2:50 | **Show & tell** — a few participants demo their two assistants | share |
| 2:50–3:00 | **Production** — re-pointing GOLD views at real OmniHR/Harvest tables; Q&A | talk |

## Live build — DEMO path (presenter, ~50 min)

On `sevenpeaks_partner_demo`, after `src/reset_for_coco.sql` (drops only the medallion) and `src/00_setup.sql`,
start the API: `cd mock_api && ./serve_eai.sh start`. Then narrate the skill chain:

1. **`api-schema-extraction`** — CoCo curls `/openapi.json` + a sample page per endpoint, shows how
   `employees`' nested `position.name` / `reporting_manager.id` become flatten paths, and writes
   `build/extraction_map.json`.
2. **`medallion-build`** — CoCo generates `build/bronze.sql`; **pause, review it together, then run** (point
   the network rule at the tunnel, `CALL SP_INGEST_ALL_BRONZE`, show the raw VARIANT). Repeat for
   `build/silver.sql` (`CALL SP_BUILD_SILVER`) and `build/gold.sql`. The **review hook at each layer** is the
   moment to invite "what would you change here?" — widen a column, add a view — and re-run just that layer.
3. **`cortex-analyst-search`** — generate the semantic view + the document Search; **review, then run**; load
   `docs/*.md` and rebuild the chunks.
4. **`dashboard-compose`** — deploy the committed app; ask "headcount by department" (Analyst) and "What is the
   PTO policy?" (Search).

## Lab — 7ptrial path (participants, ~70 min)

"Now build it on your trial account — no External Access needed." On `7ptrial`:

1. `src/00_setup.sql` + `src/03_silver.sql` (database, warehouses, PUBLIC tables, SILVER tables + flatten proc).
2. `cd src/seeders && ./seed_bronze.sh --connection 7ptrial` (loads Bronze from the profiles), then
   `CALL SILVER.SP_BUILD_SILVER();`.
3. `src/04_gold.sql` → `src/05_semantic_analyst.sql` → `src/01_document_ingestion.sql`.
4. Deploy with `src/deploy_app.sql` (Workspace) or `snow streamlit deploy -c 7ptrial`, load `docs/*.md`, and
   ask each assistant a question.

Facilitators float and unblock. The pitfalls table below covers ~90% of issues.

## Common pitfalls (and fixes)

| Pitfall | Fix |
|---|---|
| Either assistant returns nothing | `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;` and wait for the Cortex Search service's initial build. |
| Dashboard charts blank | GOLD empty — Bronze not ingested/flattened. Check `BRONZE.BRONZE_INGEST_LOG`, re-`CALL SP_BUILD_SILVER`. |
| `USE WAREHOUSE` confusion | Two warehouses by design: `DEMO_EMPLOYEE_APP` (app) + `DEMO_WH` (Search/tasks). Don't add a third. |
| DEMO Bronze ingest fails | The network rule host doesn't match the live tunnel — `ALTER NETWORK RULE … SET VALUE_LIST=('<host>')` or `serve_eai.sh start --set-rule`. |
| Seeder Bronze looks wrong | Edit `profiles_*.json`, re-run `seed_bronze.sh`, re-flatten; run `seed_bronze.py --selftest`. |
| `snow streamlit deploy` can't find the app | Run it from `deployed_app/app/` (it has `snowflake.yml`). |

## Facilitator checklist

- [ ] Participants completed pre-flight (connection test + CORTEX_USER grant).
- [ ] Repo cloned; `pip install -r requirements.txt` done.
- [ ] The presenter's mock API + tunnel are up and the network rule points at it.
- [ ] A pre-built account on standby as a fallback demo.
- [ ] Time-boxed the lab; kept the last 10 minutes for the production re-pointing story.
