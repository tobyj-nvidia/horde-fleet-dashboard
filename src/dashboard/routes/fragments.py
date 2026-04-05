"""HTMX fragment routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.db import get_db
from dashboard.queries import get_dead_letter, get_nodes

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


@router.get("/fragments/nodes", response_class=HTMLResponse)
async def fragment_nodes(request: Request, conn=Depends(get_db)):
    nodes = await get_nodes(conn)
    return templates.TemplateResponse(
        "fragments/nodes.html", {"request": request, "nodes": nodes}
    )


@router.get("/fragments/dead-letter", response_class=HTMLResponse)
async def fragment_dead_letter(request: Request, conn=Depends(get_db)):
    rows = await get_dead_letter(conn, limit=20)
    tasks = []
    for row in rows:
        # Build prompt snippet from payload JSON if available, else use error_msg
        prompt_snippet = ""
        if row.get("error_msg"):
            prompt_snippet = row["error_msg"][:80]

        # Compute seconds since failure (use completed_at or updated_at)
        failure_age_sec = None
        ts = row.get("completed_at") or row.get("updated_at")
        if ts is not None:
            import datetime
            now = datetime.datetime.utcnow()
            if hasattr(ts, "timetuple"):
                delta = now - ts
                failure_age_sec = int(delta.total_seconds())

        tasks.append({
            **row,
            "prompt_snippet": prompt_snippet,
            "failure_age_sec": failure_age_sec,
        })
    return templates.TemplateResponse(
        "fragments/dead_letter.html", {"request": request, "tasks": tasks}
    )
