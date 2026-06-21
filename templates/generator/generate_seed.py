#!/usr/bin/env python3
"""Config-driven synthetic seed generator for the Cortex Dashboard Kit.

Reads a `schema_spec.json` (see docs/CONTRACT.md) and writes one CSV per table.
Deterministic (fixed SEED) and stdlib-only except Faker — no pandas required.

Usage:
    python generate_seed.py --spec path/to/schema_spec.json --out path/to/seed/ \
        [--today 2026-06-21] [--seed 42]

Design notes:
  * Generation order is topologically resolved from `fk` / `per_parent` refs, so
    a foreign key always points at rows that already exist.
  * `TODAY` defaults to the real current date (override with --today), and date
    columns accept relative tokens ("-5y", "+12m", "today") — so time-series data
    always covers the current period. This is the fix for the original demo's
    "empty current month" bug, whose TODAY was pinned in the past.
  * Tables flagged `is_chat_table` get NO rows (the app writes them at runtime).

Requires: pip install faker
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker("en_US")

# ── date token resolution ────────────────────────────────────────────────────
_TOKEN = re.compile(r"^([+-]?\d+)([dmy])$")


def resolve_date(token, today: date) -> date:
    """ISO date string or relative token -> date. Tokens: 'today', '-5y', '+12m', '-90d'."""
    if isinstance(token, date):
        return token
    if token in (None, "today"):
        return today
    m = _TOKEN.match(str(token))
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "d":
            return today + timedelta(days=n)
        if unit == "m":
            return _add_months(today, n)
        if unit == "y":
            return _add_months(today, n * 12)
    return datetime.strptime(str(token), "%Y-%m-%d").date()


def _add_months(d: date, n: int) -> date:
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


# ── template rendering ("{FIRST_NAME|lower}.{LAST_NAME|lower}@acme.com") ───────
_FIELD = re.compile(r"\{([A-Z][A-Z0-9_]*)(?:\|(lower|upper|slug))?\}")


def render_template(tmpl: str, row: dict) -> str:
    def sub(m):
        val = str(row.get(m.group(1), "") or "")
        pipe = m.group(2)
        if pipe == "lower":
            return val.lower()
        if pipe == "upper":
            return val.upper()
        if pipe == "slug":
            return re.sub(r"[^a-z0-9]+", "-", val.lower()).strip("-")
        return val
    return _FIELD.sub(sub, tmpl)


# ── per-column value generation ──────────────────────────────────────────────
def gen_value(col: dict, ctx: dict):
    """ctx provides: row (so far), index, generated (all tables' rows), parent_pk, today."""
    g = col["gen"]
    row, idx = ctx["row"], ctx["index"]

    if g == "row_index":
        return ctx["global_index"]
    if g == "const":
        return col.get("value")
    if g == "choice":
        choices = col["choices"]
        weights = col.get("weights")
        return random.choices(choices, weights=weights, k=1)[0]
    if g == "int":
        return random.randint(int(col["min"]), int(col["max"]))
    if g == "float":
        v = random.uniform(float(col["min"]), float(col["max"]))
        return round(v, col["round"]) if "round" in col else v
    if g == "bool":
        return random.random() < col.get("p_true", 0.5)
    if g in ("date", "datetime"):
        lo = resolve_date(col["min"], ctx["today"])
        hi = resolve_date(col["max"], ctx["today"])
        if hi < lo:
            lo, hi = hi, lo
        d = lo + timedelta(days=random.randint(0, (hi - lo).days))
        if g == "datetime":
            dt = datetime(d.year, d.month, d.day, random.randint(8, 18), random.randint(0, 59))
            return dt.strftime(col.get("format", "%Y-%m-%d %H:%M:%S"))
        return d.strftime(col.get("format", "%Y-%m-%d"))
    if g == "sequence_date":
        anchor = resolve_date(col.get("anchor", "today"), ctx["today"])
        step = col.get("step", "month")
        i = idx
        if step == "day":
            d = anchor + timedelta(days=i)
        elif step == "week":
            d = anchor + timedelta(weeks=i)
        else:
            d = _add_months(anchor, i)
        return d.strftime(col.get("format", "%Y-%m-%d"))
    if g == "template":
        return render_template(col["template"], row)
    if g == "faker":
        return getattr(fake, col["faker_provider"])()
    if g == "fk":
        strat = col.get("fk_strategy", "random")
        if strat == "parent":
            return ctx["parent_pk"]
        ref_rows = ctx["generated"].get(col["ref_table"], [])
        ref_col = col.get("ref_column") or _pk_name(ctx["specs_by_table"][col["ref_table"]])
        if not ref_rows:
            return None
        if strat == "sequential":
            return ref_rows[idx % len(ref_rows)][ref_col]
        return random.choice(ref_rows)[ref_col]
    raise ValueError(f"unknown gen '{g}' for column {col['name']}")


def _pk_name(table: dict) -> str:
    for c in table["columns"]:
        if c.get("pk"):
            return c["name"]
    return table["columns"][0]["name"]


# ── table-level generation ───────────────────────────────────────────────────
def gen_row(table: dict, ctx: dict) -> dict:
    row: dict = {}
    ctx["row"] = row
    for col in table["columns"]:
        if "null_pct" in col and random.random() < col["null_pct"]:
            row[col["name"]] = None
            continue
        row[col["name"]] = gen_value(col, ctx)
    return row


def gen_table(table: dict, generated: dict, specs_by_table: dict, today: date, counter: dict) -> list[dict]:
    rows: list[dict] = []
    base_ctx = {"generated": generated, "specs_by_table": specs_by_table, "today": today}

    if "per_parent" in table:
        pp = table["per_parent"]
        parent_rows = generated.get(pp["parent"], [])
        parent_pk = _pk_name(specs_by_table[pp["parent"]])
        for prow in parent_rows:
            for _ in range(random.randint(pp["min"], pp["max"])):
                counter["n"] += 1
                ctx = dict(base_ctx, index=len(rows), global_index=counter["n"], parent_pk=prow[parent_pk])
                rows.append(gen_row(table, ctx))
    else:
        for i in range(table.get("row_count", 0)):
            counter["n"] += 1
            ctx = dict(base_ctx, index=i, global_index=counter["n"], parent_pk=None)
            rows.append(gen_row(table, ctx))
    return rows


# ── dependency ordering ──────────────────────────────────────────────────────
def order_tables(tables: list[dict]) -> list[dict]:
    by_name = {t["name"]: t for t in tables}
    deps: dict[str, set] = {t["name"]: set() for t in tables}
    for t in tables:
        if "per_parent" in t:
            deps[t["name"]].add(t["per_parent"]["parent"])
        for c in t["columns"]:
            if c["gen"] == "fk" and c.get("fk_strategy", "random") != "parent":
                ref = c.get("ref_table")
                if ref and ref in by_name and ref != t["name"]:
                    deps[t["name"]].add(ref)
    ordered, seen = [], set()
    def visit(name, stack):
        if name in seen:
            return
        if name in stack:        # cycle — break it, declared order wins
            return
        for d in deps[name]:
            visit(d, stack | {name})
        seen.add(name)
        ordered.append(by_name[name])
    for t in tables:
        visit(t["name"], set())
    return ordered


# ── csv writing ──────────────────────────────────────────────────────────────
def write_csv(out_dir: Path, table: dict, rows: list[dict]) -> None:
    cols = [c["name"] for c in table["columns"]]
    path = out_dir / f"{table['name']}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else _fmt(r.get(c)) for c in cols])


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD; default = real today")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    spec = json.loads(Path(args.spec).read_text())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    specs_by_table = {t["name"]: t for t in spec["tables"]}
    generated: dict[str, list[dict]] = {}
    counter = {"n": 0}

    for table in order_tables(spec["tables"]):
        if table.get("is_chat_table"):
            generated[table["name"]] = []          # DDL only; app writes rows at runtime
            continue
        counter["n"] = 0                            # pk row_index restarts per table
        rows = gen_table(table, generated, specs_by_table, today, counter)
        generated[table["name"]] = rows
        write_csv(out_dir, table, rows)
        print(f"  {table['name']:32} {len(rows):>6} rows")

    data_tables = [t for t in spec["tables"] if not t.get("is_chat_table")]
    print(f"✓ generated {len(data_tables)} CSVs into {out_dir}  (today={today}, seed={args.seed})")


if __name__ == "__main__":
    main()
