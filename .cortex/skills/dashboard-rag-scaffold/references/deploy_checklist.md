# Deploy checklist (ordered commands)

Replace `<conn>` with your `snow` connection name and `<SPEC>` with the path to your spec.
For the worked examples, `<SPEC>` is e.g. `examples/hris_people/schema_spec.json` and the
bundle renders in place (so `--out` is the example directory).

```bash
# 0. Sanity: connection works
snow connection test -c <conn>

# 1. (once per account) grant Cortex access to the deploy role
snow sql -c <conn> -q "GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;"

# 2. Validate the spec and (re)generate the seed data
python3 tools/validate_spec.py <SPEC>
python3 templates/generator/generate_seed.py --spec <SPEC> --out examples/hris_people/seed --today 2026-06-22

# 3. Render the deployable bundle (deploy/ + app/)
python3 templates/render.py --spec <SPEC> --out examples/hris_people

# 4. Bootstrap + DDL + load + Cortex Search + row-count verification
examples/hris_people/deploy/run.sh <conn>

# 5. Confirm the Cortex Search service exists and finished indexing
snow sql -c <conn> -q "SHOW CORTEX SEARCH SERVICES IN SCHEMA DEMO_EMPLOYEE_APP.PUBLIC;"

# 6. Deploy the Streamlit app (multi-file; reads snowflake.yml in this dir)
cd examples/hris_people/app
snow streamlit deploy --connection <conn> --replace
cd -

# 7. Open the URL printed by step 6. In the Assistant tab, ask a suggested prompt
#    and confirm a grounded answer with a Sources expander.
```

## What `run.sh` does (step 4 expanded)

1. `snow sql -f 00_bootstrap.sql` — warehouse, database, schema, `DEMO_SEED_STAGE`, `STREAMLIT_STAGE`.
2. `snow sql -f 01_ddl.sql` — all tables.
3. `PUT file://../seed/*.csv @<db>.<schema>.<stage>` — upload every seed CSV.
4. `snow sql -f 05_load_seed.sql` — `COPY INTO` each data table.
5. `snow sql -f 04_cortex_search.sql` — create the Cortex Search service.
6. Row-count assertion — `SELECT COUNT(*)` per data table; **exits non-zero if any is empty**.

If you prefer manual control, run steps 1–5 with individual `snow sql -c <conn> -f <file>` calls.
