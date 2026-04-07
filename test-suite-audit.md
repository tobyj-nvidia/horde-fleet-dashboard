# Test Suite Audit — horde-fleet-dashboard

**Date:** 2026-04-07
**Python:** 3.10.12
**pytest:** 8.4.2

---

## Summary

| Result  | Count |
|---------|-------|
| Passed  | 43    |
| Failed  | 1     |
| Errored | 72    |
| Skipped | 0     |
| **Total collected** | **116** |

---

## Test Files

| File | Tests | Passed | Failed | Errored |
|------|-------|--------|--------|---------|
| `tests/test_queries.py` | 35 | 5 | 0 | 30 |
| `tests/test_routes.py` | 21 | 0 | 0 | 21 |
| `tests/test_schema.py` | 17 | 2 | 0 | 15 |
| `tests/test_templates.py` | 43 | 36 | 1 | 0 |

---

## Failing Test

### `tests/test_templates.py::test_throughput_renders`

**Error:** `jinja2.exceptions.UndefinedError: 'dict object' has no attribute 'dead_letter'`

**Root cause:** The `throughput.html` template references `b.dead_letter` in each table row, but the `sample_throughput` fixture in `conftest.py` only provides keys `date`, `total`, `success`, `failure` — no `dead_letter` key.

**Fix:** Add `"dead_letter": 0` (or a non-zero value) to each dict in the `sample_throughput` fixture, e.g.:
```python
{"date": "2026-04-01", "total": 10, "success": 8, "failure": 2, "dead_letter": 0},
```

---

## Errored Tests — External Database Dependency

**72 tests** across `test_queries.py`, `test_routes.py`, and `test_schema.py` error at setup with:

```
pymysql.err.OperationalError: (2003, "Can't connect to MySQL server on '127.0.0.1' ([Errno 111] Connection refused)")
```

These tests require a live **Dolt** (MySQL-compatible) server on `127.0.0.1:3306`. They are integration tests — not unit tests — and cannot run without the database.

**Affected categories:**
- All query tests (`test_queries.py`) except 5 pure-Python logic tests
- All route/HTTP tests (`test_routes.py`) — FastAPI `TestClient` calls real DB via `Depends(get_db)`
- All schema/introspection tests (`test_schema.py`) except 2 pure-Python checks

---

## Tests That Pass Without a Database

These 43 tests run cleanly with no external dependencies:

### `test_queries.py` (5 pure logic tests)
- `test_get_recent_completed_target_branch_explicit`
- `test_get_recent_completed_target_branch_main`
- `test_get_recent_completed_target_branch_null_fleet_fallback`
- `test_get_recent_completed_target_branch_null_non_fleet`
- `test_get_recent_completed_deduplicates_repo_branch`
- `test_get_recent_completed_deduplicates_multiple_repos`

### `test_schema.py` (2 static checks)
- `test_queries_source_readable`
- `test_queries_source_no_dead_underscore`

### `test_templates.py` (36 Jinja2 render tests, all pass except throughput)
Queue counts, active tasks, nodes, dead letter, failures, tokens, token spend, duration, node metrics, node utilization, recent completed, recent failed — all render correctly against in-memory fixture data.

---

## Untested Routes

The following routes have **no passing tests** (all route tests error due to missing DB):

| Route | Handler |
|-------|---------|
| `GET /` | `main.index` |
| `GET /healthz` | `main.healthz` |
| `GET /fragments/queue-counts` | `fragment_queue_counts` |
| `GET /fragments/active-tasks` | `fragment_active_tasks` |
| `GET /fragments/nodes` | `fragment_nodes` |
| `GET /fragments/dead-letter` | `fragment_dead_letter` |
| `GET /fragments/throughput` | `fragment_throughput` |
| `GET /fragments/token-spend` | `fragment_token_spend` |
| `GET /fragments/tokens` | `fragment_tokens` |
| `GET /fragments/failures` | `fragment_failures` |
| `GET /fragments/node-metrics` | `fragment_node_metrics` |
| `GET /fragments/node-utilization-chart` | `fragment_node_utilization_chart` |
| `GET /fragments/recent-completed` | `fragment_recent_completed` |
| `GET /fragments/recent-failed` | `fragment_recent_failed` |
| `GET /fragments/duration` | `fragment_duration` |
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

---

## Coverage Gaps and Recommendations

### 1. Fix the one genuine test failure (immediate)
Add `dead_letter` to `sample_throughput` fixture in `conftest.py`. This is a fixture bug, not a production bug.

### 2. Decouple route tests from live DB
The `TestClient` in `test_routes.py` uses `Depends(get_db)` which connects to a real Dolt server. Override the dependency in tests using FastAPI's `app.dependency_overrides`:
```python
app.dependency_overrides[get_db] = lambda: mock_conn
```
This would make all 21 route tests runnable without a server.

### 3. Add CI database fixture or pytest-docker
For the 30 query tests and 15 schema tests that genuinely need a database, use `pytest-docker` or a GitHub Actions service container to spin up a MySQL-compatible server during CI.

### 4. API routes have zero test coverage
The entire `routes/api.py` module (11 endpoints) has no tests at all — not even template render tests, since it returns JSON, not HTML. Add unit tests with mocked DB connections.

### 5. Known bugs documented in schema tests
`test_schema.py` documents several known bugs via `test_known_bug_*` tests:
- `get_task` and `retry_task` use wrong primary key column
- `get_recent_failed` uses `status = 'error'` instead of `status = 'failed'`
- `recent_failed` template references `error_message` instead of `error_msg`

These pass as "known bug" assertions today (verifying the bug exists); they should be converted to regression tests once the bugs are fixed.
