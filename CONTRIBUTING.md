# Contributing

Thanks for improving the Employee 360 Cortex Code demo. This repo is **one worked demo** (the HRIS medallion
app under `examples/hris_people/deployed_app/`) plus the **five Cortex Code skills** that drive it.
Contributions usually fall into: a skill improvement, a change to the demo's SQL/app, or a fix to the mock
API / seeder.

## Ground rules

- **Never commit secrets.** Snowflake credentials live in your local `~/.snowflake/connections.toml` and are
  read by the `snow` CLI. Connection files, `*.p8` keys, and `.env` files are git-ignored — keep it that way.
- **Synthetic data only.** All demo data is generated from `src/seeders/profiles_*.json`. Never commit real
  customer, employee, or client data.
- **Never overwrite `src/*.sql` from the live-API path.** The committed `src/02→05.sql` are the golden reference
  *and* the offline seeder runtime. CoCo's live build writes to the git-ignored `deployed_app/build/` instead.

## Local setup

```bash
pip install -r requirements.txt   # Faker only (the seeder engine)
```
`pandas`/`altair` are not needed locally — they run in Snowflake's Streamlit runtime.

## Authoring or changing a skill

Skills live under `.snowflake/cortex/skills/<skill-name>/SKILL.md` with a `references/` folder. Follow the
existing convention:

- YAML frontmatter with `name`, `description`, and a `tools:` list.
- Sections: `# When to Use`, `# Prerequisites`, `# Workflows`, `# Best Practices`, `# Examples` (the linter
  requires `When to Use` + `Workflows`).
- Put copy-paste SQL in `references/`; reference each file by its `references/<file>` path (the linter checks
  it exists).
- The DEMO build skills (`medallion-build`, `cortex-analyst-search`) must keep the **per-layer review hook** —
  generate → present → wait → run on approval.

Lint before opening a PR:
```bash
python3 tools/lint_skill.py .snowflake/cortex/skills/<skill-name>/SKILL.md
```

## Changing the demo schema

The medallion is described in several places that must stay in sync:

- `src/03_silver.sql` (typed tables + `SILVER_FIELD_MAP`) is authoritative for the entity schema. The mock API
  reads it via `mock_api/schema.py`, so an API change starts here.
- The seeder data brain is `src/seeders/profiles_omnihr.json` / `profiles_harvest.json`; the generation engine
  `src/seeders/_seedlib.py` is shared with the mock API (`mock_api/dataset.py`) — one engine, no drift.
- If you change the schema or a serializer, run the seeder self-test:
  `cd examples/hris_people/deployed_app/src/seeders && python3 seed_bronze.py --selftest`.
- Keep view names the app reads (`GOLD.EMPLOYEE_360`, `GOLD.HR_ANALYST`, `COMPANY_KB_SEARCH`, …) identical, or
  update `app/streamlit_app.py` to match.

## Pre-PR checklist

- [ ] `python3 tools/lint_skill.py` passes for any skill you touched.
- [ ] `python3 seed_bronze.py --selftest` passes if you touched the schema, profiles, serializers, or engine.
- [ ] `python3 -m py_compile` passes for any Python you touched (the apps can't run locally — they need Snowpark).
- [ ] No secrets, no real data, no credentials in the diff; no DEMO-generated SQL committed under `build/`.
