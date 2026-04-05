"""JSON API routes for the Horde Fleet Dashboard."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.db import get_db
from dashboard.queries import get_task, get_tasks

VALID_STATUSES = {"pending", "claimed", "running", "completed", "failed", "dead-letter"}

api_router = APIRouter()


@api_router.get("/tasks")
async def list_tasks(
    status: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn=Depends(get_db),
):
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {status!r}")
    tasks, total = await get_tasks(conn, status=status, limit=limit, offset=offset)
    return {"tasks": tasks, "total": total}


@api_router.get("/tasks/{task_id}")
async def get_task_detail(task_id: str, conn=Depends(get_db)):
    data = await get_task(conn, task_id)
    if data is None:
        raise HTTPException(status_code=404, detail="not found")
    return data
