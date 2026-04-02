# Horde Fleet Dashboard — Implementation Plan

**Status:** Draft
**Date:** 2026-04-02
**Scope:** FastAPI + HTMX observability dashboard for the Dolt-based fleet task scheduler (ADR-0002)
**Repo:** `horde-fleet-dashboard` — standalone dashboard service, deployed on hub node

---

## Prerequisites (Already Complete in horde-claw-fleet)

The following are **done** and are not re-implemented here:

- `task_telemetry` table — schema applied, workers emit one row per LLM API call
- `node_metrics` table — schema applied, heartbeat loop collects CPU/GPU/mem/disk per node
- Worker instrumentation — `execute_task()` callback writes telemetry; heartbeat loop writes metrics
- Dolt `sql-server` running on hub at `127.0.0.1:3306`, database `dolt-tasks`

The dashboard is a **read-only consumer** of these tables. It does not modify the scheduler schema.

---

## Commit Convention

Every task must be committed as at least one commit. The message must reference the task ID:

```
T-003: aiomysql connection pool with lifespan management
```

Multi-commit tasks each reference the task:

```
T-007: task queue counts fragment — SQL query
T-007: task queue counts fragment — HTMX HTML + route
```

Atomic multi-task commits are allowed when tightly coupled:

```
T-004, T-005: /api/tasks list and detail endpoints
```

All tasks are traceable via `git log --grep="T-0"`.

---

## Task Index

| ID | Title | Phase | Effort | Deps |
|----|-------|-------|--------|------|
| T-000 | Implementation plan | 0 | 0.5h | — |
| T-001 | Project scaffold | 1 | 1h | — |
| T-002 | App configuration and settings | 1 | 0.5h | T-001 |
| T-003 | aiomysql connection pool | 2 | 1.5h | T-002 |
| T-004 | SQL queries module | 2 | 2h | T-003 |
| T-005 | GET /api/tasks (list + filter) | 3 | 1.5h | T-004 |
| T-006 | GET /api/tasks/:id (detail) | 3 | 1h | T-004 |
| T-007 | GET /api/nodes | 3 | 1h | T-004 |
| T-008 | GET /api/metrics/summary | 3 | 1h | T-004 |
| T-009 | GET /api/metrics/* (throughput / tokens / failures / duration) | 3 | 2h | T-004 |
| T-010 | POST /api/tasks/:id/retry | 3 | 1h | T-005 |
| T-011 | Base HTML layout and static assets | 4 | 1.5h | T-001 |
| T-012 | Fragment: task queue counts | 4 | 1h | T-004, T-011 |
| T-013 | Fragment: active tasks | 4 | 1h | T-004, T-011 |
| T-014 | Fragment: node health | 4 | 1h | T-004, T-011 |
| T-015 | Fragments: historical panels (throughput / tokens / failures / duration) | 4 | 2h | T-009, T-011 |
| T-016 | Fragment: dead-letter task list | 4 | 1h | T-004, T-011 |
| T-017 | supervisord deployment on localhost:8080 | 5 | 1h | T-001 |
| T-018 | SSH tunnel access documentation | 6 | 0.5h | T-017 |

**Total estimated effort (single agent, sequential):** ~19.5 hours
**With parallelization (phases 3 and 4 tasks independent within phase):** ~6–7 hours

---

## Phase 1: FastAPI Scaffold

### T-001 — Project Scaffold

**Description:** Create the Python package layout for the dashboard service. Use a `src/`
layout with `pyproject.toml`, a minimal `main.py` FastAPI application, and a `requirements.txt`
pinning `fastapi`, `aiomysql`, `uvicorn[standard]`, and `jinja2`. The app should start and
return HTTP 200 on `GET /healthz` before any database is wired up.

**Phase:** 1 — FastAPI Scaffold
**Dependencies:** None
**Deliverables:**
- `pyproject.toml` — package metadata, `[project.scripts]` entry: `dashboard = "dashboard.main:app"`
- `src/dashboard/__init__.py`
- `src/dashboard/main.py` — FastAPI app factory, `GET /healthz`
- `src/dashboard/templates/` — Jinja2 template directory (empty placeholder)
- `src/dashboard/static/` — static assets directory (empty placeholder)
- `requirements.txt` — pinned deps

**Definition of Done:**
- `uvicorn dashboard.main:app --host 127.0.0.1 --port 8080` starts with no errors
- `curl -s http://127.0.0.1:8080/healthz` returns `{"status": "ok"}`
- No database connection required at startup (pool initialized lazily or via lifespan)

**Estimated effort:** 1 hour

---

### T-002 — App Configuration and Settings

**Description:** Add a `config.py` module using `pydantic-settings` (or `os.environ` fallback)
to read Dolt connection parameters. Settings must be overridable via environment variables for
deployment flexibility.

**Phase:** 1 — FastAPI Scaffold
**Dependencies:** T-001
**Deliverables:**
- `src/dashboard/config.py` — `Settings` dataclass/pydantic model

**Settings exposed:**

| Env var | Default | Purpose |
|---------|---------|---------|
| `DOLT_HOST` | `127.0.0.1` | Dolt sql-server host |
| `DOLT_PORT` | `3306` | Dolt sql-server port |
| `DOLT_DB` | `dolt-tasks` | Database name |
| `DOLT_USER` | `root` | MySQL user |
| `DOLT_PASSWORD` | `` | MySQL password (empty default) |
| `DASHBOARD_HOST` | `127.0.0.1` | Bind address |
| `DASHBOARD_PORT` | `8080` | Bind port |
| `POOL_MIN_SIZE` | `2` | aiomysql pool min connections |
| `POOL_MAX_SIZE` | `10` | aiomysql pool max connections |
| `QUERY_TIMEOUT_SEC` | `10` | Per-query timeout |

**Definition of Done:**
- `from dashboard.config import settings` imports cleanly
- Env vars override defaults correctly (verified with a unit test or manual check)

**Estimated effort:** 0.5 hours

---

## Phase 2: Database Layer

### T-003 — aiomysql Connection Pool

**Description:** Create `src/dashboard/db.py` with an async connection pool to Dolt's
`sql-server` at `127.0.0.1:3306`. The pool is initialized during FastAPI's lifespan
startup and closed on shutdown. Expose a `get_db()` dependency for use in route handlers.

**Phase:** 2 — Database Layer
**Dependencies:** T-002
**Deliverables:**
- `src/dashboard/db.py` — pool init/teardown, `get_db()` async dependency
- Pool configured from `settings` (host, port, db, user, password, min/max size)
- Per-query timeout enforced via `asyncio.wait_for` or cursor timeout

**Definition of Done:**
- FastAPI lifespan starts pool; `GET /healthz` confirms DB connectivity (single ping query)
- `GET /healthz` returns `{"status": "ok", "db": "connected"}` when Dolt is reachable
- `GET /healthz` returns `{"status": "ok", "db": "unavailable"}` (not 500) when Dolt is down
- Pool is closed cleanly on SIGTERM/shutdown

**Estimated effort:** 1.5 hours

---

### T-004 — SQL Queries Module

**Description:** Create `src/dashboard/queries.py` with all SQL queries used by the
dashboard, as named async functions. Queries should use parameterized values (no
f-string interpolation into SQL). Group into: current-state queries and historical/trend
queries. All queries include a timeout guard.

**Phase:** 2 — Database Layer
**Dependencies:** T-003
**Deliverables:**
- `src/dashboard/queries.py`

**Query functions:**

| Function | Returns | Notes |
|----------|---------|-------|
| `get_queue_counts(db)` | `dict[str, int]` | COUNT per status |
| `get_active_tasks(db)` | `list[dict]` | claimed/running with running_sec |
| `get_nodes(db)` | `list[dict]` | all nodes with heartbeat_age_sec |
| `get_dead_letter(db, limit)` | `list[dict]` | dead-letter + last error |
| `get_throughput(db, window_days)` | `list[dict]` | daily totals/failures |
| `get_duration_percentiles(db, window_days)` | `dict` | p50, p95, p99, avg |
| `get_failure_rate(db, window_days)` | `list[dict]` | per-node failure_pct |
| `get_token_spend(db, window_days)` | `list[dict]` | per provider/model tokens + USD |
| `get_task(db, task_id)` | `dict \| None` | full task + result + telemetry summary |
| `get_tasks(db, status, limit, offset)` | `tuple[list, int]` | paginated list + total |
| `retry_task(db, task_id)` | `bool` | UPDATE status='pending', clears claim fields |

**Definition of Done:**
- All functions execute against a live Dolt instance without errors
- `retry_task` is the only write operation; all others are `SELECT`
- No raw SQL string interpolation — all user values use `%s` placeholders

**Estimated effort:** 2 hours

---

## Phase 3: JSON API Endpoints

### T-005 — GET /api/tasks

**Description:** Paginated task list endpoint with optional status filter.

**Phase:** 3 — JSON API Endpoints
**Dependencies:** T-004
**Deliverables:**
- Route in `src/dashboard/routes/api.py` (or `main.py` if simple enough)

**Endpoint:**
```
GET /api/tasks
  ?status=pending|claimed|running|completed|failed|dead-letter
  ?limit=50   (max 200)
  ?offset=0
  → { "tasks": [...], "total": N }
```

**Definition of Done:**
- Returns correct tasks for each valid `status` value
- Invalid `status` → HTTP 422
- `limit` capped at 200; `offset` defaults to 0
- Response is valid JSON with `tasks` array and `total` integer

**Estimated effort:** 1.5 hours

---

### T-006 — GET /api/tasks/:id

**Description:** Full task detail including result, telemetry summary, and recent logs.

**Phase:** 3 — JSON API Endpoints
**Dependencies:** T-004
**Deliverables:**
- Route added to `src/dashboard/routes/api.py`

**Endpoint:**
```
GET /api/tasks/{task_id}
  → { task: {...}, result: {...}|null, telemetry: {...}, logs: [...] }
```

**Definition of Done:**
- Returns full task record including `task_results` and `task_telemetry` aggregates
- Unknown `task_id` → HTTP 404 with `{"detail": "not found"}`

**Estimated effort:** 1 hour

---

### T-007 — GET /api/nodes

**Description:** List all nodes with live status and heartbeat staleness.

**Phase:** 3 — JSON API Endpoints
**Dependencies:** T-004
**Deliverables:**
- Route in `src/dashboard/routes/api.py`

**Endpoint:**
```
GET /api/nodes
  → { "nodes": [...] }
```

Each node object includes: `id`, `status`, `capabilities`, `active_tasks`,
`max_concurrent`, `heartbeat_age_sec`.

**Definition of Done:**
- Returns all rows from `nodes` table with computed `heartbeat_age_sec`
- Nodes with `heartbeat_age_sec > 60` are flagged `is_stale: true` in the response

**Estimated effort:** 1 hour

---

### T-008 — GET /api/metrics/summary

**Description:** Single lightweight endpoint returning queue counts, active task count,
and online node count. Used by the dashboard header and `/healthz` consumers.

**Phase:** 3 — JSON API Endpoints
**Dependencies:** T-004
**Deliverables:**
- Route in `src/dashboard/routes/api.py`

**Endpoint:**
```
GET /api/metrics/summary
  → { "queue_counts": {"pending": N, ...}, "active_tasks": N, "nodes_online": N }
```

**Definition of Done:**
- Response includes all task status keys (0 for missing statuses)
- `nodes_online` counts nodes with `status = 'active'`

**Estimated effort:** 1 hour

---

### T-009 — GET /api/metrics/* (Trend Endpoints)

**Description:** Four historical trend endpoints used by the dashboard's charting panels.
All accept a `?window=7d|30d|90d` query parameter (default `7d`).

**Phase:** 3 — JSON API Endpoints
**Dependencies:** T-004
**Deliverables:**
- Routes in `src/dashboard/routes/api.py`

**Endpoints:**
```
GET /api/metrics/throughput?window=7d
  → { "buckets": [ { "date": "2026-03-27", "total": 42, "success": 40, "failure": 2 }, ... ] }

GET /api/metrics/tokens?window=7d
  → { "by_provider_model": [ { "provider", "model", "total_tokens", "total_usd" }, ... ] }

GET /api/metrics/failures?window=7d
  → { "buckets": [ { "date", "total", "failures", "failure_pct" }, ... ] }

GET /api/metrics/duration?window=7d
  → { "p50_sec": N, "p95_sec": N, "p99_sec": N, "avg_sec": N }
```

**Definition of Done:**
- Invalid `window` value → HTTP 422
- Returns empty buckets (not errors) when there is no data in the window
- All `_usd` values are rounded to 4 decimal places in JSON output

**Estimated effort:** 2 hours

---

### T-010 — POST /api/tasks/:id/retry

**Description:** Re-queue a dead-letter task by resetting its status to `pending` and
clearing claim fields. This is the only write path in the dashboard.

**Phase:** 3 — JSON API Endpoints
**Dependencies:** T-005
**Deliverables:**
- Route in `src/dashboard/routes/api.py`

**Endpoint:**
```
POST /api/tasks/{task_id}/retry
  → { "task_id": "...", "status": "pending" }
```

**Behavior:**
- Only allowed if task `status = 'dead-letter'`; other statuses → HTTP 409
- Sets `status = 'pending'`, clears `claimed_by`, `claim_expires_at`, `started_at`
- Does NOT reset `retry_count` (preserves history)

**Definition of Done:**
- Retried task appears in `GET /api/tasks?status=pending` immediately after
- HTTP 404 for unknown task_id; HTTP 409 if task is not in `dead-letter` status
- Idempotent: retrying a task already in `pending` returns HTTP 409, not an error

**Estimated effort:** 1 hour

---

## Phase 4: HTMX Frontend

### T-011 — Base HTML Layout and Static Assets

**Description:** Create the base Jinja2 template (`base.html`) with the full dashboard
shell. Include HTMX from CDN, minimal CSS (grid layout, status colors, monospace tables),
and the main dashboard route (`GET /`) returning the full page.

**Phase:** 4 — HTMX Frontend
**Dependencies:** T-001
**Deliverables:**
- `src/dashboard/templates/base.html` — full HTML shell with HTMX CDN script tag
- `src/dashboard/templates/index.html` — extends base, defines panel grid
- `src/dashboard/static/style.css` — minimal CSS (no framework required)
- `GET /` route in `main.py` returning `TemplateResponse("index.html", ...)`

**Layout:** Two-column grid (active tasks left, node health right), four metric panels
below, dead-letter table at bottom. Matches the ADR-0002 dashboard wireframe.

**Definition of Done:**
- `GET /` returns a valid HTML page with all panel placeholders
- HTMX script loads from CDN (no local copy required)
- Page renders without JavaScript errors in a browser

**Estimated effort:** 1.5 hours

---

### T-012 — Fragment: Task Queue Counts

**Description:** HTMX fragment for the status bar showing pending/claimed/running/
completed/failed/dead-letter counts. Polls every 5 seconds.

**Phase:** 4 — HTMX Frontend
**Dependencies:** T-004, T-011
**Deliverables:**
- `src/dashboard/templates/fragments/queue_counts.html`
- `GET /fragments/queue-counts` route

**Fragment trigger:**
```html
<div hx-get="/fragments/queue-counts" hx-trigger="every 5s" hx-swap="outerHTML">
```

**Definition of Done:**
- Fragment renders six labeled count boxes (one per status)
- Counts update live every 5 seconds with a running Dolt instance
- Zero counts render as `0` (not blank)

**Estimated effort:** 1 hour

---

### T-013 — Fragment: Active Tasks

**Description:** HTMX fragment listing currently claimed/running tasks with task ID,
type, node, elapsed time. Polls every 5 seconds.

**Phase:** 4 — HTMX Frontend
**Dependencies:** T-004, T-011
**Deliverables:**
- `src/dashboard/templates/fragments/active_tasks.html`
- `GET /fragments/active-tasks` route

**Definition of Done:**
- Renders a table/list of active tasks with running time formatted as `Xm Ys`
- Empty state shows "No active tasks" (not a blank area)
- Polls every 5 seconds

**Estimated effort:** 1 hour

---

### T-014 — Fragment: Node Health

**Description:** HTMX fragment showing all nodes with online/offline/draining status,
active task count, and heartbeat staleness indicator. Polls every 10 seconds.

**Phase:** 4 — HTMX Frontend
**Dependencies:** T-004, T-011
**Deliverables:**
- `src/dashboard/templates/fragments/nodes.html`
- `GET /fragments/nodes` route

**Status indicators:** active (●), draining (○), offline/stale (✗)
Stale threshold: `heartbeat_age_sec > 60`

**Definition of Done:**
- All nodes from `nodes` table are shown
- Stale nodes are visually distinguished (different color or symbol)
- Polls every 10 seconds

**Estimated effort:** 1 hour

---

### T-015 — Fragments: Historical Panels

**Description:** Four HTMX fragments for the trend panels: task throughput (7d), token
spend (7d), failure rate (7d), and task duration percentiles (7d). All poll every 60
seconds. Charts rendered as unicode sparklines (no JS charting library).

**Phase:** 4 — HTMX Frontend
**Dependencies:** T-009, T-011
**Deliverables:**
- `src/dashboard/templates/fragments/throughput.html`
- `src/dashboard/templates/fragments/tokens.html`
- `src/dashboard/templates/fragments/failures.html`
- `src/dashboard/templates/fragments/duration.html`
- `src/dashboard/routes/fragments.py` (or inline in main.py) — four `GET /fragments/*` routes
- `src/dashboard/sparkline.py` — helper converting `list[int]` → unicode sparkline string

**Sparkline characters:** `▁▂▃▄▅▆▇█` (8 levels, scaled to data range)

**Definition of Done:**
- Each panel renders data or an "No data for this window" placeholder
- Token spend shows per-provider/model breakdown with USD totals
- Duration panel shows P50, P95 formatted as `Xm Ys`
- All four panels poll every 60 seconds

**Estimated effort:** 2 hours

---

### T-016 — Fragment: Dead-Letter Task List

**Description:** HTMX fragment listing recent dead-letter tasks with ID, type, prompt
snippet, retry count, time since failure, and a retry button. Polls every 30 seconds.

**Phase:** 4 — HTMX Frontend
**Dependencies:** T-004, T-011
**Deliverables:**
- `src/dashboard/templates/fragments/dead_letter.html`
- `GET /fragments/dead-letter` route

**Retry button:** `<button hx-post="/api/tasks/{id}/retry" hx-target="closest tr">`
Clicking re-queues the task and removes it from the dead-letter view.

**Definition of Done:**
- Lists up to 20 most recent dead-letter tasks
- Retry button triggers `POST /api/tasks/:id/retry` and removes the row on success
- Empty state shows "No dead-letter tasks"
- Polls every 30 seconds

**Estimated effort:** 1 hour

---

## Phase 5: Supervisord Deployment

### T-017 — Supervisord Service on localhost:8080

**Description:** Create a supervisord configuration file that runs the dashboard as a
managed service on `127.0.0.1:8080`. The service must auto-restart on crash, log stdout/
stderr to `/tmp/dashboard.log` and `/tmp/dashboard.err`, and be startable via `supervisorctl`.

**Phase:** 5 — Supervisord Deployment
**Dependencies:** T-001
**Deliverables:**
- `deploy/dashboard.conf` — supervisord program config

**Content:**
```ini
[program:fleet-dashboard]
command=uvicorn dashboard.main:app --host 127.0.0.1 --port 8080 --workers 1
directory=/home/horde/horde-fleet-dashboard
environment=PYTHONPATH="%(here)s/src"
autostart=true
autorestart=true
startretries=5
stdout_logfile=/tmp/dashboard.log
stderr_logfile=/tmp/dashboard.err
```

**Install steps** (manual, one-time):
```bash
cp deploy/dashboard.conf ~/.config/supervisor/conf.d/fleet-dashboard.conf
supervisorctl reread && supervisorctl update
supervisorctl status fleet-dashboard
```

**Definition of Done:**
- `supervisorctl status fleet-dashboard` shows `RUNNING` after `supervisorctl update`
- `curl -s http://127.0.0.1:8080/healthz` returns `{"status": "ok"}` from the managed process
- Service restarts automatically after `kill <pid>`
- Dashboard binds only to `127.0.0.1` (not `0.0.0.0`)

**Estimated effort:** 1 hour

---

## Phase 6: SSH Tunnel Documentation

### T-018 — SSH Tunnel Access Documentation

**Description:** Document the SSH port-forwarding workflow that lets operators access
the dashboard from their laptops without K8s port exposure. Cover both one-shot and
persistent tunnel patterns.

**Phase:** 6 — SSH Tunnel Docs
**Dependencies:** T-017
**Deliverables:**
- `docs/SSH_TUNNEL.md`

**Contents:**

#### One-shot tunnel (ad-hoc access)
```bash
ssh -L 8080:127.0.0.1:8080 horde@<hub-ip>
# Then open: http://localhost:8080/
```

#### Persistent background tunnel (operator convenience)
```bash
ssh -fNL 8080:127.0.0.1:8080 horde@<hub-ip>
# Runs in background; kill by: kill $(lsof -ti:8080)
```

#### Using the fleet SSH key (if configured per ADR-0001 T-004/T-005)
```bash
ssh -i ~/.ssh/horde_fleet_key -L 8080:127.0.0.1:8080 horde@<hub-ip>
```

#### SSH config shortcut (~/.ssh/config)
```
Host horde-hub
  HostName <hub-ip>
  User horde
  IdentityFile ~/.ssh/horde_fleet_key
  LocalForward 8080 127.0.0.1:8080
```
Then: `ssh horde-hub` — tunnel is active for the session duration.

**Definition of Done:**
- `docs/SSH_TUNNEL.md` exists and contains all four access patterns
- Each pattern includes the `http://localhost:8080/` URL reminder
- Note included: dashboard is never exposed via K8s NodePort or LoadBalancer

**Estimated effort:** 0.5 hours

---

## Dependency Graph

```
T-001 ──→ T-002 ──→ T-003 ──→ T-004 ──┬──→ T-005 ──→ T-010
                                        ├──→ T-006
                                        ├──→ T-007
                                        ├──→ T-008
                                        └──→ T-009

T-001 ──→ T-011 ──┬──→ T-012  (needs T-004)
                   ├──→ T-013  (needs T-004)
                   ├──→ T-014  (needs T-004)
                   ├──→ T-015  (needs T-009)
                   └──→ T-016  (needs T-004)

T-001 ──→ T-017 ──→ T-018
```

**Critical path:** T-001 → T-002 → T-003 → T-004 → T-009 → T-015

**Parallelizable within phases:**
- Phase 3 (T-005 through T-010): all independent once T-004 is done
- Phase 4 (T-012 through T-016): all independent once T-004 and T-011 are done
- T-011 and T-002 can start in parallel after T-001
- T-017 can start immediately after T-001
