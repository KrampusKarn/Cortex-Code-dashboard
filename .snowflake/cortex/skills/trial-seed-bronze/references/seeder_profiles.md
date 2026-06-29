# Seeder profiles — the 7ptrial data brain

The offline Bronze load is driven by two maintained artifacts next to the seeder:
`profiles_omnihr.json` (HR / org / recruitment / leave) and `profiles_harvest.json` (projects / time /
delivery). They are the no-tunnel equivalent of the live API's data — the same engine
(`_seedlib.build_rows`) and the same `endpoints.py` serializers produce byte-identical Bronze JSON.

## Format

```json
{
  "tables":  { "EMPLOYEES": { "rows": 250 }, "CANDIDATES": { "rows": 200 }, ... },
  "columns": {
    "EMPLOYEES.EMAIL":   { "gen": "template", "template": "{FIRST_NAME|lower}.{LAST_NAME|lower}@acme-demo.co" },
    "EMPLOYEES.STATUS":  { "gen": "choice", "choices": ["Active","On Leave","Left"], "weights": [0.85,0.07,0.08] },
    "EMPLOYEES.HIRE_DATE": { "gen": "date", "min": "-6y", "max": "-30d" },
    "EMPLOYEES.MANAGER_ID": { "null_pct": 0.12 }
  }
}
```

- **`tables[T].rows`** — row count for table `T`.
- **`columns["T.COL"]`** — how to generate that column. A column not listed gets a sensible default by type.

### gen vocabulary
| `gen` | params | use |
|---|---|---|
| `enumerate` | `choices` | small dimension, one value per row in order (`rows == len(choices)`) |
| `choice` | `choices`, `weights?` | categorical with realistic distribution |
| `int` | `min`, `max` | integer counts |
| `float` | `min`, `max`, `round?` | money / rates / hours |
| `bool` | `p_true?` | flags |
| `date` | `min`, `max`, `null_pct?` | relative tokens (`-6y`, `-30d`, `today`) keep data current |
| `template` | `template` | derive from other columns (`{FIRST_NAME|lower}`) |
| `faker` | `faker_provider` | free text (names, sentences, companies) |
| any | `null_pct` | inject NULLs |

Foreign keys are **inferred** from column names (+ an alias map) and drawn from real parent rows, so the
whole OmniHR + Harvest graph is FK-coherent in one pass (`TIME_ENTRIES.EMPLOYEE_ID → EMPLOYEES`, etc.) — you
don't declare them in the profiles.

## Tuning the demo data

Edit the profiles, never the Bronze tables. Change a `rows` count or a value rule, then re-run
`./seed_bronze.sh --connection 7ptrial` and `CALL SILVER.SP_BUILD_SILVER();`. Keep `SEED=42` so the trial
account matches the DEMO account.

## Self-test (determinism + flatten parity)

```bash
cd examples/hris_people/deployed_app/src/seeders
python3 seed_bronze.py --selftest      # asserts the serialized JSON matches the Silver flatten paths
```
Run this after editing a profile or the serializers — it catches a profile/column or nested-path drift before
you load.

## What `schema_spec.json` is for

`examples/hris_people/schema_spec.json` is the **entity/lineage reference** — the list of tables and the
`api_field` (JSON path) → column mapping. Read it to see *which* entities exist and how API fields map to
columns; it is not executed or validated (the kit's old spec-validation tooling was retired). The profiles are
what actually generates the data; `03_silver.sql` is what actually types it.

## Never seeded

The 5 app-managed tables are written by the app or the doc pipeline, never by the seeder:
`CHAT_SESSIONS`, `CHAT_MESSAGES`, `DOCUMENT_CHUNKS`, `DOC_INGEST_LOG`, `COMPANY_KNOWLEDGE_BASE`.
