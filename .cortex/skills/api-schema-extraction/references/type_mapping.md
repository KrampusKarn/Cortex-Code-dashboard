# JSON field → Snowflake type + gen strategy

Use this when mapping each leaf field of an API payload to a `schema_spec.json` column.
The repo's `docs/CONTRACT.md` and `templates/schema_spec.schema.json` are authoritative; this is a working summary.

## Mapping table

| JSON value (in payload/docs) | Snowflake `type` | `gen` | Typical params |
|---|---|---|---|
| Primary id (`id`, `order_id`) | `NUMBER` (numeric ids) or `VARCHAR` (opaque/uuid ids) | `row_index` | set `pk: true` |
| Auto-increment surrogate key | `NUMBER` | `row_index` | `pk: true`, optionally `autoincrement: true` |
| Foreign key (id pointing at another entity) | match the referenced pk's type | `fk` | `ref_table`, `ref_column`, `fk_strategy` |
| Low-cardinality string (status, tier, category, country code) | `VARCHAR` | `choice` | `choices: [...]`, `weights: [...]` (weights optional) |
| Free-text person/company name | `VARCHAR` | `faker` | `faker_provider: "name"` / `"company"` / `"first_name"` |
| Email | `VARCHAR` | `template` or `faker` | `template: "{FIRST_NAME\|lower}@x.com"` or `faker_provider: "email"` |
| Phone, address, url, etc. | `VARCHAR` | `faker` | matching `faker_provider` (`phone_number`, `address`, `url`) |
| Long free text / description / body | `VARCHAR` or `TEXT` | `faker` | `faker_provider: "paragraph"` / `"sentence"` |
| Integer count / quantity | `NUMBER` | `int` | `min`, `max` |
| Decimal money / price / amount | `NUMBER(p,s)` (e.g. `NUMBER(10,2)`) or `FLOAT` | `float` | `min`, `max`, `round` (2 for money) |
| Ratio / rate / score | `FLOAT` | `float` | `min`, `max`, `round` |
| Boolean / flag | `BOOLEAN` | `bool` | `p_true` (e.g. `0.7`) |
| ISO date (`"2026-06-21"`) | `DATE` | `date` | `min`, `max` (relative tokens OK) |
| ISO datetime / timestamp (`"2026-06-21T10:00:00Z"`, epoch) | `TIMESTAMP_NTZ` | `datetime` | optional `min`/`max` |
| Ordered/sequential timestamp (events over time) | `TIMESTAMP_NTZ` | `sequence_date` | `step` (e.g. `"+1d"`), `anchor` (e.g. `"-90d"`) |
| Always-the-same / single-value enum | (its scalar type) | `const` | `value` |
| Nested object `{...}` | flatten each child field to its own column, **or** keep as `VARIANT` | per-field gens, or `const`/`faker` for the VARIANT | — |
| Array of child objects `[{...}, ...]` | (NO column on the parent) | model as a **child table** | child table uses `per_parent: {parent, min, max}` + `fk` back to parent |
| Array of scalars (`["a","b"]`) | `VARIANT` or `ARRAY` | `const` (small fixed list) or flatten to a child table | — |
| `null` / unknown / optional | infer from a non-null sample; mark | any | add `nullable: true` and/or `null_pct` |

## Full `gen` vocabulary (and params)

| `gen` | Purpose | Params |
|---|---|---|
| `row_index` | sequential integer per row (great for pks) | — (pair with `pk: true`) |
| `const` | fixed literal for every row | `value` |
| `fk` | foreign key into another table | `ref_table`, `ref_column`, `fk_strategy` |
| `choice` | pick from a fixed set | `choices: [...]`, optional `weights: [...]` (same length as choices) |
| `int` | random integer in range | `min`, `max` |
| `float` | random float in range | `min`, `max`, optional `round` |
| `bool` | random boolean | `p_true` (probability of `true`) |
| `date` | random date in range | `min`, `max` (relative tokens OK) |
| `datetime` | random timestamp | optional `min`, `max` |
| `sequence_date` | stepped timestamp from an anchor | `step` (e.g. `"+1d"`, `"+1h"`), `anchor` (e.g. `"-1y"`) |
| `template` | string built from other column values + transforms | `template` (e.g. `"{FIRST_NAME\|lower}.{LAST_NAME\|lower}@x.com"`) |
| `faker` | a Faker provider value | `faker_provider` (e.g. `"name"`, `"email"`, `"company"`, `"city"`) |

### Relative date tokens

`date`, `datetime`, and `sequence_date` accept relative tokens anywhere a date is expected:
`"today"`, `"-5y"` (5 years ago), `"+12m"` (12 months ahead), `"-90d"` (90 days ago).
Prefer these over literal dates so demo data stays current.

### Column-level keys (besides name/type/gen + gen params)

`pk`, `nullable`, `autoincrement`, `default`, `api_field` (original JSON field name, for lineage), `null_pct`.

## Decision tips

- **Numeric id that is referenced elsewhere** → `row_index` + `pk: true` on the owner; `fk` on the referencer.
- **String field with only a handful of distinct values across the sample** → `choice` (lift the enum from the docs if listed).
- **Anything money** → `float` with `round: 2`, or `NUMBER(p,s)`.
- **A field that is itself a list of objects** → never a column; it is a child table sized by `per_parent`.
- **A field present in some objects but not others** → `nullable: true` + a sensible `null_pct`.
