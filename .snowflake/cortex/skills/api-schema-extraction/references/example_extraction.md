# Worked example: sample JSON → schema_spec.json

A small end-to-end walkthrough. We start from a tiny sample response and end at a valid
`schema_spec.json` that passes `python3 tools/validate_spec.py`.

## Step 0 — the sample response

The user pastes one element of a `/v1/orders` response array:

```json
{
  "order_id": 1042,
  "status": "shipped",
  "total": 129.95,
  "created_at": "2026-05-30T14:11:02Z",
  "line_items": [
    { "sku": "TEE-BLK-M", "qty": 2, "unit_price": 24.99 },
    { "sku": "MUG-WHT",   "qty": 1, "unit_price": 9.99 }
  ]
}
```

## Step 1 — entities & grain

- The response array element is an **order** → table `ORDERS`, grain "one row per order", endpoint `/v1/orders`.
- `line_items` is an **array of child objects** → child table `ORDER_LINE_ITEMS`, grain "one row per line item", sized with `per_parent` and linked by `fk` to `ORDERS`.

## Step 2 — the 3 scalar fields of ORDERS → columns

(The minimal "3-field" mapping the task calls for; we also add the obvious pk.)

| JSON field | column name | type | gen | params |
|---|---|---|---|---|
| `order_id` | `ORDER_ID` | `NUMBER` | `row_index` | `pk: true` |
| `status` | `STATUS` | `VARCHAR` | `choice` | choices `["pending","shipped","delivered","cancelled"]`, weighted |
| `total` | `TOTAL` | `NUMBER(10,2)` | `float` | `min: 10, max: 500, round: 2` |
| `created_at` | `CREATED_AT` | `TIMESTAMP_NTZ` | `datetime` | `min: "-12m", max: "today"` |

## Step 3 — child table + inferred sizing

`ORDER_LINE_ITEMS`: `SKU` → `choice` over a small catalog; `QTY` → `int(1,5)`;
`UNIT_PRICE` → `float(5,100,2)`. Size with `per_parent: {parent:"ORDERS", min:1, max:6}`.
Give `ORDERS` a demo `row_count` of `400`.

## Step 4–5 — add KB + chat tables, fill app/dashboard

Add `KNOWLEDGE_BASE`, `CHAT_SESSIONS`, `CHAT_MESSAGES` (see `chat_tables.md`) and the
`knowledge_base`, `app`, and `dashboard` blocks.

## Resulting schema_spec.json (abridged)

```json
{
  "source": { "name": "Orders API", "description": "Sample /v1/orders endpoint" },
  "app": {
    "database": "ORDERS_DEMO",
    "schema": "PUBLIC",
    "warehouse": "COMPUTE_WH",
    "role": "SYSADMIN",
    "stage": "KIT_STAGE",
    "company_name": "Acme Commerce",
    "llm_model": "claude-3-5-sonnet",
    "embed_model": "snowflake-arctic-embed-m"
  },
  "tables": [
    {
      "name": "ORDERS",
      "grain": "One row per order",
      "endpoint": "/v1/orders",
      "row_count": 400,
      "columns": [
        { "name": "ORDER_ID", "type": "NUMBER", "gen": "row_index", "pk": true, "api_field": "order_id" },
        { "name": "STATUS", "type": "VARCHAR", "gen": "choice",
          "choices": ["pending", "shipped", "delivered", "cancelled"],
          "weights": [0.2, 0.3, 0.4, 0.1], "api_field": "status" },
        { "name": "TOTAL", "type": "NUMBER(10,2)", "gen": "float",
          "min": 10, "max": 500, "round": 2, "api_field": "total" },
        { "name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "gen": "datetime",
          "min": "-12m", "max": "today", "api_field": "created_at" }
      ]
    },
    {
      "name": "ORDER_LINE_ITEMS",
      "grain": "One row per order line item",
      "endpoint": "/v1/orders (line_items[])",
      "per_parent": { "parent": "ORDERS", "min": 1, "max": 6 },
      "columns": [
        { "name": "LINE_ITEM_ID", "type": "NUMBER", "gen": "row_index", "pk": true },
        { "name": "ORDER_ID", "type": "NUMBER", "gen": "fk",
          "ref_table": "ORDERS", "ref_column": "ORDER_ID", "fk_strategy": "per_parent" },
        { "name": "SKU", "type": "VARCHAR", "gen": "choice",
          "choices": ["TEE-BLK-M", "MUG-WHT", "CAP-RED", "BAG-CNV"], "api_field": "sku" },
        { "name": "QTY", "type": "NUMBER", "gen": "int", "min": 1, "max": 5, "api_field": "qty" },
        { "name": "UNIT_PRICE", "type": "NUMBER(10,2)", "gen": "float",
          "min": 5, "max": 100, "round": 2, "api_field": "unit_price" }
      ]
    },
    {
      "name": "KNOWLEDGE_BASE",
      "grain": "One knowledge article",
      "endpoint": "n/a (derived)",
      "row_count": 200,
      "columns": [
        { "name": "ARTICLE_ID", "type": "NUMBER", "gen": "row_index", "pk": true },
        { "name": "TITLE", "type": "VARCHAR", "gen": "faker", "faker_provider": "sentence" },
        { "name": "CONTENT", "type": "VARCHAR", "gen": "faker", "faker_provider": "paragraph" },
        { "name": "CATEGORY", "type": "VARCHAR", "gen": "choice",
          "choices": ["shipping", "returns", "billing", "product"],
          "weights": [0.3, 0.2, 0.2, 0.3] },
        { "name": "UPDATED_AT", "type": "TIMESTAMP_NTZ", "gen": "datetime", "min": "-1y", "max": "today" }
      ]
    },
    {
      "name": "CHAT_SESSIONS",
      "grain": "One chat session",
      "endpoint": "n/a (app-generated)",
      "is_chat_table": true,
      "row_count": 50,
      "columns": [
        { "name": "SESSION_ID", "type": "VARCHAR", "gen": "row_index", "pk": true },
        { "name": "USER_NAME", "type": "VARCHAR", "gen": "faker", "faker_provider": "name" },
        { "name": "STARTED_AT", "type": "TIMESTAMP_NTZ", "gen": "datetime", "min": "-90d", "max": "today" },
        { "name": "TITLE", "type": "VARCHAR", "gen": "faker", "faker_provider": "sentence" }
      ]
    },
    {
      "name": "CHAT_MESSAGES",
      "grain": "One message within a chat session",
      "endpoint": "n/a (app-generated)",
      "is_chat_table": true,
      "per_parent": { "parent": "CHAT_SESSIONS", "min": 2, "max": 12 },
      "columns": [
        { "name": "MESSAGE_ID", "type": "NUMBER", "gen": "row_index", "pk": true },
        { "name": "SESSION_ID", "type": "VARCHAR", "gen": "fk",
          "ref_table": "CHAT_SESSIONS", "ref_column": "SESSION_ID", "fk_strategy": "per_parent" },
        { "name": "ROLE", "type": "VARCHAR", "gen": "choice",
          "choices": ["user", "assistant"], "weights": [0.5, 0.5] },
        { "name": "CONTENT", "type": "VARCHAR", "gen": "faker", "faker_provider": "paragraph" },
        { "name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "gen": "sequence_date", "step": "+1m", "anchor": "-90d" }
      ]
    }
  ],
  "knowledge_base": {
    "table": "KNOWLEDGE_BASE",
    "content_col": "CONTENT",
    "attributes": ["CATEGORY", "TITLE"],
    "service_name": "KB_SEARCH_SERVICE",
    "source_json": "knowledge_base.json"
  },
  "dashboard": {
    "title": "Orders Intelligence",
    "icon": "📦",
    "suggested_prompts": [
      "How many orders shipped in the last 30 days?",
      "What is the average order total by status?",
      "Which SKUs sell the most units?",
      "Summarize our shipping and returns policy."
    ],
    "search_columns": ["STATUS", "SKU"],
    "search_limit": 10
  }
}
```

## Step 6 — validate

```bash
python3 tools/validate_spec.py schema_spec.json
# -> exit 0 when structure + semantics are valid
```

Fix anything reported (e.g. an `fk` whose `ref_column` doesn't exist, a `choice` with no
`choices`, a `knowledge_base.table` that isn't in `tables[]`) and re-run until clean.
