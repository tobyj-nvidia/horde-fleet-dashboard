# Coverage Audit: horde-fleet-dashboard

**Date:** 2026-04-07
**Audited by:** automated coverage audit

---

## Current State

### Test Count and Results

| Metric | Count |
|--------|-------|
| **Total tests collected** | 115 |
| **Passed** | 6 |
| **Errors (DB unavailable)** | 109 |
| **Failed** | 0 |

The 6 passing tests are pure-logic / static-analysis tests that don't require a database connection (push_target branch logic, deduplication logic, queries.py source checks). All DB-dependent tests error out when Dolt is unavailable.

### Test Files

| File | Tests | What it covers |
|------|-------|---------------|
| `test_queries.py` | ~45 | All 17 query functions: return types, columns, values, parameters |
| `test_routes.py` | 16 | 13 fragment endpoints + `/healthz` + `/` + 404 |
| `test_templates.py` | ~30 | All 13 fragment templates: rendering, empty states, structure |
| `test_schema.py` | ~24 | Table existence, required columns, known bugs, status values |

### Source Modules

| Module | Lines | Test coverage |
|--------|-------|--------------|
| `queries.py` | 511 | Covered (test_queries.py) |
| `routes/fragments.py` | 247 | Covered (test_routes.py) |
| `routes/api.py` | 222 | **NOT TESTED** |
| `main.py` | 46 | Partial (/ and /healthz only) |
| `sparkline.py` | 21 | **NOT TESTED** |
| `charts.py` | 170 | **NOT TESTED** |
| `db.py` | 54 | **NOT TESTED** (used indirectly via fixtures) |
| `config.py` | 31 | **NOT TESTED** |

---

## Coverage Gaps

### Gap 1: API Routes (HIGH priority)

**File:** `src/dashboard/routes/api.py` (11 endpoints, 0 tests)

No API endpoints have any tests. This is the largest gap.

| Endpoint | Method | Tests needed |
|----------|--------|-------------|
| `/api/tasks` | GET | Happy path; status filter; invalid status (422); limit bounds; offset |
| `/api/tasks/{task_id}` | GET | Happy path; task not found (404) |
| `/api/nodes` | GET | Happy path; returns node list |
| `/api/metrics/summary` | GET | Happy path; response shape (queue_counts, active_tasks, nodes_online) |
| `/api/metrics/throughput` | GET | Default window; explicit 30d/90d; invalid window (422) |
| `/api/metrics/tokens` | GET | Default window; explicit windows; invalid window (422) |
| `/api/metrics/failures` | GET | Default window; explicit windows; invalid window (422) |
| `/api/metrics/duration` | GET | Default window; explicit windows; invalid window (422) |
| `/api/metrics/nodes/latest` | GET | Happy path; response shape |
| `/api/metrics/nodes/history` | GET | Default params; explicit node_id; invalid window/resolution (422) |
| `/api/tasks/{task_id}/retry` | POST | Happy path (dead-letter task); not found (404); wrong status (409) |

**Estimated tests: 30-35**

### Gap 2: Input Validation and Error Paths (HIGH priority)

No tests for HTTP error responses:

- **422 responses:** Invalid `status`, `window`, `resolution` params on API routes
- **404 responses:** `/api/tasks/{task_id}` for non-existent task
- **409 responses:** `/api/tasks/{task_id}/retry` when task is not dead-letter
- **Limit clamping:** `limit > 200` silently capped to 200

**Estimated tests: 10-12**

### Gap 3: Sparkline Module (MEDIUM priority)

**File:** `src/dashboard/sparkline.py` (pure function, no DB needed)

The `sparkline()` function is untested but trivial to test. Cases:

- Empty list returns `""`
- Single value returns one block char
- All same values returns uniform blocks (middle block)
- Increasing values returns ascending blocks
- Negative values handled
- Large values handled

**Estimated tests: 5-6**

### Gap 4: Charts Module (MEDIUM priority)

**File:** `src/dashboard/charts.py` (`render_line_chart()`)

Server-side SVG chart generation is untested. Cases:

- Empty data returns "No data" SVG placeholder
- Single data point renders valid SVG
- Multiple series render correctly (polyline elements)
- y_range = 0 edge case (division guard)
- x_range = 0 edge case (single timestamp)
- Grid lines rendered when `show_grid=True`
- Legend entries match series
- Various tick intervals (< 12h, 12-24h, > 24h)

**Estimated tests: 8-10**

### Gap 5: Fragment Route Logic (MEDIUM priority)

Fragment routes have integration tests (HTTP 200 + content check) but no unit tests for route-level logic:

- `_format_elapsed()` helper (None, negative, 0, positive values)
- `/fragments/token-spend` with `period` query param
- `/fragments/active-tasks` elapsed time decoration
- `/fragments/recent-completed` duration formatting
- `/fragments/node-metrics` sparkline integration per-node
- `/fragments/node-utilization-chart` SVG chart per-node grouping
- `/fragments/duration` `no_data` flag logic

**Estimated tests: 10-12**

### Gap 6: DB Module (LOW priority)

**File:** `src/dashboard/db.py`

- `get_pool()` singleton behavior (creates once, returns cached)
- `close_pool()` cleanup
- `ping_db()` success and failure paths
- `get_db()` generator yields and releases connection

**Note:** These are infrastructure functions tested indirectly. Explicit tests have lower ROI but improve coverage completeness.

**Estimated tests: 4-5**

### Gap 7: Config Module (LOW priority)

**File:** `src/dashboard/config.py`

- Default values when env vars are unset
- Custom values from env vars
- Type coercion (port as int, etc.)

**Estimated tests: 2-3**

### Gap 8: Template Edge Cases (LOW priority)

Existing template tests cover rendering and empty states. Missing:

- Templates with extreme values (very long strings, large numbers)
- `token_spend.html` with None cost/token values
- `node_utilization_chart.html` with single node vs. many nodes
- All status badge variants in `nodes.html` (online, offline, draining)

**Estimated tests: 5-8**

---

## Implementation Plan

### Phase 1: API Route Tests (Priority 1 - Highest value)

**File:** `tests/test_api_routes.py`

These are the most critical gap. All 11 API endpoints are completely untested.

1. **Setup:** Reuse existing `client` fixture from conftest.py (AsyncClient with the app)
2. **Test each endpoint:**
   - Happy path: call with valid params, assert 200, verify JSON response shape
   - Error paths: invalid params -> 422, missing resources -> 404, conflict -> 409
3. **Dolt DB note:** These tests hit the real DB like `test_routes.py`. They'll error without Dolt but catch regressions when Dolt is available.

```
test_api_list_tasks_default
test_api_list_tasks_with_status_filter
test_api_list_tasks_invalid_status_422
test_api_list_tasks_limit_bounds
test_api_get_task_detail
test_api_get_task_detail_not_found_404
test_api_get_nodes
test_api_metrics_summary_shape
test_api_metrics_throughput_default
test_api_metrics_throughput_30d
test_api_metrics_throughput_invalid_window_422
test_api_metrics_tokens_default
test_api_metrics_tokens_invalid_window_422
test_api_metrics_failures_default
test_api_metrics_failures_invalid_window_422
test_api_metrics_duration_default
test_api_metrics_duration_invalid_window_422
test_api_node_metrics_latest
test_api_node_metrics_history_default
test_api_node_metrics_history_with_node_id
test_api_node_metrics_history_invalid_window_422
test_api_node_metrics_history_invalid_resolution_422
test_api_retry_task_not_found_404
test_api_retry_task_wrong_status_409
test_api_retry_task_success (if dead-letter tasks exist)
```

### Phase 2: Pure Function Unit Tests (Priority 2 - Easy wins, no DB needed)

**File:** `tests/test_sparkline.py`

```
test_sparkline_empty
test_sparkline_single_value
test_sparkline_all_same
test_sparkline_ascending
test_sparkline_descending
test_sparkline_length_matches_input
```

**File:** `tests/test_charts.py`

```
test_render_line_chart_empty_data
test_render_line_chart_single_point
test_render_line_chart_multiple_series
test_render_line_chart_no_grid
test_render_line_chart_y_range_zero
test_render_line_chart_x_range_zero
test_render_line_chart_legend
test_render_line_chart_tick_intervals
```

**File:** `tests/test_helpers.py` (or add to existing test_routes.py)

```
test_format_elapsed_none
test_format_elapsed_negative
test_format_elapsed_zero
test_format_elapsed_positive
test_format_elapsed_large_value
```

### Phase 3: Config and DB Tests (Priority 3 - Completeness)

**File:** `tests/test_config.py`

```
test_settings_defaults
test_settings_from_env (monkeypatch env vars)
```

**File:** `tests/test_db.py`

```
test_ping_db_success (requires Dolt)
test_ping_db_failure (mock connection error)
test_get_pool_singleton
test_close_pool
```

### Phase 4: Additional Edge Cases (Priority 4 - Hardening)

Add to existing test files:

- `test_queries.py`: edge cases with extreme params (limit=1, offset=99999, window_days=90)
- `test_templates.py`: extreme data values, all status badge variants
- `test_routes.py`: fragment endpoints with query params (e.g., `/fragments/token-spend?period=7`)

---

## Summary

| Category | Current | To add | Total |
|----------|---------|--------|-------|
| Query tests | ~45 | +5 edge cases | ~50 |
| Fragment route tests | 16 | +7 param/logic | ~23 |
| API route tests | 0 | +25-30 | ~30 |
| Template tests | ~30 | +5 edge cases | ~35 |
| Schema tests | ~24 | 0 | ~24 |
| Sparkline tests | 0 | +6 | ~6 |
| Chart tests | 0 | +8 | ~8 |
| Helper unit tests | 0 | +5 | ~5 |
| Config tests | 0 | +2 | ~2 |
| DB module tests | 0 | +4 | ~4 |
| **Total** | **115** | **+67-72** | **~187** |

### Priority Order

1. **API routes** - 11 untested endpoints, highest risk
2. **Sparkline + charts** - Pure functions, easy to test, no DB dependency
3. **Input validation / error paths** - 422/404/409 responses on API
4. **Fragment route helpers** - `_format_elapsed()` and param handling
5. **Config / DB** - Infrastructure, lowest risk but completes coverage

### Dolt DB Considerations

- Most tests require a live Dolt instance (MySQL-compatible on port 3306)
- Tests use `aiomysql.DictCursor` so column aliases matter (e.g., `dead-letter` with hyphen)
- Dolt may return `Decimal` types for aggregates instead of `float` - test assertions should handle both
- `test_schema.py` already documents known column alias bugs (task_id vs id, dead_letter vs dead-letter)
- Pure function tests (sparkline, charts, helpers, config) can run without any DB
