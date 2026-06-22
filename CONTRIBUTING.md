# Contributing

Thanks for extending the Cortex Dashboard Kit. The kit is a set of Cortex Code skills plus
generalized templates; contributions usually fall into one of three buckets: a new data-source
example, an improvement to a skill, or a fix to the templates/tooling.

## Ground rules

- **Never commit secrets.** The kit reads Snowflake credentials from your local
  `~/.snowflake/connections.toml` via the `snow` CLI. Connection files, `*.p8` keys, and
  `.env` files are git-ignored on purpose — keep it that way. Don't add real credentials.
- **Synthetic data only.** Everything under `examples/*/seed/` is produced by the generator
  from a `schema_spec.json`. Never commit real customer, employee, or client data.
- **Code against the contract.** Specs must conform to [`docs/CONTRACT.md`](docs/CONTRACT.md)
  and validate against `templates/schema_spec.schema.json`.

## Local setup

```bash
pip install -r requirements.txt   # Faker + jsonschema
```
`pandas`/`altair` are not needed locally (they run in Snowflake's Streamlit runtime). The
generator and validators are stdlib + Faker only.

## Adding a new data source (the 3-skill flow)

1. **Extract** — use the `api-schema-extraction` skill (or hand-write) a `schema_spec.json`.
2. **Validate** — `python3 tools/validate_spec.py path/to/schema_spec.json` must exit 0.
3. **Generate** — `python3 templates/generator/generate_seed.py --spec <spec> --out <dir>`.
4. **Scaffold + deploy** — `python3 templates/render.py --spec <spec> --out <dir>` then the
   `dashboard-rag-scaffold` steps.

If you're contributing it as a new worked example, mirror the layout of
[`examples/hris_people`](examples/hris_people): `schema_spec.json`, `kb_content.json`,
`seed/`, `deploy/`, and `app/` (with domain dashboard tabs added to `streamlit_app.py`).

## Authoring or changing a skill

Skills live under `.snowflake/cortex/skills/<skill-name>/SKILL.md` with a `references/` folder.
Follow the existing convention:

- YAML frontmatter with `name`, `description`, and a `tools:` list.
- Sections: `# When to Use`, `# Prerequisites`, `# Workflows`, `# Best Practices`, `# Examples`.
- Put copy-paste material in `references/`; reference each file by its `references/<file>` path.

Lint structure before opening a PR:
```bash
python3 tools/lint_skill.py .snowflake/cortex/skills/<skill-name>/SKILL.md
```
Keep documented commands accurate to the real tool flags — re-read `templates/render.py` and
`templates/generator/generate_seed.py` if you change behavior.

## Changing the templates or contract

- If you add a `gen` strategy or a `schema_spec` field, update **all** of:
  `templates/schema_spec.schema.json`, `tools/validate_spec.py` (semantic checks),
  `templates/generator/generate_seed.py` and/or `templates/render.py`, and
  [`docs/CONTRACT.md`](docs/CONTRACT.md).
- Re-run both worked examples end to end (validate → generate → render → py_compile the apps)
  so they stay green.

## Pre-PR checklist

- [ ] `python3 tools/validate_spec.py` passes for any spec you touched.
- [ ] `python3 tools/lint_skill.py` passes for any skill you touched.
- [ ] Generators run cleanly and re-running is deterministic (`diff -r`).
- [ ] `python3 -m py_compile` passes for any Python you touched.
- [ ] No secrets, no real data, no credentials in the diff.
