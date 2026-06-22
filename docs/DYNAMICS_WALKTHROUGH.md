# Walkthrough: a Microsoft Dynamics ERP dashboard from an OData response

This walks the full pipeline on a Microsoft Dynamics 365 Business Central sample, ending at
the finished [`examples/dynamics_erp`](../examples/dynamics_erp). It highlights the one thing
ERP data adds over the HR example: **parent → child modeling** (a sales order and its line
items) via `per_parent`.

## 0. The source: an OData response

Dynamics 365 Business Central exposes OData. A `salesOrders` response is an envelope with a
`value` array, and each order embeds a `salesOrderLines` array. A representative response looks like:

```jsonc
{
  "@odata.context": "...",
  "value": [
    {
      "id": "…", "number": "SO-1001", "orderDate": "2026-05-12",
      "customerNumber": "C10", "status": "Released", "currencyCode": "SGD",
      "totalAmountExcludingTax": 12500.00, "totalAmountIncludingTax": 13375.00,
      "salesOrderLines": [
        { "lineType": "Item", "itemId": "…", "quantity": 5, "unitPrice": 1200, "lineAmount": 6000 },
        ...
      ]
    }
  ]
}
```

## 1. Extract → `schema_spec.json` (skill: `api-schema-extraction`)

Hand Cortex Code a sample `salesOrders` response (like the one above — from your Dynamics 365
OData endpoint or its API docs). Key extraction decisions:

- The `value` array element is the **`SALES_ORDERS`** table (grain: one order header). The OData
  envelope (`@odata.context`, paging) is metadata, not a table.
- `salesOrderLines[]` is an **array of child objects** → its own table **`SALES_ORDER_LINES`**,
  linked to the parent. This is the crucial move: model it as a child table, **not** a VARIANT blob.
- Recurring reference entities become dimension tables: **`CUSTOMERS`**, **`PRODUCTS`**, **`VENDORS`**.
- Add the finance facts the dashboard needs: **`INVOICES`**, **`GL_ENTRIES`**.
- Always add the **`COMPANY_KNOWLEDGE_BASE`** + **`CHAT_SESSIONS`/`CHAT_MESSAGES`** tables so the RAG chat works.

The parent→child link is expressed like this (the finished spec is in `examples/dynamics_erp/schema_spec.json`):

```jsonc
{
  "name": "SALES_ORDER_LINES",
  "per_parent": { "parent": "SALES_ORDERS", "min": 1, "max": 5 },
  "columns": [
    { "name": "LINE_ID",   "type": "NUMBER", "pk": true, "gen": "row_index" },
    { "name": "ORDER_ID",  "type": "NUMBER", "gen": "fk", "fk_strategy": "parent", "ref_table": "SALES_ORDERS" },
    { "name": "PRODUCT_ID","type": "NUMBER", "gen": "fk", "ref_table": "PRODUCTS" },
    { "name": "QUANTITY",  "type": "NUMBER", "gen": "int", "min": 1, "max": 25 },
    { "name": "LINE_AMOUNT","type": "FLOAT", "gen": "float", "min": 50, "max": 45000, "round": 2 }
  ]
}
```

`per_parent` (no `row_count`) means: for each `SALES_ORDERS` row, generate 1–5 line rows; the
`fk_strategy: "parent"` column receives that parent order's id. Time columns (`orderDate`,
`invoiceDate`, `postingDate`) use `"-12m"`..`"today"` so the current month has data.

Validate:
```bash
python3 tools/validate_spec.py examples/dynamics_erp/schema_spec.json
```
The validator confirms the `per_parent.parent` and every `fk.ref_table` resolve to real tables.

## 2. Generate → seed CSVs (skill: `demo-data-generator`)

```bash
python3 templates/generator/generate_seed.py \
    --spec examples/dynamics_erp/schema_spec.json \
    --out  examples/dynamics_erp/seed --today 2026-06-22
```
Confirm `SALES_ORDER_LINES.csv` has several lines per order (every `ORDER_ID` from
`SALES_ORDERS` appears) and `INVOICES.csv` includes the current month. The
`COMPANY_KNOWLEDGE_BASE` table is seeded from `examples/dynamics_erp/kb_content.json`
(payment terms, credit policy, returns/RMA, product catalog) — that's what the RAG retrieves.

## 3. Scaffold + deploy (skill: `dashboard-rag-scaffold`)

**Snowflake Workspaces (no CLI) — recommended:** connect the repo to a Workspace, open
`examples/dynamics_erp/deploy/workspace_setup.sql` and **Run All** (bootstrap + tables +
inline data + Cortex Search), then create the Streamlit app *from repository* pointed at
`examples/dynamics_erp/app/`. See the README's "Deploy in Snowflake Workspaces" section.

**CLI / local IDE (advanced)** — regenerate locally and load via the `snow` CLI:

```bash
python3 templates/render.py --spec examples/dynamics_erp/schema_spec.json --out examples/dynamics_erp --today 2026-06-22
examples/dynamics_erp/deploy/run.sh <your_connection>
cd examples/dynamics_erp/app && snow streamlit deploy --connection <your_connection> --replace && cd -
```

## 4. The result

Open the app:
- **Assistant** — ask "What are our standard payment terms?" or "What is the returns / RMA policy?" → a grounded answer citing the finance-policy KB docs.
- **Revenue** — invoiced amount by month (YTD card + trend).
- **Customers** — top customers by invoiced amount.
- **AR Aging** — open/overdue invoices bucketed by days past due.
- **Orders & Inventory** — orders by status; lowest-inventory reorder candidates.

## 5. From demo to production

When real Dynamics data lands (Fivetran or a custom OData pull into bronze tables), create
views in the app schema that map the logical names/columns the dashboard expects to your
bronze tables — using the `api_field` annotations in the spec (e.g. `totalAmountIncludingTax`
→ `INVOICES.TOTAL_AMOUNT`) as the mapping guide. Redeploy the app with the same `app_config.py`;
it now reads live data, and the Cortex chat indexes your real policy documents.
