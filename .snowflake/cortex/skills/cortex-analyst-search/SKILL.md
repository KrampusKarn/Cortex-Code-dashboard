---
name: cortex-analyst-search
description: Add the two Cortex assistants on top of the GOLD medallion, generating the SQL for review first. Builds the GOLD.HR_ANALYST semantic view that powers Cortex Analyst (natural-language → SQL "Ask Your Data") and the document pipeline (COMPANY_DOCS stage → PARSE_DOCUMENT/SPLIT_TEXT → DOCUMENT_CHUNKS → COMPANY_KB_SEARCH Cortex Search service) that powers the grounded "Documents" RAG chat. Each piece is generated into build/ and run only after a confirm hook. This is step ③ of the DEMO (live mock_api) path, after medallion-build. Use when GOLD exists and the presenter wants the Analyst + Search assistants.
tools:
- read_file
- write_file
- run_shell_command
- ask_user_question
---

# When to Use

- Step ③ of the **live-API path**: the GOLD layer is built (from
  `medallion-build`) and the presenter wants the **two Cortex assistants** the dashboard ships:
  **Ask Your Data** (Cortex Analyst over a semantic view) and **Documents** (Cortex Search RAG over company
  docs).
- Keywords: Cortex Analyst, semantic view, Ask Your Data, Cortex Search, RAG, documents, knowledge base,
  COMPANY_KB_SEARCH, talk to your data.

Generate into `build/`, run only after the review hook. Golden references: `src/05_semantic_analyst.sql`
(Analyst) and `src/01_document_ingestion.sql` (Search). The **offline seeder** path runs those two committed files
as-is via `trial-seed-bronze`; this skill is the DEMO path's generate-then-review version.

# The review hook

Same gate as `medallion-build`: generate → present a summary + the `build/` file path → **STOP and ask via
the `ask_user_question` selection popup, then wait** (never decide for the user). Present exactly these four
options (header `Review`, question `Review build/<file>.sql — what next?`):

> **Run it** · **Revise** (tell me what to change) · **Show full SQL** · **Skip**

The tool auto-appends a **"Something else"** free-form entry — that IS the fifth "tell Cortex Code what to do"
option, so never add it as a literal option. On **Run it** run it against the connection; **Revise** (or the
free-form "Something else") edit just that file and re-present the popup; **Show full SQL** print the full
file; **Skip** skip. The two assistants are independent — review them as two separate hooks (semantic view
first or docs first, either order). If the selection tool is unavailable, fall back to the same four choices
as a plain-text menu replied to in chat.

# Prerequisites

1. **Analyst:** GOLD exists (`GOLD.EMPLOYEE_360`, `GOLD.TIME_ENTRIES`, `GOLD.PROJECTS`, `GOLD.LEAVE_REQUESTS`,
   `GOLD.CANDIDATES`) — the semantic view models these.
2. **Search:** the PUBLIC app/RAG layer from `src/00_setup.sql` is in place — the `COMPANY_DOCS` stage
   (directory + SSE) and the `DOCUMENT_CHUNKS` / `DOC_INGEST_LOG` tables. The chat indexes
   `DOCUMENT_CHUNKS`, not any curated table.
3. **Docs to ingest:** `examples/hris_people/deployed_app/docs/*.md` (pto-policy, health-benefits,
   upcoming-events). Each `.md` sets its TITLE via a leading `# Heading` and CATEGORY via a `**Category:** X`
   line.
4. **Cortex granted:** `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;` (the #1 cause of a
   dead Assistant tab). See `references/semantic_and_search.md` for the skeletons.

# Workflows

## A. Cortex Analyst — GOLD.HR_ANALYST semantic view  → review hook

Generate `build/semantic.sql`: a `CREATE OR REPLACE SEMANTIC VIEW GOLD.HR_ANALYST` with
- **TABLES** — the GOLD entities as logical tables with `PRIMARY KEY` + `WITH SYNONYMS`
  (`employees`←`EMPLOYEE_360`, `time_entries`, `projects`, `leave_requests`, `candidates`).
- **RELATIONSHIPS** — `time_entries→employees`, `time_entries→projects`, `leave_requests→employees`.
- **DIMENSIONS** + **METRICS** with synonyms so plain English maps to the right joins/aggregations
  (`headcount`, `billable_pct`/utilization, `total_leave_days`, `avg_salary`, …).

**Review hook (present the `ask_user_question` popup, then wait).** On **Run it**, run `build/semantic.sql`, then verify the view answers directly:
```sql
SELECT * FROM SEMANTIC_VIEW(GOLD.HR_ANALYST METRICS employees.headcount DIMENSIONS employees.department)
ORDER BY headcount DESC;
```
The app's "Ask Your Data" tab posts `{"semantic_view":"DEMO_EMPLOYEE_APP.GOLD.HR_ANALYST"}` to
`/api/v2/cortex/analyst/message` and runs the SQL Analyst returns — no app change needed if the name matches.

## B. Cortex Search — the document RAG pipeline  → review hook

Generate `build/document_search.sql` (in `PUBLIC`, on warehouse `DEMO_WH`):
- `SP_REBUILD_DOC_CHUNKS()` — parses every file in `@COMPANY_DOCS` with `SNOWFLAKE.CORTEX.PARSE_DOCUMENT`
  (LAYOUT), chunks with `SPLIT_TEXT_RECURSIVE_CHARACTER` (1000/200), derives TITLE (first `# H1`) + CATEGORY
  (`Category:` line), and rebuilds `DOCUMENT_CHUNKS` atomically.
- `COMPANY_DOCS_STREAM` on the stage + `DOCS_REFRESH_TASK` / `DOCS_INGEST_TASK` (auto-reingest on change).
- `CORTEX SEARCH SERVICE COMPANY_KB_SEARCH ON CONTENT ATTRIBUTES TITLE, CATEGORY, FILE_NAME` over
  `DOCUMENT_CHUNKS` (embedding `snowflake-arctic-embed-m-v1.5`, short `TARGET_LAG`).

**Review hook (present the `ask_user_question` popup, then wait).** On **Run it**, run `build/document_search.sql`, then load the docs and build the index:
```sql
-- PREFERRED (server-side, no local file transfer; also works when there's no `snow` CLI):
--   create the git repo once (see dashboard-compose / src/deploy_app.sql), then:
COPY FILES INTO @COMPANY_DOCS FROM '@CORTEX_REPO/branches/main/examples/hris_people/deployed_app/docs/';
-- FALLBACK (local CLI upload) — note: `snow sql PUT` may trigger a browser OAuth flow that hangs even on a
-- key-pair connection, so prefer COPY FILES above:
--   PUT 'file://.../docs/*.md' @DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_DOCS AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
ALTER STAGE COMPANY_DOCS REFRESH;
CALL SP_REBUILD_DOC_CHUNKS();
SELECT COUNT(*) FROM DOCUMENT_CHUNKS;          -- > 0 once parsed
```
Cortex Search builds embeddings asynchronously — give it a minute before the Documents tab returns answers.

# Best Practices

- **Run the review hook per assistant.** They are independent; let the presenter approve each.
- **Match the reference names** — `GOLD.HR_ANALYST`, `COMPANY_KB_SEARCH`, the service columns
  `CONTENT/TITLE/CATEGORY/FILE_NAME`. The committed app reads exactly these.
- **Grant `SNOWFLAKE.CORTEX_USER`** before either assistant, or both tabs come back empty.
- **Search indexes `DOCUMENT_CHUNKS`** (parsed from `docs/*.md`) — not a hand-curated table.
- **Wait for indexing** before judging RAG quality; "No relevant information found" usually means the index
  is still building or `DOCUMENT_CHUNKS` is empty.
- **Generate into `build/`; never overwrite `src/01` or `src/05`** (golden reference + offline seeder path).

# Examples

## Example 1: Add both assistants

Presenter: "GOLD's up — add the two assistants." CoCo generates `build/semantic.sql`, summarizes the
entities/metrics, **stops**; on approve runs it and verifies headcount-by-department. Then
`build/document_search.sql`, **stops**; on approve runs it, loads `docs/*.md`, calls `SP_REBUILD_DOC_CHUNKS`,
confirms `DOCUMENT_CHUNKS` is non-empty, and notes the index needs ~1 min.

## Example 2: Analyst returns nothing useful

CoCo checks the semantic view exists and the `SEMANTIC_VIEW(...)` probe returns rows; if a metric is missing
a synonym the presenter expected (e.g. "utilisation"), it adds the synonym in `build/semantic.sql` and
re-runs just that file.

# References

- `references/semantic_and_search.md` — the `CREATE SEMANTIC VIEW` skeleton (tables/relationships/dimensions/
  metrics) and the document-pipeline skeleton (rebuild proc, stream, tasks, search service), keyed to the
  golden `src/05_semantic_analyst.sql` and `src/01_document_ingestion.sql`.
