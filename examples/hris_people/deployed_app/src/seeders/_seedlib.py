#!/usr/bin/env python3
"""Structure-driven, FK-aware synthetic data engine for the DASHBOARD_SPS app.

Unlike the kit's spec-driven templates/generator/generate_seed.py, this reads the
ACTUAL live table structure from Snowflake (INFORMATION_SCHEMA + SHOW PRIMARY KEYS),
so it adapts automatically as the schema changes. It is invoked once per data
source (OmniHR / Harvest) with that source's table list + a column
"profile" that encodes API-realistic values. Output is a .sql file of
INSERT statements (run by the per-source bash wrapper via `snow sql -f`); this
module never writes to Snowflake itself, only reads (introspection + parent keys).

  introspect  ->  INFORMATION_SCHEMA.COLUMNS + SHOW PRIMARY KEYS (via `snow ... --format json`)
  resolve FKs ->  column name / alias map -> parent table.pk (parents read live from DB
                  when they belong to another source, so sources stay decoupled)
  generate    ->  per-PK sequential ids, FK values drawn from real parents, profile or
                  type-default values for the rest
  emit        ->  [optional TRUNCATE] + batched INSERTs to --out

Faker is the only third-party dependency (already in requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker("en_US")

# ── FK resolution ────────────────────────────────────────────────────────────
# Columns whose name does not equal the parent's PK, or that are ambiguous.
# Keyed by bare COLUMN (applies anywhere) or "TABLE.COLUMN" (overrides for one table).
FK_ALIASES = {
    # EMPLOYEE_ID is the PK of EMPLOYEES *and* of the 1:1 satellites (EMPLOYEE_FIELDS,
    # EMPLOYEE_PII, …); as a non-PK column it always points at EMPLOYEES.
    "EMPLOYEE_ID": "EMPLOYEES.EMPLOYEE_ID",
    "MANAGER_ID": "EMPLOYEES.EMPLOYEE_ID",
    "HEAD_USER_ID": "EMPLOYEES.EMPLOYEE_ID",
    "ASSIGNED_TO": "EMPLOYEES.EMPLOYEE_ID",
    "CREATED_BY": "EMPLOYEES.EMPLOYEE_ID",
    "BUSINESS_UNIT_ID": "BUSINESS_UNITS.BU_ID",
    # TASK_ID is the PK of both TASKS and ONBOARDING_TASKS — disambiguate the refs:
    "TIME_ENTRIES.TASK_ID": "TASKS.TASK_ID",
    "PROJECT_TASKS.TASK_ID": "TASKS.TASK_ID",
}

# "Soft" back-references (org chart / audit): still resolved to a valid id, but they
# must NOT constrain generation order — otherwise org-chart cycles (e.g.
# BUSINESS_UNITS.HEAD_USER_ID -> EMPLOYEES while EMPLOYEES.BUSINESS_UNIT_ID -> BUSINESS_UNITS)
# would push a parent after its child and leave the hard FK NULL.
SOFT_FK_COLS = {"MANAGER_ID", "HEAD_USER_ID", "ASSIGNED_TO", "CREATED_BY"}


# ── snow CLI helpers (read-only) ──────────────────────────────────────────────
def snow_json(conn: str, query: str) -> list[dict]:
    """Run one read-only query via the snow CLI and return rows as list[dict]."""
    proc = subprocess.run(
        ["snow", "sql", "-c", conn, "--format", "json", "-q", query],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + "\n" + proc.stderr + "\n")
        raise SystemExit(f"snow query failed: {query[:80]}...")
    out = proc.stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def _ci(row: dict, *names):
    """Case-insensitive column lookup (INFORMATION_SCHEMA upper, SHOW lower)."""
    low = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def introspect(conn: str, db: str, schema: str, tables: list[str]) -> tuple[dict, dict]:
    """Return (columns_by_table, pk_by_table). columns: name/type/len/scale/nullable/identity."""
    in_list = ", ".join("'" + t + "'" for t in tables)
    rows = snow_json(conn, f"""
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
               NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, IS_IDENTITY, ORDINAL_POSITION
        FROM {db}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME IN ({in_list})
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """)
    cols: dict[str, list] = {t: [] for t in tables}
    for r in rows:
        t = _ci(r, "TABLE_NAME")
        cols.setdefault(t, []).append({
            "name": _ci(r, "COLUMN_NAME"),
            "type": (_ci(r, "DATA_TYPE") or "TEXT").upper(),
            "len": _ci(r, "CHARACTER_MAXIMUM_LENGTH"),
            "scale": _ci(r, "NUMERIC_SCALE"),
            "nullable": (_ci(r, "IS_NULLABLE") or "YES").upper() == "YES",
            "identity": (_ci(r, "IS_IDENTITY") or "NO").upper() == "YES",
        })
    # PKs for the WHOLE schema (not just targets) so cross-source FKs resolve —
    # e.g. HARVEST_USERS.EMPLOYEE_ID -> EMPLOYEES even when seeding only Harvest.
    pk_rows = snow_json(conn, f"SHOW PRIMARY KEYS IN SCHEMA {db}.{schema}")
    pk: dict[str, str] = {}
    for r in pk_rows:
        if int(_ci(r, "key_sequence") or 1) == 1:
            pk[_ci(r, "table_name")] = _ci(r, "column_name")
    return cols, pk


# ── relative date tokens ("today", "-5y", "+12m", "-90d") ─────────────────────
_TOKEN = re.compile(r"^([+-]?\d+)([dmy])$")


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def resolve_date(token, today: date) -> date:
    if token in (None, "today"):
        return today
    m = _TOKEN.match(str(token))
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return today + timedelta(days=n) if unit == "d" else _add_months(today, n * (12 if unit == "y" else 1))
    return datetime.strptime(str(token), "%Y-%m-%d").date()


# ── template rendering: "{FIRST_NAME|lower}.{LAST_NAME|lower}@x.com" ──────────
_FIELD = re.compile(r"\{([A-Z][A-Z0-9_]*)(?:\|(lower|upper|slug))?\}")


def render_template(tmpl: str, row: dict) -> str:
    def sub(m):
        val = str(row.get(m.group(1), "") or "")
        p = m.group(2)
        if p == "lower":
            return val.lower()
        if p == "upper":
            return val.upper()
        if p == "slug":
            return re.sub(r"[^a-z0-9]+", "-", val.lower()).strip("-")
        return val
    return _FIELD.sub(sub, tmpl)


# ── value generation ──────────────────────────────────────────────────────────
def gen_from_profile(spec: dict, row: dict, today: date, idx: int = 0):
    g = spec.get("gen")
    if g == "const":
        return spec.get("value")
    if g == "choice":
        return random.choices(spec["choices"], weights=spec.get("weights"), k=1)[0]
    if g == "enumerate":
        # deterministic distinct values for small dimension tables (row N -> choices[N]).
        return spec["choices"][idx % len(spec["choices"])]
    if g == "int":
        return random.randint(int(spec["min"]), int(spec["max"]))
    if g == "float":
        v = random.uniform(float(spec["min"]), float(spec["max"]))
        return round(v, spec.get("round", 2))
    if g == "bool":
        return random.random() < spec.get("p_true", 0.5)
    if g in ("date", "datetime"):
        lo, hi = resolve_date(spec["min"], today), resolve_date(spec["max"], today)
        if hi < lo:
            lo, hi = hi, lo
        d = lo + timedelta(days=random.randint(0, (hi - lo).days))
        if g == "datetime":
            return datetime(d.year, d.month, d.day, random.randint(8, 18), random.randint(0, 59)).strftime("%Y-%m-%d %H:%M:%S")
        return d.strftime("%Y-%m-%d")
    if g == "template":
        return render_template(spec["template"], row)
    if g == "faker":
        return getattr(fake, spec["faker_provider"])(*spec.get("faker_args", []))
    raise ValueError(f"unknown profile gen '{g}'")


def gen_default(col: dict, today: date):
    """Type-based fallback when no profile entry covers the column."""
    t = col["type"]
    if any(k in t for k in ("NUMBER", "DECIMAL", "NUMERIC", "INT", "FLOAT", "DOUBLE", "REAL")):
        scale = col.get("scale") or 0
        if scale and int(scale) > 0:
            return round(random.uniform(0, 5000), int(scale))
        return random.randint(1, 500)
    if t == "BOOLEAN":
        return random.random() < 0.5
    if t == "DATE":
        return (today - timedelta(days=random.randint(0, 1095))).strftime("%Y-%m-%d")
    if t.startswith("TIMESTAMP") or t == "DATETIME":
        d = today - timedelta(days=random.randint(0, 365))
        return datetime(d.year, d.month, d.day, random.randint(8, 18), random.randint(0, 59)).strftime("%Y-%m-%d %H:%M:%S")
    n = col.get("len") or 40
    if n <= 20:
        return fake.word()[:n]
    if n <= 80:
        return fake.sentence(nb_words=4)[:n].rstrip(".")
    return fake.sentence(nb_words=10)[:n]


# ── SQL literal formatting (mirrors templates/render.py:sql_literal) ──────────
_NUMERIC = ("NUMBER", "INT", "FLOAT", "DECIMAL", "DOUBLE", "REAL", "NUMERIC")


def sql_literal(value, col_type: str) -> str:
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if any(k in col_type.upper() for k in _NUMERIC):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


# ── ordering ──────────────────────────────────────────────────────────────────
def order_targets(targets: list[str], fk_edges: dict) -> list[str]:
    """Topologically order target tables by intra-target FK edges (external parents ignored)."""
    deps = {t: set() for t in targets}
    for t in targets:
        for parent in fk_edges.get(t, {}).values():
            if parent in deps and parent != t:
                deps[t].add(parent)
    ordered, seen = [], set()

    def visit(n, stack):
        if n in seen or n in stack:
            return
        for d in deps[n]:
            visit(d, stack | {n})
        seen.add(n)
        ordered.append(n)
    for t in targets:
        visit(t, set())
    return ordered


def resolve_fk(table: str, col: str, pk_index: dict) -> str | None:
    """Return 'PARENT.PKCOL' if col is a foreign key, else None."""
    if f"{table}.{col}" in FK_ALIASES:
        return FK_ALIASES[f"{table}.{col}"]
    if col in FK_ALIASES:
        return FK_ALIASES[col]
    owners = [t for t in pk_index.get(col, []) if t != table]
    return f"{owners[0]}.{col}" if len(owners) == 1 else None


# ── core generation (shared by the seeders and the mock API) ──────────────────
def build_rows(cols, pk, targets, profile, default_rows=50, today=None,
               fetch_external=None):
    """Generate FK-coherent synthetic rows for `targets`. Pure: never writes to DB.

    ONE generation engine, two callers: the seeders feed structure from
    introspect() (live), the mock API feeds it from a parsed schema — so the
    data shape can never drift between "load into Snowflake" and "serve over HTTP".

      cols/pk        : {table: [col dicts]} / {table: pk_col}. The whole schema is
                       fine — FK inference indexes every pk; only `targets` are built.
      profile        : {"tables": {T: {"rows": n}}, "columns": {"T.C": spec}}.
      default_rows   : rows per table when the profile gives no count.
      today          : anchor for relative date tokens (defaults to date.today()).
      fetch_external : optional callable(parent_fqcol) -> [ids] for a parent NOT in
                       `targets` (cross-source). Seeders pass a live DB reader; an
                       all-in-memory caller omits it (missing parents -> NULL FKs).

    Returns (order, data): topological table order and {table: [row dict]}.
    The caller seeds random/Faker beforehand for determinism.
    """
    if today is None:
        today = date.today()
    prof_tables = profile.get("tables", {})
    prof_cols = profile.get("columns", {})

    # PK index: pk column name -> [tables having it] (for generic FK inference)
    pk_index: dict[str, list] = {}
    for t, c in pk.items():
        pk_index.setdefault(c, []).append(t)

    # FK edges per table: column -> parent table (soft back-refs excluded from order)
    fk_edges: dict[str, dict] = {}
    for t in targets:
        edges = {}
        for col in cols[t]:
            cn = col["name"]
            if cn == pk.get(t):
                continue
            parent = resolve_fk(t, cn, pk_index)
            if parent:
                col["_fk"] = parent
                if cn not in SOFT_FK_COLS:           # soft back-refs don't constrain order
                    edges[cn] = parent.split(".")[0]
        fk_edges[t] = edges

    order = order_targets(targets, fk_edges)

    def prof_for(table, colname):
        return prof_cols.get(f"{table}.{colname}") or prof_cols.get(f"*.{colname}")

    generated_pks: dict[str, list] = {}          # table -> list of assigned PK ids (this run)
    external_keys: dict[str, list] = {}          # "PARENT.PK" -> keys from fetch_external

    def parent_keys(parent_fqcol: str):
        ptable, _pcol = parent_fqcol.split(".")
        if ptable in generated_pks:              # generated in this run
            return generated_pks[ptable]
        if fetch_external is None:               # in-memory caller: no external source
            return []
        if parent_fqcol not in external_keys:
            external_keys[parent_fqcol] = fetch_external(parent_fqcol)
        return external_keys[parent_fqcol]

    data: dict[str, list] = {}
    for t in order:
        tcols = cols[t]
        pkcol = pk.get(t)
        n = prof_tables.get(t, {}).get("rows", default_rows)
        # PK ids assigned up-front (1..n) so children + self-refs can reference them.
        ids = list(range(1, n + 1)) if pkcol else [None] * n
        if pkcol:
            generated_pks[t] = ids

        rows_out = []
        for i in range(n):
            row: dict = {}
            if pkcol:
                row[pkcol] = ids[i]
            # pass 1: non-template columns
            for col in tcols:
                cn = col["name"]
                if cn == pkcol:
                    continue
                spec = prof_for(t, cn)
                if spec and spec.get("gen") == "template":
                    continue  # pass 2
                if "_fk" in col:
                    keys = parent_keys(col["_fk"])
                    if col["_fk"].split(".")[0] == t:        # self-reference (e.g. MANAGER_ID)
                        keys = [k for k in ids[:i]]          # only earlier rows, avoids self
                    np = (spec or {}).get("null_pct", 0.0)
                    row[cn] = (None if (not keys or random.random() < np) else random.choice(keys))
                    continue
                if spec:
                    if "null_pct" in spec and random.random() < spec["null_pct"]:
                        row[cn] = None
                    else:
                        row[cn] = gen_from_profile(spec, row, today, i)
                else:
                    row[cn] = gen_default(col, today)
            # pass 2: templates (may reference any column set above, incl. PK)
            for col in tcols:
                spec = prof_for(t, col["name"])
                if spec and spec.get("gen") == "template":
                    row[col["name"]] = render_template(spec["template"], row)
            rows_out.append(row)
        data[t] = rows_out
    return order, data


# ── main generation (seeder CLI) ──────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Structure-driven synthetic data generator (one source).")
    ap.add_argument("--connection", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--tables", required=True, help="comma-separated table list for this source")
    ap.add_argument("--profile", required=True, help="path to the source's column-profile JSON")
    ap.add_argument("--out", required=True, help="output .sql path")
    ap.add_argument("--rows", type=int, default=50, help="default rows per table (profile can override)")
    ap.add_argument("--reset", action="store_true", help="emit TRUNCATE before INSERTs")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)
    today = date.today()

    targets = [t.strip() for t in args.tables.split(",") if t.strip()]
    profile = json.loads(Path(args.profile).read_text())

    cols, pk = introspect(args.connection, args.database, args.schema, targets)
    missing = [t for t in targets if not cols.get(t)]
    if missing:
        raise SystemExit(f"tables not found in {args.database}.{args.schema}: {missing}")

    def fetch_external(parent_fqcol: str):
        """Cross-source parent keys, read live from the DB (seeder mode)."""
        _ptable, pcol = parent_fqcol.split(".")
        rows = snow_json(
            args.connection,
            f"SELECT {pcol} AS K FROM {args.database}.{args.schema}.{_ptable}")
        return [r.get("K") for r in rows if r.get("K") is not None]

    order, data = build_rows(cols, pk, targets, profile, args.rows, today, fetch_external)

    out_parts: list[str] = [
        "-- Generated by _seedlib.py — synthetic data for ONE source. Do not hand-edit.",
        f"-- target: {args.database}.{args.schema}  tables: {len(targets)}  seed: {args.seed}",
        "USE ROLE ACCOUNTADMIN;",
        f"USE SCHEMA {args.database}.{args.schema};",
        "",
    ]
    if args.reset:
        out_parts.append("-- reset: wipe target tables before reload")
        for t in reversed(order):
            out_parts.append(f"TRUNCATE TABLE IF EXISTS {t};")
        out_parts.append("")

    for t in order:
        tcols = cols[t]
        rows_out = data[t]
        colnames = [c["name"] for c in tcols]
        types = {c["name"]: c["type"] for c in tcols}
        out_parts.append(f"-- {t}: {len(rows_out)} rows")
        for start in range(0, len(rows_out), 500):
            chunk = rows_out[start:start + 500]
            values = ",\n".join(
                "    (" + ", ".join(sql_literal(r.get(c), types[c]) for c in colnames) + ")"
                for r in chunk)
            out_parts.append(f"INSERT INTO {t} ({', '.join(colnames)}) VALUES\n{values};")
        out_parts.append("")

    Path(args.out).write_text("\n".join(out_parts), encoding="utf-8")
    print(f"✓ wrote {args.out}  ({len(order)} tables, order: {', '.join(order)})")


if __name__ == "__main__":
    main()
