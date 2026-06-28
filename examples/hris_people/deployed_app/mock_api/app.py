#!/usr/bin/env python3
"""Mock OmniHR + Harvest API for the DASHBOARD_SPS / Employee 360 demo.

Boots a FastAPI server that serves the SAME synthetic data the seeders load into
Snowflake (generated at startup from the seeder profiles), shaped like the real
OmniHR (Omni API v1) and Harvest (v2) APIs. Point Snowflake at it (via an
External Access Integration over an HTTPS tunnel) and extract every endpoint into
Bronze — the "Extract" of the medallion (Bronze -> Silver -> Gold) demo.

Run:
    pip install -r requirements.txt
    ./run.sh                 # or: uvicorn app:api --host 0.0.0.0 --port 8000
Browse:
    GET /                    -> index of endpoints
    GET /docs                -> Swagger UI (auto)
    GET /api/v1/employees    -> OmniHR-style, paginated, nested JSON
    GET /v2/time_entries     -> Harvest-style, paginated, nested JSON

Determinism: SEED env var (default 42). Currency: dates use relative tokens, so
the data always covers the current period (pin with MOCK_TODAY=YYYY-MM-DD).
"""
from __future__ import annotations

import math
import os
from datetime import date

from fastapi import FastAPI, Request

import dataset
from endpoints import endpoint_specs

SEED = int(os.environ.get("SEED", "42"))
_today_env = os.environ.get("MOCK_TODAY")
TODAY = date.fromisoformat(_today_env) if _today_env else None

# Generate the whole OmniHR+Harvest graph ONCE at import (FK-coherent, deterministic).
_ORDER, DATA, COLS, PK, SOURCE_OF = dataset.build(seed=SEED, today=TODAY)
SPECS = endpoint_specs(PK)
SPEC_BY_TABLE = {s["table"]: s for s in SPECS}

api = FastAPI(
    title="OmniHR + Harvest mock API (DASHBOARD_SPS demo)",
    description="Synthetic OmniHR (Omni API v1) and Harvest (v2) endpoints for the "
                "Cortex Code medallion-ELT demo. Same data the seeders load into Snowflake.",
    version="1.0.0",
)


def _page_args(request: Request, default_size: int) -> tuple[int, int]:
    qp = request.query_params
    try:
        page = max(1, int(qp.get("page", "1")))
    except ValueError:
        page = 1
    size_key = "page_size" if "page_size" in qp else "per_page"
    try:
        size = int(qp.get(size_key, str(default_size)))
    except ValueError:
        size = default_size
    return page, max(1, min(size, 1000))


def _omnihr_envelope(spec, items, page, size, base):
    total = len(items)
    start = (page - 1) * size
    window = [spec["serializer"](r) for r in items[start:start + size]]
    has_next = start + size < total
    return {
        "count": total,
        "next": f"{base}{spec['path']}?page={page + 1}&page_size={size}" if has_next else None,
        "previous": f"{base}{spec['path']}?page={page - 1}&page_size={size}" if page > 1 else None,
        "results": window,
    }


def _harvest_envelope(spec, items, page, size, base):
    total = len(items)
    pages = max(1, math.ceil(total / size))
    start = (page - 1) * size
    window = [spec["serializer"](r) for r in items[start:start + size]]
    return {
        spec["resource"]: window,
        "per_page": size,
        "total_pages": pages,
        "total_entries": total,
        "page": page,
        "next_page": page + 1 if page < pages else None,
        "previous_page": page - 1 if page > 1 else None,
        "links": {
            "first": f"{base}{spec['path']}?page=1&per_page={size}",
            "next": f"{base}{spec['path']}?page={page + 1}&per_page={size}" if page < pages else None,
            "previous": f"{base}{spec['path']}?page={page - 1}&per_page={size}" if page > 1 else None,
            "last": f"{base}{spec['path']}?page={pages}&per_page={size}",
        },
    }


def _make_list_handler(spec):
    default_size = 50 if spec["source"] == "omnihr" else 100

    async def handler(request: Request):
        page, size = _page_args(request, default_size)
        base = str(request.base_url).rstrip("/")
        rows = DATA[spec["table"]]
        if spec["source"] == "omnihr":
            return _omnihr_envelope(spec, rows, page, size, base)
        return _harvest_envelope(spec, rows, page, size, base)

    return handler


for _spec in SPECS:
    api.add_api_route(
        _spec["path"], _make_list_handler(_spec),
        methods=["GET"], name=f"list_{_spec['table'].lower()}",
        summary=f"List {_spec['table']} ({_spec['source']})", tags=[_spec["source"]],
    )


@api.get("/", tags=["meta"])
async def index(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "service": "OmniHR + Harvest mock API",
        "purpose": "Extract source for the Cortex Code Bronze->Silver->Gold demo",
        "seed": SEED,
        "docs": f"{base}/docs",
        "openapi": f"{base}/openapi.json",
        "endpoints": [
            {
                "source": s["source"],
                "table": s["table"],
                "rows": len(DATA[s["table"]]),
                "list": f"{base}{s['path']}",
            }
            for s in SPECS
        ],
    }


@api.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "tables": len(DATA), "rows": sum(len(v) for v in DATA.values())}
