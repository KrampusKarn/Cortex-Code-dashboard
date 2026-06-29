# Mock OmniHR + Harvest API — the live *Extract* source for the medallion demo

A standalone FastAPI server that serves the **same synthetic data the seeders load
into Snowflake**, shaped like the real **OmniHR (Omni API v1)** and **Harvest (v2)**
APIs. You boot it on stage, expose it over an HTTPS tunnel, and have **Cortex Code
extract every endpoint into a Bronze layer** — the live "E" of the
Bronze → Silver → Gold ELT demo (step 4 of the E2E analytics story).

> This is the **Extract** half of step 4. It is additive and **non-destructive** —
> running this server touches nothing in Snowflake. The Snowflake-side objects
> (External Access Integration, Bronze tables, transforms) are at the bottom of this
> file and are run separately, with explicit approval.

## Why this exists

| Path | Audience | What it does |
|---|---|---|
| **Seeder** (`../src/seeders/seed_bronze.sh`) | Trial / any account (no EAI) | Loads the same JSON **straight into `BRONZE.*`** (no tunnel), then `SP_BUILD_SILVER` flattens it |
| **This mock API** | The live (DEMO) demo | Serves the same data as a **real HTTP API** so Snowflake can *extract* it into Bronze live |

Both read the **same data brain** — the seeder profiles (`profiles_omnihr.json`,
`profiles_harvest.json`) and the same engine (`_seedlib.build_rows`) — and produce the **same Bronze**,
so what the seeder loads and what this API serves can never drift.

## Quick start

```bash
pip install -r requirements.txt        # fastapi + uvicorn (faker comes from the repo root)
./run.sh                                # http://localhost:8000  (local only)
```

**Or, for the full Snowflake-ingestable (EAI) endpoint in one command** — boots the API,
opens a tunnel, and (when needed) points the `BRONZE.OMNI_HARVEST_EGRESS` network rule at it:

```bash
./serve_eai.sh start          # prints the tunnel URL + the ingest commands
./serve_eai.sh stop           # stops the local API + tunnel (Snowflake data/objects untouched)
```
The Snowflake side (EAI, network rule, procs, data) is created once by `../src/02_bronze.sql`
and persists — only the local API + tunnel are ephemeral. Two tunnel backends:

- **ngrok static domain (preferred — stable URL).** Put your free reserved domain in
  `.tunnel.env` (`NGROK_DOMAIN=<you>.ngrok-free.app`) and store the authtoken once with
  `ngrok config add-authtoken <token>` (it lives in ngrok's own config, **never** in this repo).
  Because the host never changes, set the network rule **once** with `./serve_eai.sh start --set-rule`;
  after that, plain `./serve_eai.sh start` needs no rule change and no ACCOUNTADMIN to boot.
- **cloudflare quick tunnel (fallback — `--cloudflare`).** No account needed, but the URL is
  random each run, so `serve_eai.sh` re-points the network rule on every boot.

> `.tunnel.env` (your domain) and the ngrok authtoken are both gitignored / outside the repo —
> no per-user or secret values are committed.

- `GET /` — index of all 33 endpoints (with row counts)
- `GET /docs` — Swagger UI (auto-generated); `GET /openapi.json` — the schema CoCo can read
- `GET /api/v1/employees?page=1&page_size=5` — OmniHR-style, paginated, **nested** JSON
- `GET /v2/time_entries?page=1&per_page=5` — Harvest-style, paginated, **nested** JSON

Determinism: `SEED=42` by default (`SEED=7 ./run.sh`). Currency: dates use relative
tokens so the data always covers the current period — pin with `MOCK_TODAY=2026-06-26`.

## What it serves

- **33 endpoints, one per Silver table** (18 OmniHR + 15 Harvest) — so "extract every
  endpoint" maps 1:1 to "rebuild the Silver layer".
- **Authentic envelopes:** OmniHR uses DRF-style `{count, next, previous, results}`;
  Harvest uses `{<resource>: [...], per_page, total_pages, total_entries, page, links}`.
- **Nested headline resources** (`/api/v1/employees`, `/v2/time_entries`) expose nested
  objects (`position.name`, `department.name`, `reporting_manager.system_id`,
  `user.id`/`project.id`/`task.id`) so the **"raw nested JSON → flatten into Silver"**
  step is visible. Every other endpoint is flat snake_case.
- **FK-coherent across sources** — generated as one in-memory graph, so
  `HARVEST_USERS.employee_id`, `TIME_ENTRIES.user.id`, etc. all reference real employees.

## How it fits the medallion (Bronze → Silver → Gold)

```
  THIS SERVER (OmniHR + Harvest JSON over HTTPS)
        │  Snowflake External Access Integration  (the live Extract)
        ▼
  BRONZE   BRONZE.<entity> (PAYLOAD VARIANT, _SOURCE, _PATH, _LOADED_AT) — one table per endpoint
        │  INSERT … SELECT payload:field::type    (flatten nested JSON)
        ▼
  SILVER   typed entity tables (EMPLOYEES, TIME_ENTRIES, …) — flattened from Bronze
        │  business entities, joins, metrics
        ▼
  GOLD     entity pass-through views (1:1 over SILVER) + analytics views
           (headcount, utilization, …)  →  the Streamlit dashboard reads GOLD
```

## Architecture (no live DB needed to boot)

| File | Role |
|---|---|
| `app.py` | FastAPI; builds the dataset once at startup; registers one list route per table |
| `dataset.py` | Merges the seeder profiles + calls `_seedlib.build_rows` → in-memory graph |
| `schema.py` | Parses `../src/03_silver.sql` → entity table structures (so no Snowflake connection is needed) |
| `endpoints.py` | Path map (OmniHR `/api/v1/…`, Harvest `/v2/…`), envelopes, serializers |
| `run.sh` / `requirements.txt` | Boot script + deps |

> The **offline Bronze loader** (`seed_bronze.py` / `seed_bronze.sh`) lives in
> [`../src/seeders/`](../src/seeders/) with the other data-load scripts. It reuses this module's
> `endpoints.py` serializers to load `BRONZE.*` directly — the no-tunnel path for trial accounts.

The engine (`../src/seeders/_seedlib.py`) is shared, not copied — `build_rows()` is the
one generator the seeders also use.

## Reusability — re-pointing at the real APIs later

- **Add/adjust fields:** edit the seeder profiles (the same files the seeders use).
- **Schema changed:** re-run nothing — `schema.py` re-reads `00_setup.sql` on boot.
- **Go live for real:** the endpoint paths already follow OmniHR/Harvest conventions, so
  swapping the External Access Integration's host from your tunnel to
  `https://api.omnihr.co` / `https://api.harvestapp.com` (plus a real auth secret) reuses
  the same Bronze → Silver → Gold pipeline unchanged.

---

## Trial accounts — offline Bronze load (no tunnel, no EAI)

Trial accounts can't use an External Access Integration, so they can't pull this API over a tunnel.
The offline twin is [`../src/seeders/seed_bronze.sh`](../src/seeders/) — it builds the same graph,
serializes each record with this module's **same `endpoints.py` serializers**, and loads the identical
JSON into `BRONZE.<entity>` so `SILVER.SP_BUILD_SILVER` → `04_gold` → `05_semantic_analyst` run
unchanged. See [`../src/seeders/README.md`](../src/seeders/README.md).

---

## Bridge to Snowflake — the live Extract (run as ACCOUNTADMIN, with approval)

Snowflake's egress can't reach `localhost`, so the server is exposed over HTTPS by a tunnel.
`serve_eai.sh` handles the tunnel + network rule (see **Quick start** above) — you rarely run
the tunnel by hand, but if you do:

```bash
ngrok http 8000 --url https://<your>.ngrok-free.app   # stable (reserved domain)
# or:  cloudflared tunnel --url http://localhost:8000  # ephemeral (random URL)
```

The Snowflake side is built **once** as a 3-schema medallion — see `../src/`:

- **`02_bronze.sql`** — creates the `BRONZE`/`SILVER`/`GOLD` schemas, the network rule + External
  Access Integration, the `BRONZE.BRONZE_ENDPOINTS` registry (all 33 endpoints), and
  `BRONZE.SP_INGEST_BRONZE` / `BRONZE.SP_INGEST_ALL_BRONZE` (paginated pull into `BRONZE.<entity>`
  VARIANT tables; sends an `ngrok-skip-browser-warning` header so the free-tier interstitial never
  replaces the JSON).
- **`03_silver.sql`** — the typed `SILVER.*` tables + `SILVER.SP_BUILD_SILVER`, which flattens each
  `BRONZE.*` table into its `SILVER.*` table (`payload:work_email::string AS EMAIL`,
  `payload:position.name::string AS TITLE`, …), driven by `SILVER.SILVER_FIELD_MAP`.
- **`04_gold.sql`** — `GOLD.*` entity + analytics views the dashboard reads.
- **`05_semantic_analyst.sql`** — the `GOLD.HR_ANALYST` semantic view for the Cortex Analyst tab.

**One-time build (fresh account):**
```bash
snow sql -c <conn> --role ACCOUNTADMIN -f ../src/02_bronze.sql
snow sql -c <conn> --role ACCOUNTADMIN -f ../src/03_silver.sql
snow sql -c <conn> --role ACCOUNTADMIN -f ../src/04_gold.sql
snow sql -c <conn> --role ACCOUNTADMIN -f ../src/05_semantic_analyst.sql
```

**Each demo run** — just start the tunnel and ingest (with an ngrok static domain the network
rule is already pinned, so there's no `ALTER` step):
```bash
./serve_eai.sh start            # first time on a fresh account: add --set-rule
# then run the two CALLs it prints:
snow sql -c <conn> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.BRONZE.SP_INGEST_ALL_BRONZE('https://<your>.ngrok-free.app');"
snow sql -c <conn> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"
```

No secrets in the repo — the mock API needs no auth, and the ngrok authtoken lives in ngrok's own
config. To go live against the real APIs, add a `SECRET` for the bearer token and reference it
from the integration.
