# `seeders/` — load synthetic data into Snowflake (no mock API needed)

**This is where attendees / Cortex Code find the data-load scripts.** All synthetic data is
structure-driven, FK-coherent, and API-realistic. There are **two ways to load**, matching the
two layers of the medallion:

### 1. Offline Bronze load — `seed_bronze.sh`  (recommended; mirrors the mock-API path)

The no-tunnel twin of `BRONZE.SP_INGEST_ALL_BRONZE`. Generates the **same JSON the mock API serves**
(reusing `../../mock_api/endpoints.py`) and loads it into `BRONZE.<entity>` VARIANT tables — then the
**same** `SILVER.SP_BUILD_SILVER` flattens it. This is the full Bronze → Silver → Gold medallion
without an External Access Integration, so it works on **trial accounts** and is byte-identical to
the live API path (same `SEED`).

```bash
./seed_bronze.sh --connection <your-connection>     # add --dry-run to inspect the SQL first
snow sql -c <your-connection> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"
```
Prereq: `../00_setup.sql` + `../03_silver.sql` first. `python3 seed_bronze.py --selftest` asserts the
JSON matches the flatten paths.

### 2. Direct Silver load — `seed_omnihr.sh` / `seed_harvest.sh` / `seed_all.sh`  (shortcut)

Skips Bronze and writes typed rows **straight into Silver** — faster for a quick refresh, but it
doesn't demonstrate the raw→flatten step. One seeder per source so the data sources stay separate:

| Seeder | Source | Tables |
|---|---|---|
| `seed_omnihr.sh` | **OmniHR** (`Omni API v1`) | 18 — employees, org, recruitment, leave |
| `seed_harvest.sh` | **Harvest** (v2) | 15 — clients, projects, time, billing |
| `seed_all.sh` | both | 33 — runs them in FK-safe order |

```bash
./seed_all.sh --connection <your-connection> --schema SILVER --reset
```

The 5 **app-managed** tables are never seeded by either path: `CHAT_SESSIONS`, `CHAT_MESSAGES`,
`DOCUMENT_CHUNKS`, `DOC_INGEST_LOG`, `COMPANY_KNOWLEDGE_BASE`.

> The dashboard reads **`GOLD`** (built from **`SILVER`**). Both load paths land in Silver, so target
> `--schema SILVER`. Prereq: `../00_setup.sql` + `../03_silver.sql`. (`--schema PUBLIC`, the default,
> targets the flat base tables from `00_setup.sql` — not the dashboard's read path.)

## How it works

- **Structure-driven:** `_seedlib.py` reads the *live* table structure each run
  (`INFORMATION_SCHEMA.COLUMNS` + `SHOW PRIMARY KEYS`), so it adapts automatically when the
  schema changes — no table/column list is hardcoded in the engine.
- **FK-coherent:** foreign keys are inferred from column names (+ an alias map) and drawn from
  **real parent rows**. Cross-source parents (e.g. `TIME_ENTRIES.EMPLOYEE_ID → EMPLOYEES`) are
  read live from the DB, which is why **order matters**: OmniHR → Harvest.
- **API-realistic:** the maintained artifacts are the two `profiles_*.json` files — they map
  `TABLE.COLUMN` to a generator (`choice`/`enumerate`/`int`/`float`/`date`/`bool`/`template`/`faker`)
  with values drawn from each API's real fields/enums. Update a profile when an API changes; the
  engine and scripts stay untouched.

## Run order

```bash
cd examples/hris_people/deployed_app/src/seeders

# always pass --connection (the scripts have no default — it resolves from your
# local ~/.snowflake/connections.toml):

# preview first — generates the SQL, executes nothing:
./seed_all.sh --connection <your-connection> --dry-run

# full coherent rebuild of the live demo data (truncate + reseed, one confirmation):
./seed_all.sh --connection <your-connection> --reset

# or one source at a time (OmniHR must run before Harvest):
./seed_omnihr.sh  --connection <your-connection> --reset
./seed_harvest.sh --connection <your-connection> --reset
```

Prereq: run `../00_setup.sql` once so the base tables exist.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--connection` | `<your-connection>` | snow CLI connection (from your local `connections.toml`) |
| `--database` / `--schema` | `DEMO_EMPLOYEE_APP` / `PUBLIC` | target |
| `--rows N` | `50` | default rows per table (a profile's `tables.<T>.rows` overrides) |
| `--seed N` | `42` | RNG seed (deterministic output) |
| `--reset` | off | **TRUNCATE** the source's tables before loading — destructive; requires a typed confirmation |
| `--dry-run` | off | generate the INSERT SQL and print a preview; execute nothing |

## Safety

`--reset` truncates live tables and is gated behind a typed schema-name confirmation. Without
`--reset` the seeders **append**. Always `--dry-run` first against an unfamiliar target. The
seeders only ever run read-only introspection plus the generated `INSERT`/`TRUNCATE`; they never
touch the app-managed chat/ingestion tables.
