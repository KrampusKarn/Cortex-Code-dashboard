# Contributing

> Stub — the full contributor guide lands with the docs unit.

## Ground rules

- **Never commit secrets.** This kit reads Snowflake credentials from your local
  `~/.snowflake/connections.toml` via the `snow` CLI. Connection files, `*.p8`
  keys, and `.env` files are git-ignored on purpose — keep it that way.
- **Synthetic data only.** Everything under `examples/*/generated/` is produced
  by the seed generator from a `schema_spec.json`. Do not commit real customer,
  employee, or client data.
- **Code against the contract.** Skills and examples must conform to
  [`docs/CONTRACT.md`](docs/CONTRACT.md) and validate against
  `templates/schema_spec.schema.json`.

## Adding a new data source

1. Use the `api-schema-extraction` skill to produce a `schema_spec.json`.
2. Validate it: `python tools/validate_spec.py path/to/schema_spec.json`.
3. Generate seed data with the `demo-data-generator` skill.
4. Scaffold + deploy with the `dashboard-rag-scaffold` skill.

## Authoring a new Cortex Code skill

Skills live under `.cortex/skills/<skill-name>/SKILL.md` with a `references/`
folder. Lint structure with `python tools/lint_skill.py <SKILL.md>`.
