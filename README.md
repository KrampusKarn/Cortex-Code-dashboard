# Cortex Dashboard Kit

> Turn any API data source into a Snowflake-native dashboard **with a Cortex AI chat assistant** — using Cortex Code to do the heavy lifting.

Point Cortex Code at an API's documentation (or a sample JSON response), and this kit walks it through a repeatable pipeline:

1. **Extract** the response structure into a portable `schema_spec.json`.
2. **Generate** realistic, deterministic synthetic demo data from that spec.
3. **Scaffold** a Snowflake deployment (tables, stage, Cortex Search) and a Streamlit app — including a retrieval-augmented **Cortex AI chat** over a knowledge base.

The result is a working demo you can show *before* a single byte of real API data has landed, and that re-points at production tables later by swapping a config.

## The three Cortex Code skills

| Skill | Input | Output |
|---|---|---|
| `api-schema-extraction` | API docs / sample JSON | `schema_spec.json` (validated) |
| `demo-data-generator` | `schema_spec.json` | deterministic seed CSVs + DDL |
| `dashboard-rag-scaffold` | spec + knowledge base | Snowflake objects + Streamlit RAG app |

## Worked examples

- [`examples/hris_people`](examples/hris_people) — an HR/People dashboard (Freshteam / Harvest / Lattice shapes).
- [`examples/dynamics_erp`](examples/dynamics_erp) — a Microsoft Dynamics ERP dashboard (OData shapes).

## Where to start

- **Contract:** [`docs/CONTRACT.md`](docs/CONTRACT.md) — the `schema_spec.json` + app-config interface every skill and example shares.
- **Workshop guide:** [`docs/WORKSHOP.md`](docs/WORKSHOP.md) — facilitation run-of-show.

> ℹ️ This README is a stub during the build. The full quick-start (prerequisites, `snow` CLI setup, step-by-step) lands with the docs unit.

## Prerequisites (preview)

- A Snowflake account with Cortex enabled (`SNOWFLAKE.CORTEX` functions + Cortex Search).
- [`snow`](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index) CLI, authenticated via `~/.snowflake/connections.toml`.
- Python 3.11+ with `faker`, `pandas`, `jsonschema` (for the generator + validators).

## License

MIT — see [LICENSE](LICENSE).
