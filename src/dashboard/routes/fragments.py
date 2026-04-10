"""HTMX fragment routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.db import get_db
from dashboard.charts import render_line_chart
from dashboard.recovery_metrics import get_active_investigations, get_blocked_chains, get_failure_patterns, get_recovery_overview
from dashboard.queries import (
    get_active_tasks,
    get_blocked_operations,
    get_pending_tasks,
    get_dead_letter,
    get_duration_percentiles,
    get_failure_rate,
    get_node_metrics_history,
    get_node_metrics_latest,
    get_node_utilization_history,
    get_nodes,
    get_queue_counts,
    get_recent_completed,
    get_recent_failed,
    get_security_overview,
    get_throughput,
    get_token_spend,
    get_token_spend_summary,
    get_security_incident,
    get_unreviewed_alerts,
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


@router.get("/fragments/pending-tasks", response_class=HTMLResponse)
async def fragment_pending_tasks(request: Request, conn=Depends(get_db)):
    tasks = await get_pending_tasks(conn)
    for task in tasks:
        task["_queue_time"] = _format_elapsed(task.get("queue_seconds"))
    return templates.TemplateResponse(
        "fragments/pending_tasks.html",
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


@router.get("/fragments/token-spend", response_class=HTMLResponse)
async def fragment_token_spend(request: Request, period: int = 1, conn=Depends(get_db)):
    rows = await get_token_spend_summary(conn, period_days=period)
    for r in rows:
        r["total_cost_usd"] = float(r["total_cost_usd"] or 0)
        r["total_tokens"] = int(r["total_tokens"] or 0)
    total_tokens = sum(r["total_tokens"] for r in rows)
    total_cost_usd = sum(r["total_cost_usd"] for r in rows)
    return templates.TemplateResponse(
        "fragments/token_spend.html",
        {
            "request": request,
            "rows": rows,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "period": period,
        },
    )


@router.get("/fragments/tokens", response_class=HTMLResponse)
async def fragment_tokens(request: Request, conn=Depends(get_db)):
    rows = await get_token_spend(conn)
    for r in rows:
        r["total_usd"] = float(r["total_usd"] or 0)
    total_usd = sum(r["total_usd"] for r in rows)
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


@router.get("/fragments/node-metrics", response_class=HTMLResponse)
async def fragment_node_metrics(request: Request, conn=Depends(get_db)):
    latest = await get_node_metrics_latest(conn)
    history = await get_node_metrics_history(conn, window_hours=1, resolution_minutes=1)

    history_by_node: dict[str, list] = {}
    for row in history:
        nid = row["node_id"]
        if nid not in history_by_node:
            history_by_node[nid] = []
        history_by_node[nid].append(row)

    nodes = []
    for n in latest:
        nid = n["node_id"]
        hist = history_by_node.get(nid, [])
        cpu_spark = sparkline([int(r["cpu_pct"] or 0) for r in hist]) if hist else ""
        gpu_spark = sparkline([int(r["gpu_pct"] or 0) for r in hist]) if hist else ""
        nodes.append({**n, "cpu_spark": cpu_spark, "gpu_spark": gpu_spark})

    return templates.TemplateResponse(
        "fragments/node_metrics.html",
        {"request": request, "nodes": nodes},
    )


@router.get("/fragments/node-utilization-chart", response_class=HTMLResponse)
async def fragment_node_utilization_chart(request: Request, conn=Depends(get_db)):
    rows = await get_node_utilization_history(conn)

    history_by_node: dict[str, list] = {}
    for row in rows:
        nid = row["node_id"]
        if nid not in history_by_node:
            history_by_node[nid] = []
        history_by_node[nid].append(row)

    nodes = []
    for node_id, hist in history_by_node.items():
        cpu_series = {
            "label": "CPU",
            "color": "#4fc3f7",
            "data": [{"x": r["bucket"], "y": float(r["cpu_pct"] or 0)} for r in hist],
        }
        gpu_series = {
            "label": "GPU",
            "color": "#66bb6a",
            "data": [{"x": r["bucket"], "y": float(r["gpu_pct"] or 0)} for r in hist],
        }
        chart_svg = render_line_chart(
            series=[cpu_series, gpu_series],
            width=800,
            height=200,
            y_label="%",
            y_min=0,
            y_max=100,
        )
        nodes.append({"node_id": node_id, "chart_svg": chart_svg})

    nodes.sort(key=lambda n: n["node_id"])
    return templates.TemplateResponse(
        "fragments/node_utilization_chart.html",
        {"request": request, "nodes": nodes},
    )


@router.get("/fragments/recent-completed", response_class=HTMLResponse)
async def fragment_recent_completed(request: Request, conn=Depends(get_db)):
    tasks = await get_recent_completed(conn)
    for task in tasks:
        ds = task.get("duration_seconds")
        if ds is not None and ds >= 0:
            task["_duration"] = _format_elapsed(ds)
        else:
            task["_duration"] = "—"
    return templates.TemplateResponse(
        "fragments/recent_completed.html",
        {"request": request, "tasks": tasks},
    )


@router.get("/fragments/recent-failed", response_class=HTMLResponse)
async def fragment_recent_failed(request: Request, conn=Depends(get_db)):
    tasks = await get_recent_failed(conn)
    return templates.TemplateResponse(
        "fragments/recent_failed.html",
        {"request": request, "tasks": tasks},
    )


@router.get("/fragments/blocked-chains", response_class=HTMLResponse)
async def fragment_blocked_chains(request: Request, conn=Depends(get_db)):
    chains = await get_blocked_chains(conn)
    return templates.TemplateResponse(
        "fragments/blocked_chains.html",
        {"request": request, "chains": chains},
    )


@router.get("/fragments/failure-patterns", response_class=HTMLResponse)
async def fragment_failure_patterns(request: Request, days: int = 7, conn=Depends(get_db)):
    patterns = await get_failure_patterns(conn, days=days)
    return templates.TemplateResponse(
        "fragments/failure_patterns.html",
        {"request": request, "patterns": patterns},
    )


@router.get("/fragments/recovery-overview", response_class=HTMLResponse)
async def fragment_recovery_overview(request: Request, days: int = 1, conn=Depends(get_db)):
    data = await get_recovery_overview(conn, days=days)
    return templates.TemplateResponse(
        "fragments/recovery_overview.html",
        {"request": request, "data": data},
    )


@router.get("/fragments/active-investigations", response_class=HTMLResponse)
async def fragment_active_investigations(request: Request, conn=Depends(get_db)):
    investigations = await get_active_investigations(conn)
    for inv in investigations:
        inv["_age"] = _format_elapsed(inv.get("age_seconds"))
    return templates.TemplateResponse(
        "fragments/active_investigations.html",
        {"request": request, "investigations": investigations},
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


@router.get("/fragments/security-overview", response_class=HTMLResponse)
async def fragment_security_overview(request: Request, conn=Depends(get_db)):
    overview = await get_security_overview(conn)
    return templates.TemplateResponse("fragments/security_overview.html", {"request": request, **overview})


@router.get("/fragments/security-alerts", response_class=HTMLResponse)
async def fragment_security_alerts(request: Request, conn=Depends(get_db)):
    alerts = await get_unreviewed_alerts(conn)
    return templates.TemplateResponse(
        "fragments/security_alerts.html",
        {"request": request, "alerts": alerts},
    )


@router.get("/fragments/blocked-ops", response_class=HTMLResponse)
async def fragment_blocked_ops(request: Request, conn=Depends(get_db)):
    ops = await get_blocked_operations(conn)
    return templates.TemplateResponse(
        "fragments/blocked_ops.html",
        {"request": request, "ops": ops},
    )


@router.get('/security/incidents/{invocation_id}', response_class=HTMLResponse)
async def security_incident_detail(request: Request, invocation_id: str, conn=Depends(get_db)):
    incident = await get_security_incident(conn, invocation_id)
    if incident is None:
        return HTMLResponse('Incident not found', status_code=404)
    return templates.TemplateResponse('security_incident.html', {'request': request, **incident})
