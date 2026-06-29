#!/usr/bin/env python3
"""Structure-driven, FK-aware synthetic data ENGINE for the DASHBOARD_SPS app.

The one generator behind both data paths: the mock API (`../../mock_api/dataset.py`)
and the offline Bronze seeder (`seed_bronze.py`) both call `build_rows()` with the
same profiles, so the data they produce can never drift. Given a table structure +
a column "profile" (API-realistic values), it generates FK-coherent rows in memory —
it never touches Snowflake.

  resolve FKs ->  column name / alias map -> parent table.pk
  generate    ->  per-PK sequential ids, FK values drawn from real parents, profile or
                  type-default values for the rest

Faker is the only third-party dependency (already in requirements.txt).
"""
from __future__ import annotations

import random
import re
from datetime import date, datetime, timedelta

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


# ── core generation (shared by the mock API and the offline Bronze seeder) ────
def build_rows(cols, pk, targets, profile, default_rows=50, today=None,
               fetch_external=None):
    """Generate FK-coherent synthetic rows for `targets`. Pure: never writes to DB.

    ONE generation engine, two callers: the mock API (serve over HTTP) and the
    offline Bronze seeder (load into Snowflake) both feed structure from the parsed
    schema (mock_api/schema.py reads 00_setup.sql) — so the data shape can never drift.

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
