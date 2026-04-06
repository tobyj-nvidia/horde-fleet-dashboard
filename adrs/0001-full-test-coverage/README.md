# ADR 0001: Full Test Suite Coverage for horde-fleet-dashboard

**Date:** 2026-04-06
**Status:** Accepted
**Deciders:** Fleet Dashboard Team

---

## Context

The horde-fleet-dashboard has suffered repeated production breakages that were preventable. Each breakage required a dedicated fix commit, caused visible dashboard failures, and eroded confidence in the dashboard as a reliable operational tool.

### Specific incidents that motivated this ADR

| Commit | Bug | Root Cause | Catchable by test? |
|--------|-----|------------|-------------------|
| `9b94019` | `get_recent_completed` and `get_recent_failed` returned wrong columns | SQL used `sha` instead of `commit_sha` | Yes — column name test |
| `17a8e52` | `get_recent_failed` returned no rows | Query filtered on `dead_letter` (underscore) instead of `dead-letter` (hyphen) | Yes — enum value test |
| `49f6ec2` | Fragment route for `recent_failed` crashed with 500 | Route imported from wrong module path (`fragments.py` vs `routes/fragments.py`) | Yes — route smoke test |

All three bugs share a pattern: **the failure mode was a silent mismatch between the code's assumptions and the database's actual schema or data**. None required complex logic to detect — a single query execution against the real database would have caught each one.

The dashboard currently has a partial test suite (91 tests across 4 files, added in `b76a4dc`). This ADR documents what exists, what is missing, and the plan to achieve full coverage.

---

## Decision

Implement a complete four-layer test suite covering every query function, every route, every template, and the integrated app stack. Tests must run against the real Dolt database (no mocks) to catch schema mismatches.

### Rationale for no mocks on the database layer

The three incidents above all involved mismatches between code assumptions and the real database schema. A mocked database would have hidden all three bugs — mocks encode the same assumptions as the code under test, so they cannot catch assumption-vs-reality divergence. Only the real database can do that.

---

## Current State (as of 2026-04-06)

### Source files

| Category | Count | Files |
|----------|-------|-------|
| Core modules | 7 | `__init__.py`, `main.py`, `queries.py`, `db.py`, `config.py`, `charts.py`, `sparkline.py` |
| Route modules | 3 | `routes/__init__.py`, `routes/api.py`, `routes/fragments.py` |
| Static assets | 2 | `static/.gitkeep`, `static/style.css` |
| Templates | 14 | 2 base + 12 fragment (see template list below) |
| **Total** | **26** | |

### Query functions (queries.py) — 16 exported, 3 internal

| # | Function | Description |
|---|----------|-------------|
| 1 | `get_queue_counts(conn)` | COUNT(*) per status |
| 2 | `get_active_tasks(conn)` | Tasks WHERE status IN ('claimed','running') |
| 3 | `get_nodes(conn)` | All nodes + heartbeat_age_sec + is_stale |
| 4 | `get_dead_letter(conn, limit=20)` | Tasks WHERE status='dead-letter' |
| 5 | `get_throughput(conn, window_days=7)` | Daily total/success/failure counts |
| 6 | `get_duration_percentiles(conn, window_days=7)` | p50, p95, p99, avg duration_sec |
| 7 | `get_failure_rate(conn, window_days=7)` | Daily total/failures/failure_pct |
| 8 | `get_token_spend(conn, window_days=7)` | Per provider/model token usage |
| 9 | `get_task(conn, task_id)` | Single task + result + telemetry (**KNOWN BUG**: uses `task_id` PK, correct column is `id`) |
| 10 | `get_tasks(conn, status=None, limit=50, offset=0)` | Paginated task list |
| 11 | `get_node_metrics_latest(conn)` | Most recent row per node from node_metrics |
| 12 | `get_node_metrics_history(conn, node_id, window_hours, resolution_minutes)` | Downsampled node metrics |
| 13 | `get_node_utilization_history(conn)` | 5-minute bucketed CPU/GPU per node |
| 14 | `get_recent_completed(conn, limit=10)` | Recent completed tasks with duration + commit hash |
| 15 | `get_recent_failed(conn, limit=10)` | Recent failed/dead-letter tasks |
| 16 | `retry_task(conn, task_id)` | SET status='pending' (**KNOWN BUG**: uses `task_id` PK, correct column is `id`) |
| — | `_parse_window(window)` | Internal helper |
| — | `_parse_metrics_window(window)` | Internal helper |
| — | `_parse_resolution(resolution)` | Internal helper |

### Routes

#### Fragment routes (routes/fragments.py) — 12 endpoints

| Route | Handler | Template |
|-------|---------|----------|
| `GET /fragments/queue-counts` | `fragment_queue_counts` | `fragments/queue_counts.html` |
| `GET /fragments/active-tasks` | `fragment_active_tasks` | `fragments/active_tasks.html` |
| `GET /fragments/nodes` | `fragment_nodes` | `fragments/nodes.html` |
| `GET /fragments/dead-letter` | `fragment_dead_letter` | `fragments/dead_letter.html` |
| `GET /fragments/throughput` | `fragment_throughput` | `fragments/throughput.html` |
| `GET /fragments/tokens` | `fragment_tokens` | `fragments/tokens.html` |
| `GET /fragments/failures` | `fragment_failures` | `fragments/failures.html` |
| `GET /fragments/node-metrics` | `fragment_node_metrics` | `fragments/node_metrics.html` |
| `GET /fragments/node-utilization-chart` | `fragment_node_utilization_chart` | `fragments/node_utilization_chart.html` |
| `GET /fragments/recent-completed` | `fragment_recent_completed` | `fragments/recent_completed.html` |
| `GET /fragments/recent-failed` | `fragment_recent_failed` | `fragments/recent_failed.html` |
| `GET /fragments/duration` | `fragment_duration` | `fragments/duration.html` |

#### API routes (routes/api.py) — 11 endpoints

| Route | Handler |
|-------|---------|
| `GET /api/tasks` | `list_tasks` |
| `GET /api/tasks/{task_id}` | `get_task_detail` |
| `GET /api/nodes` | `nodes` |
| `GET /api/metrics/summary` | `metrics_summary` |
| `GET /api/metrics/throughput` | `metrics_throughput` |
| `GET /api/metrics/tokens` | `metrics_tokens` |
| `GET /api/metrics/failures` | `metrics_failures` |
| `GET /api/metrics/duration` | `metrics_duration` |
| `GET /api/metrics/nodes/latest` | `node_metrics_latest` |
| `GET /api/metrics/nodes/history` | `node_metrics_history` |
| `POST /api/tasks/{task_id}/retry` | `retry_task_endpoint` |

#### Other routes

| Route | Notes |
|-------|-------|
| `GET /` | Index page |
| `GET /healthz` | Health check |

### Templates

| Template | Type | Covered by test_templates.py |
|----------|------|------------------------------|
| `base.html` | Layout | No |
| `index.html` | Page | No |
| `fragments/active_tasks.html` | Fragment | Yes |
| `fragments/dead_letter.html` | Fragment | Yes |
| `fragments/duration.html` | Fragment | Yes |
| `fragments/failures.html` | Fragment | Yes |
| `fragments/node_metrics.html` | Fragment | Yes |
| `fragments/node_utilization_chart.html` | Fragment | Yes |
| `fragments/nodes.html` | Fragment | Yes |
| `fragments/queue_counts.html` | Fragment | Yes |
| `fragments/recent_completed.html` | Fragment | Yes |
| `fragments/recent_failed.html` | Fragment | Yes |
| `fragments/throughput.html` | Fragment | Yes |
| `fragments/tokens.html` | Fragment | Yes |

### Existing tests (as of commit b76a4dc)

| File | Tests | Lines |
|------|-------|-------|
| `tests/conftest.py` | fixtures only | — |
| `tests/test_queries.py` | 32 | 394 |
| `tests/test_routes.py` | 15 | 136 |
| `tests/test_templates.py` | 24 | 305 |
| `tests/test_schema.py` | 20 | 430 |
| **Total** | **91** | **1,265** |

### Known bugs documented in test_schema.py (not yet fixed)

| Bug | Function | Description |
|-----|----------|-------------|
| #1 | `get_task()` | Filters on `task_id` column; actual PK column is `id` |
| #2 | `retry_task()` | Same wrong PK column `task_id` vs `id` |
| #3 | `get_recent_failed()` | Status filter was `dead_letter` (underscore); fixed in `17a8e52` |
| #4 | `recent_failed.html` | Template used `error_message`; correct column is `error_msg` |

---

## Test Architecture

### Layer 1: Query Tests (`test_queries.py`)

**Goal:** Every exported query function executes against the real database and returns columns that templates expect.

**Pattern per function:**

```python
async def test_<name>_no_error(db_conn):
    result = await <name>(db_conn)
    # no exception == pass

async def test_<name>_columns(db_conn):
    result = await <name>(db_conn)
    if result:
        row = result[0] if isinstance(result, list) else result
        assert "expected_column" in row

async def test_<name>_empty_result(db_conn):
    # test with params that return zero rows
    result = await <name>(db_conn, limit=0)
    assert isinstance(result, list)
```

**Full coverage target per function:**

| Function | Tests needed | Tests exist | Gap |
|----------|-------------|-------------|-----|
| `get_queue_counts` | no-error, int-values | 2 | None |
| `get_active_tasks` | no-error, columns | 2 | None |
| `get_nodes` | no-error, columns, is_stale bool | 3 | None |
| `get_dead_letter` | no-error, columns, status='dead-letter' | 3 | None |
| `get_throughput` | no-error, columns | 2 | None |
| `get_duration_percentiles` | no-error, keys | 2 | None |
| `get_failure_rate` | no-error, columns | 2 | None |
| `get_token_spend` | no-error, columns | 2 | None |
| `get_task` | no-error, columns, 404 case | 0 | **3 tests needed** (fix bug #1 first) |
| `get_tasks` | no-error, status filter | 2 | None |
| `get_node_metrics_latest` | no-error, columns | 2 | None |
| `get_node_metrics_history` | no-error, with/without node_id | 2 | None |
| `get_node_utilization_history` | no-error, columns | 2 | None |
| `get_recent_completed` | no-error, columns, status='completed' | 3 | None |
| `get_recent_failed` | no-error, status values | 2 | None |
| `retry_task` | no-error, state change | 0 | **2 tests needed** (fix bug #2 first) |

**New tests to add:** 5 tests covering `get_task` and `retry_task` (blocked on bug fixes #1 and #2).

### Layer 2: Route Tests (`test_routes.py`)

**Goal:** Every HTTP endpoint returns 200 and valid HTML. No Python tracebacks in responses.

**Pattern per route:**

```python
async def test_<route>_200(client):
    r = await client.get("/fragments/<name>")
    assert r.status_code == 200

async def test_<route>_contains_expected_html(client):
    r = await client.get("/fragments/<name>")
    assert "<expected_marker>" in r.text

async def test_<route>_no_traceback(client):
    r = await client.get("/fragments/<name>")
    assert "Traceback" not in r.text
    assert "Internal Server Error" not in r.text
```

**Full coverage target:**

| Route | Tests exist | Gap |
|-------|-------------|-----|
| `GET /fragments/queue-counts` | 1 (200 only) | content + no-traceback tests |
| `GET /fragments/active-tasks` | 1 | content + no-traceback tests |
| `GET /fragments/nodes` | 1 | content + no-traceback tests |
| `GET /fragments/dead-letter` | 1 | content + no-traceback tests |
| `GET /fragments/throughput` | 1 | content + no-traceback tests |
| `GET /fragments/tokens` | 1 | content + no-traceback tests |
| `GET /fragments/failures` | 1 | content + no-traceback tests |
| `GET /fragments/node-metrics` | 1 | content + no-traceback tests |
| `GET /fragments/node-utilization-chart` | 1 | content + no-traceback tests |
| `GET /fragments/recent-completed` | 1 | content + no-traceback tests |
| `GET /fragments/recent-failed` | 1 | content + no-traceback tests |
| `GET /fragments/duration` | 1 | content + no-traceback tests |
| `GET /api/tasks` | **0** | **3 tests needed** |
| `GET /api/tasks/{task_id}` | **0** | **3 tests needed** (after bug #1 fix) |
| `GET /api/nodes` | **0** | **3 tests needed** |
| `GET /api/metrics/summary` | **0** | **3 tests needed** |
| `GET /api/metrics/throughput` | **0** | **3 tests needed** |
| `GET /api/metrics/tokens` | **0** | **3 tests needed** |
| `GET /api/metrics/failures` | **0** | **3 tests needed** |
| `GET /api/metrics/duration` | **0** | **3 tests needed** |
| `GET /api/metrics/nodes/latest` | **0** | **3 tests needed** |
| `GET /api/metrics/nodes/history` | **0** | **3 tests needed** |
| `POST /api/tasks/{task_id}/retry` | **0** | **2 tests needed** (after bug #2 fix) |
| `GET /` | 1 | None |
| `GET /healthz` | 1 | None |
| 404 case | 1 | None |

**New tests to add:** ~32 tests covering all API routes.

### Layer 3: Template Tests (`test_templates.py`)

**Goal:** Every template renders without `UndefinedError` with both populated and empty data.

**Pattern per template:**

```python
def test_<template>_renders_with_data(env, sample_<data>):
    tmpl = env.get_template("fragments/<name>.html")
    html = tmpl.render(<var>=sample_<data>)
    assert html  # not empty

def test_<template>_renders_empty(env):
    tmpl = env.get_template("fragments/<name>.html")
    html = tmpl.render(<var>=[])
    assert html  # no UndefinedError raised
```

**Full coverage target:**

| Template | Tests exist | Gap |
|----------|-------------|-----|
| `fragments/queue_counts.html` | 2 | None |
| `fragments/active_tasks.html` | 3 | None |
| `fragments/nodes.html` | 3 | None |
| `fragments/dead_letter.html` | 2 | None |
| `fragments/recent_completed.html` | 3 | None |
| `fragments/recent_failed.html` | 3 | None |
| `fragments/throughput.html` | 1 | empty-state test |
| `fragments/failures.html` | 1 | empty-state test |
| `fragments/tokens.html` | 1 | empty-state test |
| `fragments/duration.html` | 2 | None |
| `fragments/node_metrics.html` | 1 | empty-state test |
| `fragments/node_utilization_chart.html` | 2 | None |
| `base.html` | **0** | **renders test** |
| `index.html` | **0** | **renders test** |

**New tests to add:** ~6 tests covering base/index templates and empty-state gaps.

### Layer 4: Integration Tests (`test_integration.py`) — NEW FILE

**Goal:** Start the actual app, hit every widget endpoint via simulated HTMX requests, verify no stuck loading states.

```python
# tests/test_integration.py

HTMX_HEADERS = {
    "HX-Request": "true",
    "HX-Target": "widget",
}

FRAGMENT_ROUTES = [
    "/fragments/queue-counts",
    "/fragments/active-tasks",
    "/fragments/nodes",
    "/fragments/dead-letter",
    "/fragments/throughput",
    "/fragments/tokens",
    "/fragments/failures",
    "/fragments/node-metrics",
    "/fragments/node-utilization-chart",
    "/fragments/recent-completed",
    "/fragments/recent-failed",
    "/fragments/duration",
]

@pytest.mark.asyncio
@pytest.mark.parametrize("path", FRAGMENT_ROUTES)
async def test_all_fragments_return_200(client, path):
    r = await client.get(path, headers=HTMX_HEADERS)
    assert r.status_code == 200, f"{path} returned {r.status_code}"

@pytest.mark.asyncio
@pytest.mark.parametrize("path", FRAGMENT_ROUTES)
async def test_no_fragment_contains_loading_stuck(client, path):
    r = await client.get(path, headers=HTMX_HEADERS)
    # HTMX loading spinners should not appear in rendered fragment responses
    assert "Loading..." not in r.text, f"{path} response contains stuck 'Loading...'"

@pytest.mark.asyncio
@pytest.mark.parametrize("path", FRAGMENT_ROUTES)
async def test_no_fragment_contains_traceback(client, path):
    r = await client.get(path, headers=HTMX_HEADERS)
    assert "Traceback" not in r.text, f"{path} contains Python traceback"
    assert "Internal Server Error" not in r.text

@pytest.mark.asyncio
async def test_index_loads_all_htmx_targets(client):
    r = await client.get("/")
    assert r.status_code == 200
    # Verify each HTMX hx-get target is present in the page
    for path in FRAGMENT_ROUTES:
        assert path in r.text, f"Index page missing hx-get for {path}"
```

**Tests to add:** ~40 integration tests (parametrized across 12 fragment routes × 3 assertions + index test).

---

## Implementation Plan

### Phase 1: Fix known bugs (prerequisite for full query/route coverage)

Before writing tests for `get_task`, `retry_task`, and `GET /api/tasks/{task_id}`, the underlying bugs must be fixed:

- **Bug #1 & #2:** Rename `task_id` → `id` in `get_task()` and `retry_task()` WHERE clauses
- These bugs are already documented with expected-failure (`xfail`) markers in `test_schema.py`; once fixed, flip to passing tests

### Phase 2: Query tests for remaining functions

Add tests for:
- `get_task(conn, task_id)` — 3 tests
- `retry_task(conn, task_id)` — 2 tests

**Value:** Highest — catches column/enum bugs before any route or template is involved.

### Phase 3: API route tests

Add `test_routes.py` coverage for all 11 API endpoints:
- `GET /api/tasks` — list pagination
- `GET /api/tasks/{task_id}` — detail + 404
- `GET /api/nodes` — node list
- All 6 metrics endpoints
- `POST /api/tasks/{task_id}/retry` — state change verification

**Value:** High — catches route registration bugs (like the `fragments.py` import incident).

### Phase 4: Template gap tests

Add tests for:
- `base.html` renders (with minimal context)
- `index.html` renders (with minimal context)
- Empty-state tests for `throughput.html`, `failures.html`, `tokens.html`, `node_metrics.html`

### Phase 5: Integration tests

Create `tests/test_integration.py` with the parametrized HTMX suite above.

**Value:** End-to-end confidence that all widgets load without errors in a running app.

### Phase 6: CI enforcement

Add to every fleet dashboard task that pushes code:

```bash
cd tests && pytest --tb=short -q
```

This ensures no commit reaches the branch without passing the full suite. The test runner must have access to a Dolt database (connection string via `DB_URL` env var).

---

## Appendix: Full Test Coverage Matrix

### Queries

| Function | no-error | columns | status-enum | empty-result | exists? |
|----------|----------|---------|-------------|--------------|---------|
| `get_queue_counts` | ✅ | ✅ | — | — | ✅ |
| `get_active_tasks` | ✅ | ✅ | — | — | ✅ |
| `get_nodes` | ✅ | ✅ | — | — | ✅ |
| `get_dead_letter` | ✅ | ✅ | ✅ (`dead-letter`) | — | ✅ |
| `get_throughput` | ✅ | ✅ | — | — | ✅ |
| `get_duration_percentiles` | ✅ | ✅ | — | — | ✅ |
| `get_failure_rate` | ✅ | ✅ | — | — | ✅ |
| `get_token_spend` | ✅ | ✅ | — | — | ✅ |
| `get_task` | ❌ | ❌ | — | ❌ | **missing** |
| `get_tasks` | ✅ | — | ✅ (status filter) | — | ✅ |
| `get_node_metrics_latest` | ✅ | ✅ | — | — | ✅ |
| `get_node_metrics_history` | ✅ | — | — | — | ✅ |
| `get_node_utilization_history` | ✅ | ✅ | — | — | ✅ |
| `get_recent_completed` | ✅ | ✅ | ✅ (`completed`) | — | ✅ |
| `get_recent_failed` | ✅ | — | ✅ (`dead-letter`) | — | ✅ |
| `retry_task` | ❌ | — | — | — | **missing** |

### Fragment Routes

| Route | 200 | content | no-traceback | HTMX |
|-------|-----|---------|--------------|------|
| `/fragments/queue-counts` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/active-tasks` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/nodes` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/dead-letter` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/throughput` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/tokens` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/failures` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/node-metrics` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/node-utilization-chart` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/recent-completed` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/recent-failed` | ✅ | ❌ | ❌ | ❌ |
| `/fragments/duration` | ✅ | ❌ | ❌ | ❌ |

### API Routes

| Route | 200 | schema | error-case | exists? |
|-------|-----|--------|-----------|---------|
| `GET /api/tasks` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/tasks/{task_id}` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/nodes` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/summary` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/throughput` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/tokens` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/failures` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/duration` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/nodes/latest` | ❌ | ❌ | ❌ | **missing** |
| `GET /api/metrics/nodes/history` | ❌ | ❌ | ❌ | **missing** |
| `POST /api/tasks/{task_id}/retry` | ❌ | ❌ | ❌ | **missing** |

### Templates

| Template | renders-with-data | renders-empty | no-undefined-var | exists? |
|----------|-------------------|---------------|-----------------|---------|
| `base.html` | ❌ | — | ❌ | **missing** |
| `index.html` | ❌ | — | ❌ | **missing** |
| `fragments/active_tasks.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/dead_letter.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/duration.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/failures.html` | ✅ | ❌ | ✅ | partial |
| `fragments/node_metrics.html` | ✅ | ❌ | ✅ | partial |
| `fragments/node_utilization_chart.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/nodes.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/queue_counts.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/recent_completed.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/recent_failed.html` | ✅ | ✅ | ✅ | ✅ |
| `fragments/throughput.html` | ✅ | ❌ | ✅ | partial |
| `fragments/tokens.html` | ✅ | ❌ | ✅ | partial |

---

## Success Criteria

| Criterion | Current | Target |
|-----------|---------|--------|
| Query functions with tests | 14/16 (88%) | 16/16 (100%) |
| Fragment routes with ≥1 test | 12/12 (100%) | 12/12 + no-traceback assertions |
| API routes with tests | 0/11 (0%) | 11/11 (100%) |
| Templates with render tests | 12/14 (86%) | 14/14 (100%) |
| Integration tests (HTMX) | 0 | ≥36 (parametrized) |
| Column name bugs in prod | ≥2 incidents | 0 |
| Status enum bugs in prod | ≥1 incident | 0 |
| `pytest` runs in CI | No | Yes — every task |

### Definition of "full coverage" for this codebase

A query function is fully covered when:
1. It executes against the real database without error
2. Returned column names are explicitly asserted
3. Status enum values are asserted where applicable

A route is fully covered when:
1. It returns HTTP 200
2. The response body contains expected HTML markers
3. The response body contains no Python traceback

A template is fully covered when:
1. It renders with typical data without raising `UndefinedError`
2. It renders with empty/zero data without raising `UndefinedError`
