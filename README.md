# Employee 360 — a Cortex Code medallion demo

> Watch **Cortex Code** stand up a Snowflake-native **Bronze → Silver → Gold** dashboard with **two Cortex
> assistants** — live, from a real API, with a human reviewing each layer.

This repo is **one worked demo**, not a generic kit. Cortex Code extracts a live HR API, builds the medallion,
adds the assistants, and deploys the dashboard:

```
 live mock API (OmniHR + Harvest)
          │  ① api-schema-extraction      → build/extraction_map.json
          ▼
   Bronze → Silver → Gold                 ② medallion-build   (generate each layer → REVIEW HOOK → run)
          │
          ▼  ③ cortex-analyst-search       semantic view (Analyst) + document Search (RAG)
   GOLD.HR_ANALYST  +  COMPANY_KB_SEARCH
          │
          ▼  ④ dashboard-compose           deploy the Streamlit app (14 tabs + both assistants)
   DASHBOARD_SPS
```

The **review hook** is the point: skills ② and ③ generate the SQL into `build/`, **stop, and wait** for the
presenter to review (and tweak) each layer before it runs — so you control the schema and see how little it
takes to build a medallion with Cortex Code.

## Two paths

| Path | Connection | Who | Bronze comes from |
|---|---|---|---|
| **DEMO** | `sevenpeaks_partner_demo` | the presenter | the live mock API + External Access (skill-driven, reviewed) |
| **7ptrial** | `7ptrial` | attendees on trial accounts (no EAI) | the offline seeder loads the same JSON, then the committed reference SQL runs as-is |

Both converge on the **same** GOLD layer and dashboard. Trial accounts can't create an External Access
Integration, which is the only reason the offline path exists.

## The five Cortex Code skills (`.snowflake/cortex/skills/`)

| Skill | Path | Role |
|---|---|---|
| [`api-schema-extraction`](.snowflake/cortex/skills/api-schema-extraction) | DEMO ① | read the live API → `build/extraction_map.json` |
| [`medallion-build`](.snowflake/cortex/skills/medallion-build) | DEMO ② | generate Bronze/Silver/Gold SQL with a per-layer review hook |
| [`cortex-analyst-search`](.snowflake/cortex/skills/cortex-analyst-search) | DEMO ③ | semantic view (Analyst) + document Search (RAG) |
| [`dashboard-compose`](.snowflake/cortex/skills/dashboard-compose) | both ④ | deploy + verify the Streamlit app |
| [`trial-seed-bronze`](.snowflake/cortex/skills/trial-seed-bronze) | 7ptrial | offline Bronze load → the committed reference SQL |

## Prerequisites

- A **Snowflake account with Cortex enabled**, and the role granted Cortex:
  ```sql
  GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;
  -- if models are region-limited:  ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';
  ```
- For the **DEMO** path only: the **`snow` CLI** + a `sevenpeaks_partner_demo` connection in
  `~/.snowflake/connections.toml`, plus a tunnel for the mock API (`mock_api/serve_eai.sh`, ngrok/cloudflare).
- For the **7ptrial** path: a `7ptrial` connection and **Python 3.9+** with `pip install -r requirements.txt`
  (Faker only — the apps run inside Snowflake, not locally).

## Run it

The ordered runbook is **[`examples/hris_people/deployed_app/README.md`](examples/hris_people/deployed_app/README.md)**
(both paths) and **[`src/README.md`](examples/hris_people/deployed_app/src/README.md)** (the per-file run
table). In short:

- **DEMO (presenter):** `src/reset_for_coco.sql` → `src/00_setup.sql` → start the API (`mock_api/serve_eai.sh
  start`) → drive Cortex Code through skills ①→④, approving each medallion layer.
- **7ptrial (attendee):** `src/00_setup.sql` + `src/03_silver.sql` → `src/seeders/seed_bronze.sh --connection
  7ptrial` → `CALL SP_BUILD_SILVER()` → `src/04_gold.sql` → `05_semantic_analyst.sql` →
  `01_document_ingestion.sql` → deploy the app.

See [`docs/WORKSHOP.md`](docs/WORKSHOP.md) for the facilitated run-of-show.

## What's tracked vs generated

- **Committed:** the app (`deployed_app/app/`), the setup + medallion SQL (`deployed_app/src/*.sql` — the
  golden reference *and* the 7ptrial runtime), the mock API, the RAG docs, and `schema_spec.json` (lineage
  reference only).
- **Git-ignored / regenerated:** the DEMO path's generated SQL under `deployed_app/build/`. CoCo authors it
  live for review; it never overwrites `src/`.

## Repository layout

```
AGENTS.md                  instructions Cortex Code auto-loads every conversation
.snowflake/cortex/skills/  the five Cortex Code skills (+ references/)
examples/hris_people/
  deployed_app/app/        the Streamlit monolith (14 tabs + both assistants)
  deployed_app/src/        00→05 setup + Bronze→Silver→Gold + semantic view + deploy_app.sql + seeders/
  deployed_app/mock_api/   the live Extract source (FastAPI: OmniHR + Harvest)
  deployed_app/docs/       the RAG corpus (markdown)
  deployed_app/build/      git-ignored — DEMO-path generated SQL (for review)
  schema_spec.json         entity/lineage reference only
docs/                      WORKSHOP.md (the demo runbook)
tools/                     lint_skill.py (skill structure check)
```

## Security

Credentials live in `~/.snowflake/connections.toml`, **never in this repo** — connection files, `*.p8` keys,
and `.env` files are git-ignored. Everything under `examples/` is synthetic; commit no real customer, employee,
or client data.

## License

MIT — see [LICENSE](LICENSE).
