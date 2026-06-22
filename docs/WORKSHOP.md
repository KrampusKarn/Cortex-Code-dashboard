# Workshop: Build a Cortex dashboard from an API in an afternoon

A facilitator's run-of-show for delivering this kit as a hands-on workshop. The arc:
*see it built once, then build your own.*

## Learning objectives

By the end, participants can:
1. Explain the three-skill pipeline (extract → generate → scaffold) and the `schema_spec.json` contract.
2. Use Cortex Code to turn a sample API response into a validated spec.
3. Generate deterministic demo data and deploy a Streamlit-in-Snowflake dashboard.
4. Wire a Cortex RAG chat (Cortex Search + `COMPLETE`) over a knowledge base.
5. Know how to re-point the dashboard at real production data later.

## Audience & prerequisites

- Data/analytics engineers and solution architects comfortable with SQL and the terminal.
- Each participant needs: a Snowflake account with **Cortex enabled**, the **`snow` CLI** authenticated (`~/.snowflake/connections.toml`), **Python 3.9+** with `pip install -r requirements.txt`, and this repo cloned.
- Pre-flight (send the day before): run `snow connection test -c <conn>` and `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;`.

## Agenda (~3 hours)

| Time | Segment | Mode |
|---|---|---|
| 0:00–0:20 | **Why** — the problem (demo before data lands) + the pipeline overview | talk |
| 0:20–0:35 | **The contract** — walk `docs/CONTRACT.md` + a real `schema_spec.json` | talk + repo |
| 0:35–1:10 | **Live build** — facilitator builds the HRIS example from a sample API response using the 3 skills | demo |
| 1:10–1:20 | Break | — |
| 1:20–2:30 | **Lab** — participants build a dashboard for *their own* API | hands-on |
| 2:30–2:50 | **Show & tell** — a few participants demo their Assistant tab | share |
| 2:50–3:00 | **Production** — re-pointing at real data; Q&A | talk |

## Live build (facilitator script, ~35 min)

Paste a small sample HR API response — e.g. an `employees` endpoint payload with a nested array, grabbed from a public API's docs (Freshteam, BambooHR, etc.) — as the "API response" and narrate each skill:

1. **Extract** — invoke `api-schema-extraction` on that sample. Show how the response array becomes the `EMPLOYEES` table, nested arrays become child tables, and how it always adds the knowledge-base + chat tables. Validate: `python3 tools/validate_spec.py …`.
2. **Generate** — invoke `demo-data-generator`. Show the printed row counts; open a CSV; emphasize determinism (`--seed`) and currency (`--today` / relative date tokens).
3. **Scaffold** — invoke `dashboard-rag-scaffold`. For a browser-only audience: connect the repo to a Workspace, **Run All** on `deploy/workspace_setup.sql`, then create the Streamlit app *from repository*. (CLI alternative: render → `run.sh <conn>`, noting the **row-count assertion**, → `snow streamlit deploy`.) Open the app; ask the Assistant a question; show the **Sources** citations and that the current month has data.

(If time is short, deploy the prebuilt `examples/hris_people` instead of building from a sample.)

## Lab (participants, ~70 min)

"Now do it with your own API."
1. Bring a sample response (or pick a public API). Run `api-schema-extraction`.
2. `validate_spec.py` until green. Generate data. Eyeball the CSVs.
3. Render, `run.sh`, deploy. Ask your Assistant a question grounded in a small `kb_content.json` you write (5–10 docs is enough).

Facilitators float and unblock. The pitfalls table below covers ~90% of issues.

## Common pitfalls (and fixes)

| Pitfall | Fix |
|---|---|
| Assistant returns nothing | `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <role>;` and wait for the Cortex Search service's initial build. |
| Dashboard's current month is empty | Date columns used a literal past date — use `"max": "today"`, regenerate without `--today`. (This is the exact bug the kit was designed to prevent.) |
| `USE WAREHOUSE` fails | Only one warehouse name exists — `app.warehouse`. Don't type a second one anywhere. |
| A table loaded 0 rows | `run.sh`'s row-count assertion caught a `COPY INTO` header/column mismatch — fix the spec column order and reload. |
| `snow streamlit deploy` can't find the app | Run it from the bundle's `app/` directory (it contains `snowflake.yml`). |
| Spec won't validate | Read the validator's messages — usually a missing `gen` param, an `fk` to a non-existent table, or a missing chat/knowledge-base table. |

## Facilitator checklist

- [ ] Participants completed pre-flight (connection test + CORTEX_USER grant).
- [ ] Repo cloned; `pip install -r requirements.txt` done.
- [ ] A shared warehouse/database naming convention agreed (so people don't collide).
- [ ] Prebuilt `examples/hris_people` deployed as a fallback demo.
- [ ] Time-boxed the lab; kept the last 10 minutes for the production re-pointing story.
