# Table recipes

Copy-paste patterns for the common table shapes. All identifiers UPPERCASE.

## Dimension table (specific distinct values)

Use `enumerate` so each row gets one value, in order. Set `row_count == len(choices)`.

```json
{
  "name": "DEPARTMENTS_DETAIL", "grain": "one row per department", "row_count": 5,
  "columns": [
    { "name": "DEPT_ID", "type": "NUMBER", "pk": true, "gen": "row_index" },
    { "name": "DEPT_NAME", "type": "VARCHAR(100)", "gen": "enumerate",
      "choices": ["Engineering", "Data & Analytics", "Delivery", "People & HR", "Sales"] },
    { "name": "BU_ID", "type": "NUMBER", "gen": "fk", "ref_table": "BUSINESS_UNITS" }
  ]
}
```

## Time-series / fact table (current through today)

Use a `date` column spanning `-12m`..`today` so the latest month always has rows.

```json
{
  "name": "TIME_ENTRIES", "grain": "one logged entry", "row_count": 2200,
  "columns": [
    { "name": "ENTRY_ID", "type": "NUMBER", "pk": true, "gen": "row_index" },
    { "name": "EMPLOYEE_ID", "type": "NUMBER", "gen": "fk", "ref_table": "EMPLOYEES" },
    { "name": "SPENT_DATE", "type": "DATE", "gen": "date", "min": "-12m", "max": "today" },
    { "name": "HOURS", "type": "FLOAT", "gen": "float", "min": 1.0, "max": 8.0, "round": 1 },
    { "name": "IS_BILLABLE", "type": "BOOLEAN", "gen": "bool", "p_true": 0.78 }
  ]
}
```

For one row per period (e.g. a monthly plan), use `sequence_date` and set `row_count` to the
number of periods:

```json
{ "name": "MONTH", "type": "DATE", "gen": "sequence_date", "step": "month", "anchor": "-12m" }
```

## Parent → child (per_parent)

The child table declares `per_parent` and a `fk` column with `fk_strategy: "parent"`. No
`row_count` on the child — each parent row gets `min`..`max` children.

```json
{
  "name": "SALES_ORDER_LINES", "grain": "one order line",
  "per_parent": { "parent": "SALES_ORDERS", "min": 1, "max": 5 },
  "columns": [
    { "name": "LINE_ID", "type": "NUMBER", "pk": true, "gen": "row_index" },
    { "name": "ORDER_ID", "type": "NUMBER", "gen": "fk", "fk_strategy": "parent", "ref_table": "SALES_ORDERS" },
    { "name": "PRODUCT_ID", "type": "NUMBER", "gen": "fk", "ref_table": "PRODUCTS" },
    { "name": "QUANTITY", "type": "NUMBER", "gen": "int", "min": 1, "max": 25 },
    { "name": "LINE_AMOUNT", "type": "FLOAT", "gen": "float", "min": 50, "max": 45000, "round": 2 }
  ]
}
```

## Knowledge base (seeded from curated JSON)

The KB table's rows come from `knowledge_base.source_json`, not Faker. Give non-id columns
`const ""` placeholders; the loader fills them from the JSON (keys matched to column names).

```json
{
  "name": "COMPANY_KNOWLEDGE_BASE", "grain": "one KB document", "row_count": 24,
  "columns": [
    { "name": "DOC_ID", "type": "NUMBER", "pk": true, "gen": "row_index" },
    { "name": "TITLE", "type": "VARCHAR(200)", "gen": "const", "value": "" },
    { "name": "CATEGORY", "type": "VARCHAR(80)", "gen": "const", "value": "" },
    { "name": "AUDIENCE", "type": "VARCHAR(40)", "gen": "const", "value": "" },
    { "name": "CONTENT", "type": "VARCHAR", "gen": "const", "value": "" }
  ]
}
```

## Chat tables (DDL only — the app writes the rows)

`is_chat_table: true` ⇒ the generator emits DDL but no rows. Autoincrement PK + timestamp
defaults; no `row_count`/`per_parent`/`fk`/Faker. Keep the column names exactly as below
(the Streamlit `rag_chat.py` reads/writes them).

```json
{
  "name": "CHAT_SESSIONS", "grain": "one chat conversation", "is_chat_table": true,
  "columns": [
    { "name": "SESSION_ID", "type": "NUMBER", "pk": true, "autoincrement": true, "gen": "row_index" },
    { "name": "USERNAME", "type": "VARCHAR(150)", "gen": "const", "value": "" },
    { "name": "SESSION_NAME", "type": "VARCHAR(200)", "gen": "const", "value": "" },
    { "name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "default": "CURRENT_TIMESTAMP()", "gen": "const", "value": "" },
    { "name": "LAST_ACTIVE", "type": "TIMESTAMP_NTZ", "default": "CURRENT_TIMESTAMP()", "gen": "const", "value": "" }
  ]
}
```

```json
{
  "name": "CHAT_MESSAGES", "grain": "one chat message", "is_chat_table": true,
  "columns": [
    { "name": "MESSAGE_ID", "type": "NUMBER", "pk": true, "autoincrement": true, "gen": "row_index" },
    { "name": "SESSION_ID", "type": "NUMBER", "gen": "const", "value": "" },
    { "name": "USERNAME", "type": "VARCHAR(150)", "gen": "const", "value": "" },
    { "name": "ROLE", "type": "VARCHAR(20)", "gen": "const", "value": "" },
    { "name": "CONTENT", "type": "VARCHAR", "gen": "const", "value": "" },
    { "name": "SOURCES", "type": "VARCHAR", "gen": "const", "value": "" },
    { "name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "default": "CURRENT_TIMESTAMP()", "gen": "const", "value": "" }
  ]
}
```
