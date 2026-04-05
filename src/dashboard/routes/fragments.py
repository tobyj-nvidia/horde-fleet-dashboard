"""HTMX fragment routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.db import get_db
from dashboard.queries import (
    get_active_tasks,
    get_dead_letter,
    get_duration_percentiles,
    get_failure_rate,
    get_nodes,
    get_queue_counts,
    get_throughput,
    get_token_spend,
)
from dashboard.sparkline import sparkline

BASE_DIR = Path(__file__).parent.parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


def _format_elapsed(running_sec) -> str:
    if running_sec is None or running_sec < 0:
        return "—"
    secs = int(running_sec)
    minutes = secs // 60
    seconds = secs % 60
    return f"{minutes}m {seconds}s"


@router.get("/fragments/queue-counts", response_class=HTMLResponse)
async def fragment_queue_counts(request: Request, conn=Depends(get_db)):
    counts = await get_queue_counts(conn)
    return templates.TemplateResponse(
        "fragments/queue_counts.html",
        {"request": request, "counts": counts},
    )


@router.get("/fragments/active-tasks", response_class=HTMLResponse)
async def fragment_active_tasks(request: Request, conn=Depends(get_db)):
    tasks = await get_active_tasks(conn)
    for task in tasks:
        task["_elapsed"] = _format_elapsed(task.get("running_sec"))
    return templates.TemplateResponse(
        "fragments/active_tasks.html",
        {"request": request, "tasks": tasks},
    )


@router.get("/fragments/nodes", response_class=HTMLResponse)
async def fragment_nodes(request: Request, conn=Depends(get_db)):
    nodes = await get_nodes(conn)
    return templates.TemplateResponse(
        "fragments/nodes.html",
        {"request": request, "nodes": nodes},
    )


@router.get("/fragments/dead-letter", response_class=HTMLResponse)
async def fragment_dead_letter(request: Request, conn=Depends(get_db)):
    dead_letter = await get_dead_letter(conn)
    return templates.TemplateResponse(
        "fragments/dead_letter.html",
        {"request": request, "tasks": dead_letter},
    )


@router.get("/fragments/throughput", response_class=HTMLResponse)
async def fragment_throughput(request: Request, conn=Depends(get_db)):
    buckets = await get_throughput(conn)
    spark = sparkline([b["total"] for b in buckets])
    return templates.TemplateResponse(
        "fragments/throughput.html",
        {"request": request, "buckets": buckets, "spark": spark},
    )


@router.get("/fragments/tokens", response_class=HTMLResponse)
async def fragment_tokens(request: Request, conn=Depends(get_db)):
    rows = await get_token_spend(conn)
    total_usd = sum(r["total_usd"] or 0 for r in rows)
    return templates.TemplateResponse(
        "fragments/tokens.html",
        {"request": request, "rows": rows, "total_usd": total_usd},
    )


@router.get("/fragments/failures", response_class=HTMLResponse)
async def fragment_failures(request: Request, conn=Depends(get_db)):
    buckets = await get_failure_rate(conn)
    spark = sparkline([b["failures"] for b in buckets])
    return templates.TemplateResponse(
        "fragments/failures.html",
        {"request": request, "buckets": buckets, "spark": spark},
    )


@router.get("/fragments/duration", response_class=HTMLResponse)
async def fragment_duration(request: Request, conn=Depends(get_db)):
    data = await get_duration_percentiles(conn)
    no_data = all(v is None for v in data.values())

    def fmt(sec):
        if sec is None:
            return "—"
        secs = int(sec)
        return f"{secs // 60}m {secs % 60}s"

    return templates.TemplateResponse(
        "fragments/duration.html",
        {
            "request": request,
            "no_data": no_data,
            "p50": fmt(data["p50_sec"]),
            "p95": fmt(data["p95_sec"]),
            "p99": fmt(data["p99_sec"]),
            "avg": fmt(data["avg_sec"]),
        },
    )
