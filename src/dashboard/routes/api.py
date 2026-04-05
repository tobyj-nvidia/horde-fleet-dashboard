"""JSON API routes for the Horde Fleet Dashboard."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.db import get_db
from dashboard.queries import (
    get_duration_percentiles,
    get_failure_rate,
    get_nodes,
    get_queue_counts,
    get_task,
    get_tasks,
    get_throughput,
    get_token_spend,
    retry_task,
)

router = APIRouter(prefix="/api")

VALID_STATUSES = {"pending", "claimed", "running", "completed", "failed", "dead-letter"}
ALL_STATUSES = ("pending", "claimed", "running", "completed", "failed", "dead-letter")
_WINDOW_MAP: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}


def _parse_window(window: str) -> int:
    if window not in _WINDOW_MAP:
        raise HTTPException(status_code=422, detail="Invalid window: must be 7d, 30d, or 90d")
    return _WINDOW_MAP[window]


# ── Task endpoints (T-005/T-006) ─────────────────────────────────────────────


@router.get("/tasks")
async def list_tasks(
    status: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn=Depends(get_db),
):
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {status!r}")
    if limit > 200:
        limit = 200
    tasks, total = await get_tasks(conn, status=status, limit=limit, offset=offset)
    return {"tasks": tasks, "total": total}


@router.get("/tasks/{task_id}")
async def get_task_detail(task_id: str, conn=Depends(get_db)):
    data = await get_task(conn, task_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return data


# ── Node endpoints (T-007/T-008) ─────────────────────────────────────────────


@router.get("/nodes")
async def nodes(conn=Depends(get_db)):
    node_list = await get_nodes(conn)
    return {"nodes": node_list}


@router.get("/metrics/summary")
async def metrics_summary(conn=Depends(get_db)):
    queue_counts = await get_queue_counts(conn)
    node_list = await get_nodes(conn)
    counts = {s: queue_counts.get(s, 0) for s in ALL_STATUSES}
    active_tasks = counts.get("claimed", 0) + counts.get("running", 0)
    nodes_online = sum(1 for n in node_list if n.get("status") == "active")
    return {
        "queue_counts": counts,
        "active_tasks": active_tasks,
        "nodes_online": nodes_online,
    }


# ── Trend endpoints (T-009) ──────────────────────────────────────────────────


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


# ── Retry endpoint (T-010) ───────────────────────────────────────────────────


@router.post("/tasks/{task_id}/retry")
async def retry_task_endpoint(task_id: str, conn=Depends(get_db)):
    task_data = await get_task(conn, task_id)
    if task_data is None:
        raise HTTPException(status_code=404, detail="not found")
    if task_data["task"]["status"] != "dead-letter":
        raise HTTPException(
            status_code=409,
            detail=f"task status is '{task_data['task']['status']}', not 'dead-letter'",
        )
    await retry_task(conn, task_id)
    return {"task_id": task_id, "status": "pending"}
