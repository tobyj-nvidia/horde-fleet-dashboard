"""HTMX fragment routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.db import get_db
from dashboard.queries import get_active_tasks, get_queue_counts

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
