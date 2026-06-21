# Cortex Dashboard Kit

> Turn any API data source into a Snowflake-native dashboard **with a Cortex AI chat assistant** — using Cortex Code to do the heavy lifting.

Point Cortex Code at an API's documentation (or a sample JSON response) and this kit walks it through a repeatable, three-step pipeline:

```
 API docs / sample JSON
          │
          ▼  (skill: api-schema-extraction)
   schema_spec.json  ───────────────┐
          │                         │
          ▼  (skill:                ▼  (skill: dashboard-rag-scaffold)
   demo-data-generator)        deploy SQL + Streamlit RAG app
   deterministic seed CSVs  ──▶  load → Cortex Search → Streamlit-in-Snowflake
```

The result is a working demo — dashboards **plus a retrieval-augmented Cortex chat** over a knowledge base — that you can show *before* a single byte of real API data has landed, and that re-points at production tables later by swapping a config.

## The three Cortex Code skills

| Skill | Input | Output |
|---|---|---|
| [`api-schema-extraction`](.cortex/skills/api-schema-extraction) | API docs / sample JSON | a validated `schema_spec.json` |
| [`demo-data-generator`](.cortex/skills/demo-data-generator) | `schema_spec.json` | deterministic seed CSVs |
| [`dashboard-rag-scaffold`](.cortex/skills/dashboard-rag-scaffold) | spec + knowledge base | Snowflake objects + Streamlit RAG app |

The contract that ties them together — `schema_spec.json` — is documented in [`docs/CONTRACT.md`](docs/CONTRACT.md).

## Worked examples

| Example | Source shape | What it shows |
|---|---|---|
| [`examples/hris_people`](examples/hris_people) | Freshteam / Harvest / Lattice (HR) | Workforce, joiners/attrition, sentiment, training % + RAG over a company handbook |
| [`examples/dynamics_erp`](examples/dynamics_erp) | Microsoft Dynamics 365 (OData) | Revenue, top customers, AR aging, orders/inventory + RAG over finance policies; demonstrates parent→child (`per_parent`) modeling |

## Prerequisites

- A **Snowflake account with Cortex enabled** — Cortex Search plus `SNOWFLAKE.CORTEX.COMPLETE` / `SEARCH_PREVIEW`. The deploy role needs the Cortex role:
  ```sql
  GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;
  ```
- The [**`snow` CLI**](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index), authenticated via a connection in `~/.snowflake/connections.toml`. (Credentials live there, never in this repo.)
- **Python 3.9+** with the local tooling: `pip install -r requirements.txt` (Faker + jsonschema). Note: `pandas`/`altair` are **not** needed locally — they run inside Snowflake's Streamlit runtime; the generator uses only the stdlib `csv` module.

## Quick start (≈5 minutes) — the HRIS example

```bash
# 0. install local tooling and confirm your Snowflake connection
pip install -r requirements.txt
snow connection test -c <your_connection>

# 1. validate the example spec
python3 tools/validate_spec.py examples/hris_people/schema_spec.json

# 2. (re)generate the synthetic seed data — omit --today for "current" data,
#    or pin it for byte-stable output
python3 templates/generator/generate_seed.py \
    --spec examples/hris_people/schema_spec.json \
    --out  examples/hris_people/seed --today 2026-06-22

# 3. render the deployable bundle (deploy SQL + Streamlit app) in place
python3 templates/render.py --spec examples/hris_people/schema_spec.json \
    --out examples/hris_people

# 4. bootstrap + load + create the Cortex Search service (+ row-count verification)
examples/hris_people/deploy/run.sh <your_connection>

# 5. deploy the Streamlit app (run from the app dir; it reads snowflake.yml)
cd examples/hris_people/app && snow streamlit deploy --connection <your_connection> --replace && cd -
```

Open the URL from step 5, go to the **Assistant** tab, and ask "What is the PTO policy?" — you should get a grounded answer with a **Sources** expander. The other tabs are the People dashboards.

> The bundle is rendered *in place* for the examples, so `deploy/`, `app/`, and `seed/` sit next to the spec. The committed `seed/` CSVs let you skip step 2 if you just want to deploy.

## Build a dashboard for *your* API

1. Hand Cortex Code your API docs or a sample response and invoke **`api-schema-extraction`** → it writes a `schema_spec.json`.
2. Invoke **`demo-data-generator`** → seed CSVs.
3. Invoke **`dashboard-rag-scaffold`** → deploy + Streamlit RAG app.

See [`docs/WORKSHOP.md`](docs/WORKSHOP.md) for a facilitated run-of-show and [`docs/DYNAMICS_WALKTHROUGH.md`](docs/DYNAMICS_WALKTHROUGH.md) for a full extract→deploy walkthrough on the Dynamics OData sample.

## Repository layout

```
docs/                 CONTRACT.md (the schema_spec contract), WORKSHOP.md, DYNAMICS_WALKTHROUGH.md
.cortex/skills/       the three Cortex Code skills (+ references/)
templates/            schema_spec.schema.json, generator/generate_seed.py, render.py, app/* (RAG app)
fixtures/             sample API responses to practice extraction on
examples/             hris_people/ and dynamics_erp/ — complete, runnable examples
tools/                validate_spec.py, lint_skill.py (static checks)
```

## How it works

- **One contract.** Everything keys off `schema_spec.json` (see [`docs/CONTRACT.md`](docs/CONTRACT.md)), validated by `templates/schema_spec.schema.json`.
- **Deterministic data.** The generator seeds Faker/`random` from a fixed seed; the knowledge-base table is seeded from a curated `kb_content.json`; chat tables are DDL-only (the app writes them).
- **No hardcoding.** Every Snowflake/app identity value (database, warehouse, model, company name, prompts) lives in a generated `app_config.py`; the Streamlit app and SQL read only from there, so there is one warehouse name and no drift.
- **Parameterized RAG.** `templates/app/rag_chat.py` does `SEARCH_PREVIEW` → `COMPLETE`, persists chat with **bind variables only** (no string-interpolated SQL), and works for any domain.

## Security

This kit connects to Snowflake through the `snow` CLI, which reads credentials from your local `~/.snowflake/connections.toml` — **never from this repo**. Connection files, `*.p8` keys, and `.env` files are git-ignored. Everything under `examples/*/seed/` is synthetic data produced by the generator; commit no real customer, employee, or client data.

## License

MIT — see [LICENSE](LICENSE).
