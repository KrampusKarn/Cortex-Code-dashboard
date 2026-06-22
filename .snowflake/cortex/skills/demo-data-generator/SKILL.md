---
name: demo-data-generator
description: Generate realistic, deterministic synthetic demo data from a validated schema_spec.json using templates/generator/generate_seed.py. Produces one seed CSV per table (the knowledge-base table is seeded from its curated source_json, chat tables are skipped). Covers the gen vocabulary, tuning realism with choices/weights/ranges/per_parent, keeping time-series current with relative date tokens and --today, and verifying row counts and determinism. Use after a schema_spec.json validates and before scaffolding the dashboard.
tools:
- read_file
- run_shell_command
---

# When to Use

- A `schema_spec.json` already validates (`python3 tools/validate_spec.py <spec>` exits 0) and you need demo CSVs.
- The user wants demo/sample data to stand up a dashboard **before** real API data has landed.
- The user asks to "generate the seed data", "make demo data", "populate the tables", or to tune the realism/volume of an existing dataset.
- Keywords: seed data, synthetic data, demo data, generate CSVs, Faker, row counts, mock data.

Do NOT use this skill to design the schema (that is `api-schema-extraction`) or to deploy (that is `dashboard-rag-scaffold`). This skill only turns a spec into CSVs.

# Prerequisites

1. A `schema_spec.json` that passes `python3 tools/validate_spec.py <spec>`.
2. The curated knowledge-base JSON referenced by `knowledge_base.source_json` must exist next to the spec — the KB table is seeded from it, not from Faker.
3. `Faker` installed (`pip install faker`). The generator is otherwise stdlib-only — **no pandas required**.

# Workflows

## 1. Validate the spec first

```bash
python3 tools/validate_spec.py path/to/schema_spec.json
```
Fix anything it reports. Generating from an invalid spec wastes a cycle.

## 2. Run the generator

```bash
python3 templates/generator/generate_seed.py \
    --spec path/to/schema_spec.json \
    --out  path/to/seed/ \
    --today 2026-06-22 \
    --seed 42
```

- `--spec` (required): the validated spec.
- `--out` (required): output directory for the CSVs (created if missing).
- `--today` (optional): the date that relative tokens (`today`, `-12m`, …) resolve against. **Omit it to use the real current date** — that is what keeps time-series data current. Pin it (e.g. `2026-06-22`) only when you want byte-stable committed sample data.
- `--seed` (optional, default 42): RNG seed. Same spec + same seed + same `--today` ⇒ identical CSVs.

What it does: resolves table order from `fk`/`per_parent` references, generates one CSV per table, seeds the **knowledge-base table from its `source_json`** (curated text), and **skips `is_chat_table` tables** (the app writes those at runtime). It prints a row count per table.

## 3. Tune realism

Edit the spec, not the CSVs. Common adjustments (see `references/gen_cheatsheet.md` for every `gen`):

- **Distributions**: give `choice` columns `weights` so values look real (most orders `Paid`, few `Overdue`).
- **Ranges**: set `int`/`float` `min`/`max` (and `round` for money) to business-plausible bounds.
- **Volume**: set `row_count` on primary/dimension tables; use `per_parent: {parent, min, max}` for child tables (e.g. 1–5 order lines per order).
- **Small dimension tables** with specific distinct values (the 3 business units, 5 departments): use `gen: "enumerate"` with `choices` and `row_count == len(choices)` so each row takes one value in order.
- **Keep data current**: prefer relative date tokens (`"-12m"`, `"today"`) on date columns so the latest month always has rows. (The original demo this kit is based on pinned its "today" in the past, leaving the current month empty and the MTD dashboard cards blank — relative tokens + default `--today` avoid that.)

See `references/recipes.md` for copy-paste table patterns (dimension, time-series, parent→child, knowledge base, chat tables).

## 4. Verify the output

- **Row counts**: the printed counts should match `row_count` (and child tables ≈ parents × avg(min,max)).
- **Headers match DDL**: CSV header columns equal the table's column names in order.
- **Currency**: confirm the latest period is present, e.g. the current month appears in your main fact table's date column.
- **Determinism**: re-run to a second directory with the same `--today`/`--seed` and `diff -r` — the CSVs must be identical.

# Best Practices

- **Spec is the source of truth** — never hand-edit generated CSVs; change the spec and regenerate.
- **Pin `--today` for committed sample data, omit it for live demos.** Document which you did.
- **Prefer bounded gens** (`choice`/`int`/`float`/`enumerate`/`template`) where a stable, realistic domain matters; reserve `faker` for free text (names, sentences, companies).
- **Model child arrays with `per_parent`**, not giant `row_count`s, so parent/child cardinality is realistic.
- **Don't seed chat tables** — they are `is_chat_table: true` (DDL only). Don't give them `row_count`/`per_parent`/`fk`.
- **The KB table is curated** — its content comes from `source_json`; its non-id columns can be `const ""` placeholders the loader overwrites.

# Examples

## Example 1: First generation

User: "The spec validates — make the demo data."

Agent: runs `python3 templates/generator/generate_seed.py --spec examples/hris_people/schema_spec.json --out examples/hris_people/seed --today 2026-06-22`, reads the printed row counts, confirms `BUSINESS_UNITS` is non-empty and `TIME_ENTRIES` contains the current month, then re-runs to `/tmp` and diffs to prove determinism.

## Example 2: "The current month is empty on the dashboard"

Agent: inspects the fact table's date column — it used a literal past `max` date. Switches it to `"max": "today"` (and `"min": "-12m"`), regenerates without `--today` so it resolves to the real date, and confirms the latest month now has rows.

## Example 3: "Too few line items per order"

Agent: the child table used a fixed `row_count`. Replaces it with `per_parent: {parent: "SALES_ORDERS", min: 1, max: 5}` and a `fk` column with `fk_strategy: "parent"`, regenerates, and verifies every parent id appears in the child CSV.

# References

- `references/gen_cheatsheet.md` — every `gen` strategy with a copy-paste column example and its params.
- `references/recipes.md` — full table patterns: dimension (enumerate), time-series (sequence_date / date), parent→child (per_parent), the curated knowledge base, and the chat tables.
