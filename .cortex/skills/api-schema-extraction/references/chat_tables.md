# Knowledge base + chat tables (required for the RAG chat)

Every `schema_spec.json` MUST include a knowledge_base table plus `CHAT_SESSIONS` and
`CHAT_MESSAGES` (both `is_chat_table: true`). The Cortex RAG chat does not work without them.
Copy these blocks and adapt only names/grain to the source; keep the structure.

## 1. The knowledge base table

This is the text-bearing table the Cortex Search service indexes. **Its rows are seeded
from a curated JSON file (`knowledge_base.source_json`), NOT from Faker** — that file is the
real text the RAG retrieves. The generator maps each JSON object's keys to columns by name;
an id column with `gen: "row_index"` becomes the 1-based id. So give the non-id columns
`gen: "const", "value": ""` placeholders — the loader overwrites them from the JSON.

```json
{
  "name": "COMPANY_KNOWLEDGE_BASE",
  "grain": "one row per knowledge-base document",
  "endpoint": "internal wiki export",
  "row_count": 24,
  "columns": [
    { "name": "DOC_ID",   "type": "NUMBER",       "pk": true, "gen": "row_index" },
    { "name": "TITLE",    "type": "VARCHAR(200)", "gen": "const", "value": "" },
    { "name": "CATEGORY", "type": "VARCHAR(80)",  "gen": "const", "value": "" },
    { "name": "AUDIENCE", "type": "VARCHAR(40)",  "gen": "const", "value": "" },
    { "name": "CONTENT",  "type": "VARCHAR",      "gen": "const", "value": "" }
  ]
}
```

Top-level `knowledge_base` block (its `source_json` is an array of objects whose keys match
the columns above, e.g. `[{ "TITLE": "...", "CATEGORY": "...", "AUDIENCE": "...", "CONTENT": "..." }]`):

```json
"knowledge_base": {
  "table": "COMPANY_KNOWLEDGE_BASE",
  "content_col": "CONTENT",
  "attributes": ["CATEGORY", "TITLE", "AUDIENCE"],
  "service_name": "COMPANY_KB_SEARCH",
  "target_lag": "1 hour",
  "source_json": "kb_content.json"
}
```

`table` must point at a real table in `tables[]`; `content_col` must be a column on it
(the Cortex Search `ON` column); `attributes` are columns returned alongside content.

## 2. CHAT_SESSIONS and CHAT_MESSAGES (`is_chat_table: true` — DDL only)

The app WRITES these at runtime, so the generator produces **no rows** for them — it only
emits their DDL. Therefore: no `row_count`, no `per_parent`, no `fk`, no Faker. The PK is
`autoincrement` (the app inserts without supplying an id) and timestamps get a SQL `default`.
The `gen`/`value` on each column is a required-by-contract placeholder that is never executed.

```json
{
  "name": "CHAT_SESSIONS",
  "grain": "one row per chat conversation (written by the app)",
  "is_chat_table": true,
  "columns": [
    { "name": "SESSION_ID",  "type": "NUMBER",        "pk": true, "autoincrement": true, "gen": "row_index" },
    { "name": "USERNAME",     "type": "VARCHAR(150)",  "gen": "const", "value": "" },
    { "name": "SESSION_NAME", "type": "VARCHAR(200)",  "gen": "const", "value": "" },
    { "name": "CREATED_AT",   "type": "TIMESTAMP_NTZ", "default": "CURRENT_TIMESTAMP()", "gen": "const", "value": "" },
    { "name": "LAST_ACTIVE",  "type": "TIMESTAMP_NTZ", "default": "CURRENT_TIMESTAMP()", "gen": "const", "value": "" }
  ]
}
```

```json
{
  "name": "CHAT_MESSAGES",
  "grain": "one row per chat message (written by the app)",
  "is_chat_table": true,
  "columns": [
    { "name": "MESSAGE_ID", "type": "NUMBER",        "pk": true, "autoincrement": true, "gen": "row_index" },
    { "name": "SESSION_ID", "type": "NUMBER",        "gen": "const", "value": "" },
    { "name": "USERNAME",   "type": "VARCHAR(150)",  "gen": "const", "value": "" },
    { "name": "ROLE",       "type": "VARCHAR(20)",   "gen": "const", "value": "" },
    { "name": "CONTENT",    "type": "VARCHAR",       "gen": "const", "value": "" },
    { "name": "SOURCES",    "type": "VARCHAR",       "gen": "const", "value": "" },
    { "name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "default": "CURRENT_TIMESTAMP()", "gen": "const", "value": "" }
  ]
}
```

The Streamlit `rag_chat.py` module expects exactly these column names (SESSION_ID, USERNAME,
SESSION_NAME, LAST_ACTIVE on sessions; SESSION_ID, USERNAME, ROLE, CONTENT, SOURCES on
messages) — keep them.

## Checklist

- [ ] Exactly one knowledge_base table, with a long-text `content_col`, seeded from `source_json`.
- [ ] Top-level `knowledge_base` block points at it (`table`, `content_col`, `attributes`, `service_name`, `source_json`).
- [ ] `CHAT_SESSIONS` present, `is_chat_table: true`, `autoincrement` PK, timestamp `default`s. No per_parent/fk/Faker.
- [ ] `CHAT_MESSAGES` present, `is_chat_table: true`, `autoincrement` PK. Column names match what `rag_chat.py` reads/writes.
- [ ] All names UPPERCASE.
