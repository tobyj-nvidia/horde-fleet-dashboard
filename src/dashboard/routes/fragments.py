"""HTMX fragment routes for historical metric panels."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.db import get_db
from dashboard.queries import (
    get_duration_percentiles,
    get_failure_rate,
    get_throughput,
    get_token_spend,
)
from dashboard.sparkline import sparkline

router = APIRouter()

_TEMPLATES = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def _fmt_duration(seconds) -> str:
    """Format a duration in seconds as 'Xm Ys'."""
    if seconds is None:
        return "—"
    secs = int(round(float(seconds)))
    m, s = divmod(secs, 60)
    return f"{m}m {s}s"


@router.get("/fragments/throughput", response_class=HTMLResponse)
async def fragment_throughput(request: Request, conn=Depends(get_db)):
    buckets = await get_throughput(conn, window_days=7)
    spark = sparkline([b["total"] for b in buckets]) if buckets else ""
    return _TEMPLATES.TemplateResponse(
        "fragments/throughput.html",
        {"request": request, "buckets": buckets, "spark": spark},
    )


@router.get("/fragments/tokens", response_class=HTMLResponse)
async def fragment_tokens(request: Request, conn=Depends(get_db)):
    rows = await get_token_spend(conn, window_days=7)
    total_usd = sum(float(r["total_usd"] or 0) for r in rows)
    return _TEMPLATES.TemplateResponse(
        "fragments/tokens.html",
        {"request": request, "rows": rows, "total_usd": total_usd},
    )


@router.get("/fragments/failures", response_class=HTMLResponse)
async def fragment_failures(request: Request, conn=Depends(get_db)):
    buckets = await get_failure_rate(conn, window_days=7)
    spark = sparkline([int(b["failures"]) for b in buckets]) if buckets else ""
    return _TEMPLATES.TemplateResponse(
        "fragments/failures.html",
        {"request": request, "buckets": buckets, "spark": spark},
    )


@router.get("/fragments/duration", response_class=HTMLResponse)
async def fragment_duration(request: Request, conn=Depends(get_db)):
    data = await get_duration_percentiles(conn, window_days=7)
    no_data = data.get("p50_sec") is None and data.get("p95_sec") is None
    return _TEMPLATES.TemplateResponse(
        "fragments/duration.html",
        {
            "request": request,
            "no_data": no_data,
            "p50": _fmt_duration(data.get("p50_sec")),
            "p95": _fmt_duration(data.get("p95_sec")),
            "p99": _fmt_duration(data.get("p99_sec")),
            "avg": _fmt_duration(data.get("avg_sec")),
        },
    )
