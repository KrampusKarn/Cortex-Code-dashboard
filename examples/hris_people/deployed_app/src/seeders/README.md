# `seeders/` — per-source synthetic data for DASHBOARD_SPS

Structure-driven, FK-coherent, **API-realistic** synthetic data for the live
`DEMO_EMPLOYEE_APP.PUBLIC` schema — one seeder per data source so they don't get mixed up:

| Seeder | Source | Tables | Realistic of |
|---|---|---|---|
| `seed_omnihr.sh` | **OmniHR** (`Omni API v1`) | 18 — employees, org, recruitment, leave | OmniHR field semantics: `employment_status`, `marital_status`, 198 nationalities, time-off types, ATS sources, job `event_reason` |
| `seed_harvest.sh` | **Harvest** (v2) | 15 — clients, projects, time, billing | billable flags, hourly/cost rates, weekly capacity, utilization |
| `seed_lattice.sh` | **Lattice** | 2 — performance reviews, HR notes | rating 1–5, sentiment + score in `[-1,1]` |
| `seed_all.sh` | all three | 35 | runs them in FK-safe order |

The 5 **app-managed** tables are never seeded: `CHAT_SESSIONS`, `CHAT_MESSAGES`,
`DOCUMENT_CHUNKS`, `DOC_INGEST_LOG`, `COMPANY_KNOWLEDGE_BASE`.

## How it works

- **Structure-driven:** `_seedlib.py` reads the *live* table structure each run
  (`INFORMATION_SCHEMA.COLUMNS` + `SHOW PRIMARY KEYS`), so it adapts automatically when the
  schema changes — no table/column list is hardcoded in the engine.
- **FK-coherent:** foreign keys are inferred from column names (+ an alias map) and drawn from
  **real parent rows**. Cross-source parents (e.g. `TIME_ENTRIES.EMPLOYEE_ID → EMPLOYEES`) are
  read live from the DB, which is why **order matters**: OmniHR → Harvest → Lattice.
- **API-realistic:** the maintained artifacts are the three `profiles_*.json` files — they map
  `TABLE.COLUMN` to a generator (`choice`/`enumerate`/`int`/`float`/`date`/`bool`/`template`/`faker`)
  with values drawn from each API's real fields/enums. Update a profile when an API changes; the
  engine and scripts stay untouched.

## Run order

```bash
cd examples/hris_people/deployed_app/src/seeders

# preview first — generates the SQL, executes nothing:
./seed_all.sh --dry-run

# full coherent rebuild of the live demo data (truncate + reseed, one confirmation):
./seed_all.sh --reset

# or one source at a time (OmniHR must run before Harvest/Lattice):
./seed_omnihr.sh --reset
./seed_harvest.sh --reset
./seed_lattice.sh --reset
```

Prereq: run `../00_setup.sql` once so all 40 tables exist (incl. the `OMNI_EMPLOYEE_ID` column).

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--connection` | `sevenpeaks_partner_demo` | snow CLI connection |
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
