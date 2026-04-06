# ADR-0001: Test-Driven Dashboard Development

- **Status:** Accepted
- **Date:** 2026-04-06

## Problem

Dashboard changes keep breaking queries (wrong column names, wrong status values). No tests catch these before deploy.

Specific examples of bugs that reached deploy:
- `dead_letter` vs `dead-letter` status value mismatch
- Wrong SQL column references in `get_recent_completed` and `get_recent_failed` queries

## Decision

Adopt test-driven development: every query has a test, every widget has a test, tests run against the real DB schema.

## Implementation Plan

### Phase 1 (DONE): Test suite created
- `tests/test_queries.py` — query correctness tests
- `tests/test_schema.py` — schema validation tests

### Phase 2 (NEXT): Full coverage
- Add tests for every existing query in `queries.py`
- Add template rendering tests for each widget
- Add integration test that loads dashboard and checks all widgets return data

### Phase 3: CI integration
- Test command added to task prompts: `cd tests && pytest`
- Every dashboard task must pass tests before push

### Phase 4: Monitoring
- Health endpoint that validates all queries work
- Alert when a widget returns error

## Success Criteria

- 100% query test coverage
- No more `dead_letter`/`dead-letter` type bugs
- Tests catch column name mismatches before deploy

## Consequences

**Positive:**
- Regressions caught before deploy
- Schema changes surface immediately as test failures
- New contributors get fast feedback on query correctness

**Negative:**
- Tests require a running DB (or fixture) — adds setup overhead
- Test maintenance burden when queries intentionally change
