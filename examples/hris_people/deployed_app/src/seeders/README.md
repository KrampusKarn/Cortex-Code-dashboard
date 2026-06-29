# `seeders/` — load synthetic data into Bronze (no mock API needed)

**This is where attendees / Cortex Code find the data-load script.** There is **one seeder**,
`seed_bronze.sh`, and it loads **both data sources (OmniHR + Harvest) into the Bronze layer** — the
no-tunnel twin of `BRONZE.SP_INGEST_ALL_BRONZE`. From there the *same* `SILVER.SP_BUILD_SILVER`
flattens it, exactly as the live mock-API path does. So the seeder and the mock-API path are two
front-ends to the **same** Bronze → Silver → Gold medallion.

| Path | How Bronze is filled | Then |
|---|---|---|
| **Mock API** (DEMO, needs External Access) | `SP_INGEST_ALL_BRONZE` pulls the API over a tunnel | `SP_BUILD_SILVER` |
| **Seeder** (trial / any account, no EAI) | `seed_bronze.sh` loads the same JSON locally | `SP_BUILD_SILVER` |

The seeded Bronze is **byte-identical** to the API's (same serializers in `../../mock_api/endpoints.py`,
same `SEED=42`), so `SP_BUILD_SILVER`, `04_gold.sql`, and `05_semantic_analyst.sql` run unchanged.

## Run

```bash
cd examples/hris_people/deployed_app/src/seeders

# Prereq (once): ../00_setup.sql + ../03_silver.sql  (database, warehouses, SILVER tables + SP_BUILD_SILVER)

# 1) load BOTH sources into BRONZE.<entity> VARIANT  (add --dry-run to inspect the SQL first)
./seed_bronze.sh --connection <your-connection>

# 2) flatten Bronze -> Silver (the same proc the API path calls)
snow sql -c <your-connection> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"

# 3) build Gold + the semantic view (seed_bronze.sh prints these too)
snow sql -c <your-connection> --role ACCOUNTADMIN -f ../04_gold.sql
snow sql -c <your-connection> --role ACCOUNTADMIN -f ../05_semantic_analyst.sql
```

Always pass `--connection` — the script has no default; it resolves from your local
`~/.snowflake/connections.toml`.

| Flag | Default | Meaning |
|---|---|---|
| `--connection` | *(required)* | snow CLI connection |
| `--database` | `DEMO_EMPLOYEE_APP` | target database |
| `--seed N` | `42` | RNG seed — deterministic output (so the two accounts match) |
| `--today YYYY-MM-DD` | real today | anchor for relative dates (pin for byte-stable output) |
| `--dry-run` | off | write the SQL and print stats; execute nothing |

## Files

| File | Role |
|---|---|
| `seed_bronze.sh` | The seeder — generates the JSON and loads it into `BRONZE.*` (then prints the flatten + Gold steps). |
| `seed_bronze.py` | Builds the graph + serializes each record with the mock API's serializers; emits the load SQL. `--selftest` asserts the JSON matches the flatten paths. |
| `_seedlib.py` | The **generation engine** (`build_rows`) shared with the mock API (`../../mock_api/dataset.py`) — one generator, so the two paths can never drift. |
| `profiles_omnihr.json` / `profiles_harvest.json` | Per-source column profiles (row counts + API-realistic value rules). The maintained artifacts — edit these when an API changes. |

## How it works

- **FK-coherent:** foreign keys are inferred from column names (+ an alias map) and drawn from real
  parent rows; the whole graph is built in one pass, so cross-source keys
  (`TIME_ENTRIES.EMPLOYEE_ID → EMPLOYEES`, etc.) always resolve.
- **API-realistic:** the `profiles_*.json` map `TABLE.COLUMN` to a generator
  (`choice`/`enumerate`/`int`/`float`/`date`/`bool`/`template`/`faker`) with values drawn from each
  API's real fields/enums.
- **Deterministic:** `SEED=42` gives reproducible data (and makes the DEMO and trial accounts match);
  dates use relative tokens so the dashboard always covers the current period — pin `--today` to freeze them.

The 5 **app-managed** tables are never seeded (the app writes them / the doc pipeline fills them):
`CHAT_SESSIONS`, `CHAT_MESSAGES`, `DOCUMENT_CHUNKS`, `DOC_INGEST_LOG`, `COMPANY_KNOWLEDGE_BASE`.
