"""JSON API routes for the Horde Fleet Dashboard."""

from fastapi import APIRouter, Depends

from dashboard.db import get_db
from dashboard.queries import get_nodes, get_queue_counts

router = APIRouter(prefix="/api")

ALL_STATUSES = ("pending", "claimed", "running", "completed", "failed", "dead-letter")


@router.get("/nodes")
async def nodes(conn=Depends(get_db)):
    node_list = await get_nodes(conn)
    return {"nodes": node_list}


@router.get("/metrics/summary")
async def metrics_summary(conn=Depends(get_db)):
    queue_counts = await get_queue_counts(conn)
    node_list = await get_nodes(conn)

    # Ensure all status keys are present
    counts = {s: queue_counts.get(s, 0) for s in ALL_STATUSES}

    active_tasks = counts.get("claimed", 0) + counts.get("running", 0)
    nodes_online = sum(1 for n in node_list if n.get("status") == "active")

    return {
        "queue_counts": counts,
        "active_tasks": active_tasks,
        "nodes_online": nodes_online,
    }
