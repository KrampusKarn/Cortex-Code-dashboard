# The Contract — `schema_spec.json`

Everything in this kit is held together by **one artifact**: a `schema_spec.json` file
that describes a data source as a set of logical tables plus the Snowflake/app identity
and the RAG knowledge base.

```
api-schema-extraction  ──produces──▶  schema_spec.json  ──consumed by──▶  demo-data-generator
                                              │                                    │
                                              └──────────consumed by──────────▶  dashboard-rag-scaffold
```

If a skill or example conforms to this document and validates against
`templates/schema_spec.schema.json`, it composes with the rest of the kit.
**Validate any spec with:** `python tools/validate_spec.py path/to/schema_spec.json`

---

## Top-level shape

| Key | Required | Purpose |
|---|---|---|
| `spec_version` | no | Contract version (default `"1.0"`). |
| `source` | yes | The upstream API this demo imitates (name, base_url, docs_url, auth). Informational, but drives the "port to real data" story. |
| `app` | yes | Snowflake + app identity. **The single source of truth** for object names — no hardcoding elsewhere. |
| `tables` | yes | Logical tables to create + seed. |
| `knowledge_base` | yes | The corpus the Cortex Search service indexes for RAG. |
| `dashboard` | yes | Streamlit + RAG presentation config. |

### `app` — kills all hardcoding
```jsonc
"app": {
  "database": "DEMO_EMPLOYEE_APP",
  "schema": "PUBLIC",
  "warehouse": "DEMO_WH",          // ONE warehouse name, used by deploy + load + Cortex Search + Streamlit
  "role": "SYSADMIN",
  "stage": "DEMO_SEED_STAGE",
  "company_name": "Acme Solutions Inc",
  "llm_model": "mistral-large2",
  "embed_model": "snowflake-arctic-embed-m-v1.5"
}
```
> ⚠️ **Lesson baked in:** the original demo drifted between `DEMO_EMPLOYEE_WH` (scripts) and
> `DEMO_EMPLOYEE_APP` (live), which silently broke deploys. Here, `app.warehouse` is the
> *only* place a warehouse name appears. Every template reads it.

### `knowledge_base` — the RAG corpus
```jsonc
"knowledge_base": {
  "table": "COMPANY_KNOWLEDGE_BASE",   // must also be listed in `tables`
  "content_col": "CONTENT",            // the column Cortex Search indexes (ON clause)
  "attributes": ["CATEGORY", "TITLE", "AUDIENCE"],
  "service_name": "COMPANY_KB_SEARCH",
  "target_lag": "1 hour",
  "source_json": "kb_content.json"     // path (relative to the spec) to an array of KB rows
}
```

### `dashboard` — presentation
```jsonc
"dashboard": {
  "title": "Employee 360",
  "icon": "👥",
  "assistant_intro": "Ask me about company info, benefits, and events.",
  "chat_placeholder": "Ask about company info, benefits, events...",
  "suggested_prompts": ["What health plans do we offer?", "Upcoming events?", "PTO policy?"],
  "search_columns": ["CONTENT", "TITLE", "CATEGORY"],
  "search_limit": 3
}
```

---

## Tables

```jsonc
{
  "name": "EMPLOYEES",                         // UPPERCASE identifier
  "grain": "one row per employee",             // one sentence
  "endpoint": "GET /api/v1/employees",         // informational
  "row_count": 50,                             // fixed N rows ...
  // ... OR, for child tables, generate a variable number per parent:
  "per_parent": { "parent": "SALES_ORDERS", "min": 1, "max": 5 },
  "is_chat_table": false,                      // true for CHAT_SESSIONS/CHAT_MESSAGES → DDL only, no seed
  "columns": [ ... ]
}
```

- Provide **exactly one** of `row_count` or `per_parent`.
- A table with `per_parent` implies a foreign key to its parent — give it an `fk` column
  with `"fk_strategy": "parent"`.
- Mark `CHAT_SESSIONS` and `CHAT_MESSAGES` with `"is_chat_table": true`: their DDL is emitted
  but the generator produces **no rows** (the Streamlit app writes them at runtime).
- Generation order is resolved automatically from `fk` / `per_parent` references — declare
  tables in any order.

---

## Columns and the `gen` vocabulary

Every column needs `name`, `type` (a Snowflake type string), and `gen`. Common optional
fields: `pk`, `nullable`, `api_field`, `comment`, `null_pct` (probability of NULL).

| `gen` | Produces | Key params |
|---|---|---|
| `row_index` | 1-based sequential integer | — (use for PKs) |
| `const` | a fixed value | `value` |
| `fk` | a foreign-key value | `ref_table`, `ref_column` (default = ref table's pk), `fk_strategy` (`random`\|`sequential`\|`parent`) |
| `choice` | a value picked from a list | `choices`, optional `weights` |
| `enumerate` | ordered, distinct values for a small dimension table (row N → `choices[N]`) | `choices` (set `row_count` == `len(choices)`) |
| `int` | random integer in range | `min`, `max` |
| `float` | random float in range | `min`, `max`, optional `round` |
| `bool` | TRUE/FALSE | `p_true` (default 0.5) |
| `date` | random date in range | `min`, `max` (ISO or relative tokens), optional `format` |
| `datetime` | random timestamp in range | `min`, `max`, optional `format` |
| `sequence_date` | a regular series (1 row = 1 period) | `step` (`day`\|`week`\|`month`), `anchor`, plus the table's `row_count` periods |
| `template` | a string from other columns in the row | `template` (e.g. `"{FIRST_NAME}.{LAST_NAME}@acme.com"`; supports `{COL\|lower}`) |
| `faker` | any Faker provider | `faker_provider` (e.g. `first_name`, `email`, `company`, `city`, `bothify`) |

### Relative date tokens
`min`/`max`/`anchor` for dates accept ISO (`"2025-01-01"`) **or** tokens relative to the
generator's `TODAY`: `"today"`, `"-5y"`, `"-90d"`, `"+12m"`. This is how a spec stays
"current" — see the currency note below.

### Example column set
```jsonc
"columns": [
  { "name": "EMPLOYEE_ID", "type": "NUMBER", "pk": true, "gen": "row_index", "api_field": "id" },
  { "name": "FIRST_NAME", "type": "VARCHAR(80)", "gen": "faker", "faker_provider": "first_name" },
  { "name": "EMAIL", "type": "VARCHAR(150)", "gen": "template",
    "template": "{FIRST_NAME|lower}.{LAST_NAME|lower}@acme.com", "api_field": "official_email" },
  { "name": "EMPLOYMENT_TYPE", "type": "VARCHAR(40)", "gen": "choice",
    "choices": ["Full-time", "Contractor", "Managed Workforce"], "weights": [0.78, 0.16, 0.06] },
  { "name": "HIRE_DATE", "type": "DATE", "gen": "date", "min": "-5y", "max": "today" },
  { "name": "BUSINESS_UNIT_ID", "type": "NUMBER", "gen": "fk", "ref_table": "BUSINESS_UNITS" }
]
```

---

## App config (consumed by the Streamlit app)

The scaffold renders `templates/app/app_config.py` from `app` + `dashboard` + `knowledge_base`.
The app reads **only** from this module — never inline literals:

```python
DATABASE        = "DEMO_EMPLOYEE_APP"
SCHEMA          = "PUBLIC"
SERVICE_FQN     = "DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_KB_SEARCH"
KB_TABLE        = "COMPANY_KNOWLEDGE_BASE"
LLM_MODEL       = "mistral-large2"
COMPANY_NAME    = "Acme Solutions Inc"
APP_TITLE       = "Employee 360"
APP_ICON        = "👥"
SUGGESTED_PROMPTS = ["What health plans do we offer?", "Upcoming events?", "PTO policy?"]
SEARCH_COLUMNS  = ["CONTENT", "TITLE", "CATEGORY"]
SEARCH_LIMIT    = 3
```

---

## Non-negotiable conventions

1. **UPPERCASE** table and column identifiers (Snowflake-idiomatic, matches the queries).
2. **Determinism:** the generator seeds `random`/`Faker` from a fixed `SEED` so reruns are byte-stable.
3. **Currency:** the generator's `TODAY` **defaults to the real current date** (override with `--today`).
   Use relative date tokens so time-series tables always include the current period — this avoids
   the original demo's "empty current month" bug (its `TODAY` was pinned in the past).
4. **One warehouse name** (`app.warehouse`) everywhere.
5. **Post-load verification:** the loader asserts each table's row count after `COPY INTO`
   (the original demo silently shipped two empty lookup tables — never again).
6. **Parameterized SQL only** in the app: all writes to `CHAT_*` use `params=[...]`, never
   f-string interpolation of user/LLM content.
7. **Synthetic data only** under `examples/*/generated/`.
