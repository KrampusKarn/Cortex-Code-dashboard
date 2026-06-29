---
name: trial-seed-bronze
description: Stand up the Employee 360 medallion on a trial account with NO external access — the 7ptrial path. Instead of extracting the live mock API, load the same synthetic OmniHR + Harvest JSON straight into the Bronze VARIANT tables with src/seeders/seed_bronze.sh (driven by profiles_omnihr.json / profiles_harvest.json), then run the SAME committed Silver→Gold→semantic→document SQL as the live path. Deterministic (SEED=42) so it byte-matches the API path. Use when an attendee on the 7ptrial connection wants to follow along without a tunnel or External Access Integration.
tools:
- read_file
- run_shell_command
---

# When to Use

- The **7ptrial path** (connection `7ptrial`): a Snowflake **trial account**, which cannot create an
  External Access Integration, so it can't pull the mock API over a tunnel.
- An attendee wants to reproduce the demo and land at the **same** Bronze→Silver→Gold dashboard the live
  DEMO path produces, just fed from local files instead of HTTP.
- Keywords: trial account, no External Access, no EAI, seeder, seed Bronze, offline, follow along, 7ptrial.

This is the offline twin of the live ingest: `seed_bronze.sh` is the no-tunnel replacement for steps ①②-Bronze
(`api-schema-extraction` + `medallion-build`'s Bronze ingest). Everything **downstream is identical** — the
committed `src/03_silver.sql` → `04_gold.sql` → `05_semantic_analyst.sql` → `01_document_ingestion.sql` run
unchanged. There are **no generate-then-review hooks** on this path — it runs the committed reference SQL
as-is, so attendees converge on exactly the presenter's schema.

# Prerequisites

1. **The 7ptrial connection** in `~/.snowflake/connections.toml` (the script has no default — always pass
   `--connection 7ptrial`). The kit never stores credentials.
2. **The app/RAG + Silver layers exist:** run `src/00_setup.sql` (database `DEMO_EMPLOYEE_APP`, warehouses,
   PUBLIC chat/document tables) and `src/03_silver.sql` (the typed `SILVER.*` tables + `SP_BUILD_SILVER`) once.
3. **Cortex granted:** `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ACCOUNTADMIN;` (and, if models are
   region-limited, `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';`).
4. **The data brain** the seeder reads: `src/seeders/profiles_omnihr.json` + `src/seeders/profiles_harvest.json`
   (per-source column profiles — row counts + API-realistic value rules). `examples/hris_people/schema_spec.json`
   is the entity/lineage reference (which tables exist + the `api_field` → column mapping). These are what to
   read/edit when adjusting the demo data. See `references/seeder_profiles.md`.

# Workflows

## 1. Load both sources into Bronze (no tunnel)

```bash
cd examples/hris_people/deployed_app/src/seeders
./seed_bronze.sh --connection 7ptrial          # add --dry-run to inspect the SQL first
```
This builds the FK-coherent OmniHR + Harvest graph from the profiles, serializes each record with the mock
API's **same `endpoints.py` serializers** (so the Bronze JSON is byte-identical to what the API would serve,
`SEED=42`), and loads it into `BRONZE.<entity> (PAYLOAD VARIANT, _SOURCE, _PATH, _LOADED_AT)`. Flags:
`--database` (default `DEMO_EMPLOYEE_APP`), `--seed` (default 42), `--today YYYY-MM-DD` (pin for byte-stable
dates), `--dry-run`.

## 2. Flatten Bronze → Silver (the same proc the live path calls)

```bash
snow sql -c 7ptrial --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"
```

## 3. Build Gold + the assistants from the committed reference SQL

```bash
snow sql -c 7ptrial --role ACCOUNTADMIN -f ../04_gold.sql
snow sql -c 7ptrial --role ACCOUNTADMIN -f ../05_semantic_analyst.sql      # GOLD.HR_ANALYST (Cortex Analyst)
snow sql -c 7ptrial --role ACCOUNTADMIN -f ../01_document_ingestion.sql    # COMPANY_KB_SEARCH (Cortex Search)
```
(`seed_bronze.sh` prints these next-step commands too.) Then hand off to **`dashboard-compose`** (step ④) to
deploy the app and load `docs/*.md`.

## 4. Verify

- `SELECT * FROM BRONZE.BRONZE_INGEST_LOG ORDER BY ROW_COUNT DESC;` — every entity loaded (or check Bronze row
  counts directly).
- `SELECT EMPLOYEE_ID, FIRST_NAME, EMAIL, TITLE FROM SILVER.EMPLOYEES LIMIT 5;` — flatten worked.
- `SELECT * FROM GOLD.EMPLOYEE_360 LIMIT 5;` — the dashboard's read surface is populated.

# Best Practices

- **Always pass `--connection 7ptrial`** — the seeder has no default connection.
- **Tune data in the profiles, not the CSV/Bronze.** Edit `profiles_*.json` (row counts, value rules), then
  re-run `seed_bronze.sh`. The profiles are the maintained artifacts.
- **Determinism:** keep `SEED=42` so the trial account matches the DEMO account; pin `--today` only for
  byte-stable dates (otherwise relative tokens keep the dashboard current).
- **Never seed the app-managed tables** — `CHAT_SESSIONS`, `CHAT_MESSAGES`, `DOCUMENT_CHUNKS`,
  `DOC_INGEST_LOG`, `COMPANY_KNOWLEDGE_BASE` are written by the app / the doc pipeline.
- **Run the committed `src/03→01` SQL unchanged** — this path's value is converging on the presenter's exact
  schema, so don't regenerate it.

# Examples

## Example 1: Attendee on a trial account

Attendee: "I'm on a trial — set up the demo." CoCo confirms `src/00_setup.sql` + `src/03_silver.sql` ran, then
`cd src/seeders && ./seed_bronze.sh --connection 7ptrial`, `CALL SP_BUILD_SILVER()`, runs `04`/`05`/`01`,
verifies `GOLD.EMPLOYEE_360` is populated, and hands off to `dashboard-compose`.

## Example 2: "Give me more candidates in the pipeline"

CoCo edits the `CANDIDATES` row count in `profiles_omnihr.json`, re-runs `seed_bronze.sh --connection 7ptrial`
and `SP_BUILD_SILVER`, and confirms the new count flows through to `GOLD.CANDIDATES`.

# References

- `references/seeder_profiles.md` — the `profiles_*.json` format (row counts + value-rule generators), how it
  reuses the mock API's serializers + `_seedlib` engine, the `--selftest` check, and what `schema_spec.json`
  is for.
