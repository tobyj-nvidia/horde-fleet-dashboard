"""JSON API routes for the Horde Fleet Dashboard."""

from fastapi import APIRouter, Depends, HTTPException

from dashboard.db import get_db
from dashboard.queries import get_task, retry_task

router = APIRouter(prefix="/api")


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
