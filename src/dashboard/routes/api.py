"""JSON API routes for the Horde Fleet Dashboard."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.db import get_db
from dashboard.queries import (
    get_duration_percentiles,
    get_failure_rate,
    get_throughput,
    get_token_spend,
)

router = APIRouter(prefix="/api")

_WINDOW_MAP: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}


def _parse_window(window: str) -> int:
    if window not in _WINDOW_MAP:
        raise HTTPException(status_code=422, detail="Invalid window: must be 7d, 30d, or 90d")
    return _WINDOW_MAP[window]


@router.get("/metrics/throughput")
async def metrics_throughput(
    window: Annotated[str, Query()] = "7d",
    db=Depends(get_db),
):
    days = _parse_window(window)
    rows = await get_throughput(db, days)
    buckets = [
        {
            "date": str(row["date"]),
            "total": row["total"],
            "success": row["success"],
            "failure": row["failure"],
        }
        for row in rows
    ]
    return {"buckets": buckets}


@router.get("/metrics/tokens")
async def metrics_tokens(
    window: Annotated[str, Query()] = "7d",
    db=Depends(get_db),
):
    days = _parse_window(window)
    rows = await get_token_spend(db, days)
    by_provider_model = [
        {
            "provider": row["provider"],
            "model": row["model"],
            "total_tokens": row["total_tokens"],
            "total_usd": round(float(row["total_usd"]), 4) if row["total_usd"] is not None else 0.0,
        }
        for row in rows
    ]
    return {"by_provider_model": by_provider_model}


@router.get("/metrics/failures")
async def metrics_failures(
    window: Annotated[str, Query()] = "7d",
    db=Depends(get_db),
):
    days = _parse_window(window)
    rows = await get_failure_rate(db, days)
    buckets = [
        {
            "date": str(row["date"]),
            "total": row["total"],
            "failures": row["failures"],
            "failure_pct": row["failure_pct"],
        }
        for row in rows
    ]
    return {"buckets": buckets}


@router.get("/metrics/duration")
async def metrics_duration(
    window: Annotated[str, Query()] = "7d",
    db=Depends(get_db),
):
    days = _parse_window(window)
    data = await get_duration_percentiles(db, days)
    return {
        "p50_sec": data["p50_sec"],
        "p95_sec": data["p95_sec"],
        "p99_sec": data["p99_sec"],
        "avg_sec": data["avg_sec"],
    }
