---
name: api-schema-extraction
description: Turn API documentation or a sample JSON response into a valid schema_spec.json for the Cortex Dashboard Kit. Identifies entities and grain from a payload, maps each JSON field to a Snowflake column type and a generator (gen) strategy, infers realistic choices/ranges/row_counts, always wires in a knowledge_base table plus CHAT_SESSIONS/CHAT_MESSAGES so the Cortex RAG chat works, fills the app/dashboard blocks, and validates with tools/validate_spec.py. Use when a user wants a Snowflake dashboard for a new API source and has docs or a sample payload.
tools:
- read_file
- write_file
- run_shell_command
---

# When to Use

- User wants to stand up a Snowflake dashboard + Cortex RAG chat for a **new API source**.
- User provides an **API documentation URL**, an OpenAPI/Swagger spec, or a **sample JSON response** (a payload they pasted, a `curl` output, or an example from docs).
- User says things like "build a dashboard for the Stripe charges API", "here's a sample response from our orders endpoint, make me a dashboard", or "I have docs for this weather API — set up the kit".
- Keywords: API, endpoint, sample response, JSON payload, OpenAPI, Swagger, "build a dashboard for", schema_spec, new data source.

Do NOT use this skill to write deploy SQL or the Streamlit app directly — this skill produces only `schema_spec.json`. The kit's generator and `render.py` consume that spec to produce seed CSVs, deploy SQL, and the RAG app.

# Prerequisites

1. **A sample of the data shape.** One of:
   - A sample JSON response (best — copy/paste it or save to a file), OR
   - An API docs / OpenAPI URL describing the response objects and fields.
   If the user has neither, ask for one before proceeding. Do not invent fields.
2. **The kit contract.** Read `docs/CONTRACT.md` and `templates/schema_spec.schema.json` in the repo root FIRST — they are authoritative. This skill summarizes them but the repo copies win on any conflict.
3. **The validator.** `tools/validate_spec.py` must be runnable: `python3 tools/validate_spec.py <spec.json>`. The environment is system `python3` (3.9), with Faker installed and NO pandas/jsonschema (the validator falls back to structural + semantic checks when jsonschema is absent).

# Workflows

Follow these in order. Each step builds the spec incrementally; validate at the end.

## 1. Inspect the payload → identify entities and grain

- If given a URL, fetch the docs / sample response. If given raw JSON, read it directly.
- Find the **top-level response array** (or the array under a wrapper key like `data`, `results`, `items`). Each element of that array is **one row** of the primary table. That element's shape defines the **grain** (one row per what?).
- Each distinct **entity** in the payload becomes a **table** (`name` UPPERCASE). Signals an object is its own entity:
  - It is the element type of the response array (→ the primary table).
  - It is an **array of child objects** nested under a parent (→ a child table linked by `fk`, sized with `per_parent`).
  - It is a repeated reference object that deserves its own dimension (e.g. `customer`, `product`) — promote to a table when the same object recurs across rows.
- Write down: table name, one-line `grain`, the source `endpoint`, and whether row count is fixed (`row_count`) or derived from a parent (`per_parent`).

See `references/example_extraction.md` for a full worked walkthrough.

## 2. Map each JSON field → Snowflake column TYPE + gen strategy

For every leaf field in an entity, produce a column: `{ "name": UPPERCASE, "type": <Snowflake type>, "gen": <strategy>, ...params }`.

Use the mapping table in `references/type_mapping.md`. Quick reference:

| JSON value | Snowflake `type` | `gen` strategy |
|---|---|---|
| id / primary key | `NUMBER` or `VARCHAR` | `row_index` (set `pk: true`) |
| foreign key to another entity | match parent pk type | `fk(ref_table, ref_column, fk_strategy)` |
| short string, low cardinality (status, category) | `VARCHAR` | `choice(choices, weights)` |
| free-text name / company | `VARCHAR` | `faker(faker_provider)` |
| email | `VARCHAR` | `template("{FIRST_NAME\|lower}@x.com")` or `faker("email")` |
| integer (count, qty) | `NUMBER` | `int(min, max)` |
| decimal / money | `NUMBER(p,s)` or `FLOAT` | `float(min, max, round)` |
| boolean | `BOOLEAN` | `bool(p_true)` |
| ISO date `2026-06-21` | `DATE` | `date(min, max)` |
| ISO datetime / timestamp | `TIMESTAMP_NTZ` | `datetime` or `sequence_date(step, anchor)` |
| constant / enum-of-one | (its type) | `const(value)` |
| nested object `{...}` | flatten to scalar columns **or** `VARIANT` | per child field, or `const`/`faker` for VARIANT |
| array of child objects `[{...}]` | (no column) | model as a **child table** with `per_parent` |
| array of scalars | `VARIANT` or `ARRAY` | `const(value)` (small fixed list) |

Notes:
- Date/datetime params accept relative tokens: `"today"`, `"-5y"`, `"+12m"`, `"-90d"`. Prefer these over hardcoded dates so demo data stays current.
- Column extras available: `pk`, `nullable`, `autoincrement`, `default`, `api_field` (the original JSON field name), `null_pct`.
- Record the original JSON field name in `api_field` so the lineage from payload → column is traceable.

## 3. Infer realistic choices/weights, ranges, and row_count

The payload shows shape, not realistic distributions — infer those:

- **choice**: pull the enum from docs if listed (e.g. status `["active","past_due","canceled"]`); otherwise infer sensible values. Add `weights` that reflect reality (most subscriptions `active`, few `canceled`).
- **int/float ranges**: pick plausible business ranges (order total `float(5, 500, 2)`, age `int(18, 90)`). Use `round` for money (`2`).
- **row_count**: primary tables get a demo-friendly count (e.g. 200–2000). Child tables use `per_parent: {parent, min, max}` so each parent gets a realistic number of children (e.g. 1–5 line items per order).
- Keep gens **deterministic-friendly**: prefer `choice`, `int`, `float`, `date`, `template`, `row_index` over high-entropy faker where a bounded set is more demo-stable.

## 4. Always add the knowledge base + chat tables (so RAG chat works)

The Cortex RAG chat is the point of the kit. Every spec MUST include:

- **A knowledge_base table** — a text-bearing table the Cortex Search service indexes. Often this is (or derives from) the primary entity with a rich text column, or a dedicated `KNOWLEDGE_BASE`/`ARTICLES` table with a `CONTENT` column. Then fill the top-level `knowledge_base` block: `table`, `content_col`, `attributes[]` (filterable columns), `service_name`, `source_json`.
- **CHAT_SESSIONS** and **CHAT_MESSAGES** tables, each with `is_chat_table: true`. The app WRITES these at runtime, so the generator emits only their DDL (no rows) — they need an `autoincrement` PK and timestamp `default`s, but NO `row_count`, `per_parent`, `fk`, or Faker. Use the canonical column shapes in `references/chat_tables.md` — copy them verbatim and adapt only the database/schema context.

## 5. Fill the app and dashboard blocks

- **app**: `database`, `schema`, `warehouse`, `role`, `stage`, `company_name`, `llm_model`, `embed_model`. Use UPPERCASE Snowflake identifiers. Prefer the built-in `SYSADMIN` role for demo work unless the user specifies otherwise. Pick a current Cortex `llm_model` (e.g. a Claude model available in Cortex) and a supported `embed_model`.
- **dashboard**: `title`, `icon` (emoji), `suggested_prompts[]` (3–6 questions a user would ask the RAG chat about this data), `search_columns[]` (columns the dashboard search box queries), `search_limit` (e.g. 10).
- **source**: name/description of the API source for provenance.

## 6. Validate

Run the validator and fix everything it reports before handing the spec off:

```bash
python3 tools/validate_spec.py path/to/schema_spec.json
```

- It checks structure (required keys, table/column shapes) and semantics (fk refs resolve, gen params present, chat tables exist, knowledge_base.table points at a real table).
- If `jsonschema` is installed it also validates against `templates/schema_spec.schema.json`; if not, it falls back to the built-in structural + semantic checks. Either way, exit 0 = valid.
- Re-run until it passes cleanly. Only then is the spec ready for the generator + `render.py`.

# Best Practices

- **UPPERCASE** all table and column `name` values (Snowflake identifiers); keep `api_field` in the original JSON casing for lineage.
- **Deterministic-friendly gens**: prefer `choice`/`int`/`float`/`date`/`row_index`/`template` over open-ended faker when a bounded domain produces more stable demos.
- **Model child arrays as child tables** with `per_parent`, not as VARIANT blobs — this makes the data queryable and the dashboard richer.
- **Mark id / email / name fields**: ids get `pk: true` + `row_index`; emails use `template`/`faker("email")`; names use `faker`. This keeps generated data coherent (email derived from name via `template`).
- **Keep data current** with relative date tokens (`today`, `-90d`, `+12m`) instead of literal dates, so the demo never looks stale.
- **Always include** a knowledge_base table + CHAT_SESSIONS + CHAT_MESSAGES (`is_chat_table: true`) — the RAG chat fails without them.
- **One grain per table.** If a payload mixes grains (order header + line items in one object), split into parent + child tables.
- **Don't invent fields.** Map only what the payload/docs show; infer distributions and ranges, not the existence of fields.
- **Validate before declaring done.** A spec that has not passed `tools/validate_spec.py` is not finished.

# Examples

## Example 1: Sample JSON response for a new API

User: "Here's a sample response from our subscriptions API — build me a dashboard." (pastes JSON with `id`, `customer_email`, `status`, `amount`, `created`, and a `items` array)

Agent:
1. Identifies the response array element as the `SUBSCRIPTIONS` table (grain: one row per subscription); the `items` array becomes a `SUBSCRIPTION_ITEMS` child table with `per_parent`.
2. Maps fields: `id`→NUMBER `row_index` pk; `customer_email`→VARCHAR `template("{FIRST_NAME|lower}@x.com")`; `status`→VARCHAR `choice(["active","past_due","canceled"],[0.8,0.12,0.08])`; `amount`→NUMBER(10,2) `float(5,500,2)`; `created`→TIMESTAMP_NTZ `datetime` over `-12m`..`today`.
3. Sets `row_count: 500` for SUBSCRIPTIONS; `per_parent:{parent:"SUBSCRIPTIONS", min:1, max:4}` for items.
4. Adds a `KNOWLEDGE_BASE` table with a `CONTENT` text column + CHAT_SESSIONS/CHAT_MESSAGES (`is_chat_table:true`), wires the `knowledge_base` block.
5. Fills `app` (SYSADMIN role, Cortex models) and `dashboard` (title, icon, suggested_prompts about churn/MRR, search_columns).
6. Runs `python3 tools/validate_spec.py schema_spec.json`, fixes any errors, confirms exit 0.

## Example 2: Only an API docs URL

User: "Build a dashboard for the OpenWeather current-weather API." (gives docs URL, no payload)

Agent: Fetches the docs, reconstructs the response object's fields and types from the schema/examples, then runs the same 6 workflows. Where the docs list enumerations (e.g. weather `main` values), uses them as `choice` choices; where they give units/ranges, uses them for `int`/`float` bounds.

## Example 3: Array of children needs a child table

User: "Our orders endpoint returns each order with a `line_items` array."

Agent: Creates `ORDERS` (grain: one order) and `ORDER_LINE_ITEMS` (grain: one line item), links them with `fk(ref_table:"ORDERS", ref_column:"ORDER_ID", fk_strategy:...)`, and sizes line items with `per_parent:{parent:"ORDERS", min:1, max:8}` — rather than stuffing line items into a VARIANT column.

# References

- `references/type_mapping.md` — full JSON-type → (Snowflake type, gen strategy) mapping with the complete `gen` vocabulary and parameters.
- `references/example_extraction.md` — a 3-field sample JSON walked end-to-end into a `schema_spec.json` snippet.
- `references/chat_tables.md` — canonical CHAT_SESSIONS / CHAT_MESSAGES table definitions and the `knowledge_base` block to copy in.
