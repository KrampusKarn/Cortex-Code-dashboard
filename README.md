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
| [`api-schema-extraction`](.snowflake/cortex/skills/api-schema-extraction) | API docs / sample JSON | a validated `schema_spec.json` |
| [`demo-data-generator`](.snowflake/cortex/skills/demo-data-generator) | `schema_spec.json` | deterministic seed CSVs |
| [`dashboard-rag-scaffold`](.snowflake/cortex/skills/dashboard-rag-scaffold) | spec + knowledge base | Snowflake objects + Streamlit RAG app |

The contract that ties them together — `schema_spec.json` — is documented in [`docs/CONTRACT.md`](docs/CONTRACT.md).

## Worked examples

| Example | Source shape | What it shows |
|---|---|---|
| [`examples/hris_people`](examples/hris_people) | Freshteam / Harvest / Lattice (HR) | Workforce, joiners/attrition, sentiment, training % + RAG over a company handbook |
| [`examples/dynamics_erp`](examples/dynamics_erp) | Microsoft Dynamics 365 (OData) | Revenue, top customers, AR aging, orders/inventory + RAG over finance policies; demonstrates parent→child (`per_parent`) modeling |

## Prerequisites

**Always** — a **Snowflake account with Cortex enabled** (Cortex Search plus `SNOWFLAKE.CORTEX.COMPLETE` / `SEARCH_PREVIEW`). The deploy role needs the Cortex role:
```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;
```

That is **all** you need for the Snowflake Workspaces path below — it runs entirely in the browser, no local install.

**Only for the CLI / local-IDE path:**
- The [**`snow` CLI**](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index), authenticated via a connection in `~/.snowflake/connections.toml`. (Credentials live there, never in this repo.)
- **Python 3.9+** with the local tooling: `pip install -r requirements.txt` (Faker + jsonschema). `pandas`/`altair` are **not** needed locally — they run inside Snowflake's Streamlit runtime; the generator is stdlib-only.

## Deploy in Snowflake Workspaces (recommended — no local tooling)

For non-technical users: everything runs in the browser — no shell, no `PUT`, no Python. Each example ships a single self-contained [`deploy/workspace_setup.sql`](examples/hris_people/deploy/workspace_setup.sql): warehouse/db/schema + tables + the synthetic demo data as `INSERT`s + the Cortex Search service.

1. **Connect this repo to a Workspace** — in Snowsight: *Projects » Workspaces » From Git repository*, paste the repo URL (a public repo needs no auth). ([docs](https://docs.snowflake.com/en/user-guide/ui-snowsight/workspaces-git))
2. **Grant Cortex once** (a role admin): `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;`
3. **Open `examples/hris_people/deploy/workspace_setup.sql` → Run All.** It creates everything and loads the data inline; the final query is a row-count check (every table should be non-empty).
4. **Create the Streamlit app from the repo** — *Projects » Streamlit » + Streamlit App » From repository*, point it at `examples/hris_people/app/`, main file `streamlit_app.py`. (The equivalent `CREATE STREAMLIT … FROM @repo` is at the bottom of `workspace_setup.sql`.)
5. Give Cortex Search a few minutes to finish its initial build, then open the app → **Assistant** tab → ask "What is the PTO policy?" — you should get a grounded answer with a **Sources** expander.

> Swap `dynamics_erp` for `hris_people` to deploy the Dynamics 365 example instead.

## Quick start — CLI / local IDE (advanced)

This path regenerates `seed/` and the numbered deploy SQL locally, then loads via the `snow` CLI. Use it if you live in a terminal; otherwise prefer the Workspaces path above.

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

> **What's in git, per example.** Tracked: the hand-authored inputs (`schema_spec.json`, `kb_content.json`, the customized `app/streamlit_app.py`) **plus** the artifacts the browser path needs server-side — `deploy/workspace_setup.sql` and the rest of `app/`. Git-ignored and regenerated by the CLI steps above: the bulky `seed/` CSVs and the numbered SQL + `run.sh`. Re-rendering is safe — `render.py` never overwrites your `app/streamlit_app.py`.

## Build a dashboard for *your* API

1. Hand Cortex Code your API docs or a sample response and invoke **`api-schema-extraction`** → it writes a `schema_spec.json`.
2. Invoke **`demo-data-generator`** → seed CSVs.
3. Invoke **`dashboard-rag-scaffold`** → deploy + Streamlit RAG app.

The scaffold writes a self-contained `deploy/workspace_setup.sql`, so your own API gets the same browser-only deploy: connect the repo to a Workspace, **Run All**, then create the Streamlit app from the repo — no local tooling required.

See [`docs/WORKSHOP.md`](docs/WORKSHOP.md) for a facilitated run-of-show and [`docs/DYNAMICS_WALKTHROUGH.md`](docs/DYNAMICS_WALKTHROUGH.md) for a full extract→deploy walkthrough on the Dynamics OData sample.

## Repository layout

```
docs/                      CONTRACT.md (the schema_spec contract), WORKSHOP.md, DYNAMICS_WALKTHROUGH.md
AGENTS.md                  workspace instructions Cortex Code auto-loads every conversation
.snowflake/cortex/skills/  the three Cortex Code skills (+ references/) — where Snowsight discovers them
templates/                 schema_spec.schema.json, generator/generate_seed.py, render.py, app/* (RAG app)
examples/                  hris_people/ and dynamics_erp/ — worked examples. Committed: spec, KB,
                           app/ (for CREATE STREAMLIT), deploy/workspace_setup.sql (the Run-All deploy).
                           Git-ignored/regenerated: seed/ CSVs + the numbered CLI SQL + run.sh
tools/                     validate_spec.py, lint_skill.py (static checks)
```

## How it works

- **One contract.** Everything keys off `schema_spec.json` (see [`docs/CONTRACT.md`](docs/CONTRACT.md)), validated by `templates/schema_spec.schema.json`.
- **Deterministic data.** The generator seeds Faker/`random` from a fixed seed; the knowledge-base table is seeded from a curated `kb_content.json`; chat tables are DDL-only (the app writes them).
- **No hardcoding.** Every Snowflake/app identity value (database, warehouse, model, company name, prompts) lives in a generated `app_config.py`; the Streamlit app and SQL read only from there, so there is one warehouse name and no drift.
- **Parameterized RAG.** `templates/app/rag_chat.py` does `SEARCH_PREVIEW` → `COMPLETE`, persists chat with **bind variables only** (no string-interpolated SQL), and works for any domain.

## Security

This kit connects to Snowflake through the `snow` CLI, which reads credentials from your local `~/.snowflake/connections.toml` — **never from this repo**. Connection files, `*.p8` keys, and `.env` files are git-ignored. Everything under `examples/*/seed/` is synthetic data produced by the generator (and itself git-ignored — regenerate it); commit no real customer, employee, or client data.

## License

MIT — see [LICENSE](LICENSE).
