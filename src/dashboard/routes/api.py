"""REST API routes for the Horde Fleet Dashboard."""

from fastapi import APIRouter, HTTPException, Query

from dashboard.db import get_pool
from dashboard.queries import get_task, get_tasks

VALID_STATUSES = {"pending", "claimed", "running", "completed", "failed", "dead-letter"}

router = APIRouter()


@router.get("/tasks")
async def list_tasks(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {status!r}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        tasks, total = await get_tasks(conn, status=status, limit=limit, offset=offset)
    return {"tasks": tasks, "total": total}


@router.get("/tasks/{task_id}")
async def task_detail(task_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        data = await get_task(conn, task_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return data
