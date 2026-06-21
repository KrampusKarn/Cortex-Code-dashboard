# Sample API Responses (Fixtures)

Synthetic, vendor-shaped sample API responses for the **Cortex Dashboard Kit** workshop.
Point the `api-schema-extraction` skill at any file here to scaffold a `schema_spec.json`,
then build the Snowflake dashboard + Cortex RAG chat on top.

> **All values are invented.** No real personal, customer, or company data is present.
> Field names, nesting, and pagination wrappers mirror each vendor's real response *shape*
> so the extraction exercise is realistic, but every id, name, email, and amount is fictional.
> Emails use the reserved `example.com` / `.example` domains.

## Fixtures

| Fixture | Source API | Endpoint | Entity / Grain demonstrated | Extraction notes |
|---|---|---|---|---|
| `freshteam_employees.sample.json` | Freshteam (HR) | `GET /api/v1/employees` | Top-level **array** of employees; one row per employee | Nested `addresses[]` and `emergency_contacts[]` → flatten to child tables (`per_parent` on `id`) or store as VARIANT and unnest in views. `reporting_to_id` is a self-reference to `id` (manager hierarchy). `termination_date` / `last_working_day` are null for active staff. |
| `harvest_time_entries.sample.json` | Harvest (Time Tracking) | `GET /v2/time_entries` | Pagination **envelope** `{ time_entries: [...], page, per_page, total_entries, ... }`; one row per time entry | Real records live under the `time_entries` key — extract that array, not the root object. `page` / `per_page` / `total_pages` / `total_entries` / `links` are pagination metadata, not data columns. Nested `user{}`, `project{}`, `task{}`, `client{}` → fold into `*_id` + `*_name` columns. `hours` is a 24-hour decimal (`7.5` = 7h30m). `billable` is the boolean of record. |
| `lattice_feedback.sample.json` | Lattice (Performance) | `GET /v1/feedback` | Top-level **array** of feedback items; one row per written feedback | Ids are opaque strings (e.g. `fb_...`, `usr_...`), not integers. **The API does NOT return sentiment** — derive it downstream with `SNOWFLAKE.CORTEX.SENTIMENT(written_feedback)` (returns a score in `[-1.0, 1.0]`). `feedback_type` (`review` / `praise` / ...) is the categorical dimension. `reviewee_id` / `reviewer_id` map to HR employees via email, not directly to Freshteam `id`. |
| `dynamics_salesorders.sample.json` | Microsoft Dynamics 365 Business Central | OData `GET /companies({id})/salesOrders` | OData **envelope** `{ "@odata.context", "value": [...] }`; one parent row per sales order | Real records live under the `value` array (standard OData v4 shape); `@odata.context` is metadata. `id` is a GUID. Nested `salesOrderLines[]` → child table via `per_parent` (parent key = order `id` / `number`). `lineType` varies (`Item` / `Comment` / `Resource`); `Comment` lines carry zero quantity/amount. Watch mixed `currencyCode` (THB vs USD) — totals are per-order in the order's own currency. |

## How this connects to the skill

1. Run `api-schema-extraction` against one fixture → it emits a `schema_spec.json`
   (tables, columns, types, and parent/child relationships inferred from the nesting above).
2. Pagination wrappers (`time_entries` / `value`) tell the skill where the record array starts.
3. Nested arrays (`addresses[]`, `emergency_contacts[]`, `salesOrderLines[]`) become either
   child tables (`per_parent`) or VARIANT columns, depending on your modeling choice.
4. For Lattice, remember sentiment is a **derived** column produced by Cortex at query time —
   it is intentionally absent from the source payload.
