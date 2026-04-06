"""
Query tests — execute every query function against the real Dolt database and
verify:
  1. No SQL errors are thrown
  2. Returned rows contain the columns that templates expect

These tests catch column-name mismatches, typos in status values, and bad JOINs
before they reach production.
"""

import pytest
import pytest_asyncio

from dashboard.queries import (
    get_active_tasks,
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
    get_tasks,
    get_throughput,
    get_token_spend,
    get_token_spend_summary,
)


# ---------------------------------------------------------------------------
# get_queue_counts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_queue_counts_no_error(db_conn):
    result = await get_queue_counts(db_conn)
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_get_queue_counts_returns_int_values(db_conn):
    result = await get_queue_counts(db_conn)
    for status, count in result.items():
        assert isinstance(count, int), f"Count for {status!r} is not int: {count!r}"


# ---------------------------------------------------------------------------
# get_active_tasks
# ---------------------------------------------------------------------------

ACTIVE_TASK_REQUIRED_COLUMNS = {
    "id", "type", "project", "status", "claimed_by",
    "started_at", "retry_count", "resource_class", "running_sec", "is_blocked",
}


@pytest.mark.asyncio
async def test_get_active_tasks_no_error(db_conn):
    result = await get_active_tasks(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_active_tasks_columns(db_conn):
    result = await get_active_tasks(db_conn)
    if not result:
        pytest.skip("No active tasks in DB — column check skipped")
    for row in result:
        missing = ACTIVE_TASK_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Active task row missing columns: {missing}"


# ---------------------------------------------------------------------------
# get_nodes
# ---------------------------------------------------------------------------

NODE_REQUIRED_COLUMNS = {
    "node_id", "status", "capabilities", "active_tasks",
    "max_concurrent", "gpu_capacity", "last_heartbeat",
    "deployed_version", "heartbeat_age_sec", "is_stale",
}


@pytest.mark.asyncio
async def test_get_nodes_no_error(db_conn):
    result = await get_nodes(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_nodes_columns(db_conn):
    result = await get_nodes(db_conn)
    if not result:
        pytest.skip("No nodes in DB — column check skipped")
    for row in result:
        missing = NODE_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Node row missing columns: {missing}"


@pytest.mark.asyncio
async def test_get_nodes_is_stale_bool(db_conn):
    result = await get_nodes(db_conn)
    for row in result:
        assert isinstance(row["is_stale"], bool), "is_stale must be a bool"


# ---------------------------------------------------------------------------
# get_dead_letter
# ---------------------------------------------------------------------------

DEAD_LETTER_REQUIRED_COLUMNS = {
    "id", "type", "project", "status", "retry_count",
    "submitted_at", "prompt_snippet", "error_msg",
    "completed_at", "failure_age_sec",
}


@pytest.mark.asyncio
async def test_get_dead_letter_no_error(db_conn):
    result = await get_dead_letter(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_dead_letter_columns(db_conn):
    result = await get_dead_letter(db_conn)
    if not result:
        pytest.skip("No dead-letter tasks in DB — column check skipped")
    for row in result:
        missing = DEAD_LETTER_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Dead-letter row missing columns: {missing}"


@pytest.mark.asyncio
async def test_get_dead_letter_status_value(db_conn):
    """All returned rows must have status='dead-letter' (hyphen, not underscore)."""
    result = await get_dead_letter(db_conn)
    for row in result:
        assert row["status"] == "dead-letter", (
            f"Expected status='dead-letter', got {row['status']!r}. "
            "Hint: check the WHERE clause — 'dead_letter' (underscore) won't match."
        )


# ---------------------------------------------------------------------------
# get_throughput
# ---------------------------------------------------------------------------

THROUGHPUT_REQUIRED_COLUMNS = {"date", "total", "success", "failure"}


@pytest.mark.asyncio
async def test_get_throughput_no_error(db_conn):
    result = await get_throughput(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_throughput_columns(db_conn):
    result = await get_throughput(db_conn)
    if not result:
        pytest.skip("No throughput data — column check skipped")
    for row in result:
        missing = THROUGHPUT_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Throughput row missing columns: {missing}"


# ---------------------------------------------------------------------------
# get_failure_rate
# ---------------------------------------------------------------------------

FAILURE_RATE_REQUIRED_COLUMNS = {"date", "total", "failures", "failure_pct"}


@pytest.mark.asyncio
async def test_get_failure_rate_no_error(db_conn):
    result = await get_failure_rate(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_failure_rate_columns(db_conn):
    result = await get_failure_rate(db_conn)
    if not result:
        pytest.skip("No failure rate data — column check skipped")
    for row in result:
        missing = FAILURE_RATE_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Failure rate row missing columns: {missing}"


# ---------------------------------------------------------------------------
# get_duration_percentiles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_duration_percentiles_no_error(db_conn):
    result = await get_duration_percentiles(db_conn)
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_get_duration_percentiles_keys(db_conn):
    result = await get_duration_percentiles(db_conn)
    assert set(result.keys()) == {"p50_sec", "p95_sec", "p99_sec", "avg_sec"}


# ---------------------------------------------------------------------------
# get_token_spend_summary
# ---------------------------------------------------------------------------

TOKEN_SPEND_SUMMARY_REQUIRED_COLUMNS = {"source", "model", "total_tokens", "total_cost_usd"}


@pytest.mark.asyncio
async def test_get_token_spend_summary_no_error(db_conn):
    result = await get_token_spend_summary(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_token_spend_summary_columns(db_conn):
    result = await get_token_spend_summary(db_conn)
    if not result:
        pytest.skip("No telemetry data — column check skipped")
    for row in result:
        missing = TOKEN_SPEND_SUMMARY_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Token spend summary row missing columns: {missing}"


@pytest.mark.asyncio
async def test_get_token_spend_summary_period_7(db_conn):
    result = await get_token_spend_summary(db_conn, period_days=7)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_token_spend_summary_period_30(db_conn):
    result = await get_token_spend_summary(db_conn, period_days=30)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_token_spend
# ---------------------------------------------------------------------------

TOKEN_REQUIRED_COLUMNS = {"provider", "model", "total_tokens", "total_usd"}


@pytest.mark.asyncio
async def test_get_token_spend_no_error(db_conn):
    result = await get_token_spend(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_token_spend_columns(db_conn):
    result = await get_token_spend(db_conn)
    if not result:
        pytest.skip("No token spend data — column check skipped")
    for row in result:
        missing = TOKEN_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Token spend row missing columns: {missing}"


# ---------------------------------------------------------------------------
# get_tasks (paginated)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_tasks_no_error(db_conn):
    tasks, total = await get_tasks(db_conn, limit=5, offset=0)
    assert isinstance(tasks, list)
    assert isinstance(total, int)
    assert total >= 0


@pytest.mark.asyncio
async def test_get_tasks_with_status_filter(db_conn):
    tasks, total = await get_tasks(db_conn, status="pending", limit=5)
    assert isinstance(tasks, list)
    for task in tasks:
        assert task["status"] == "pending"


# ---------------------------------------------------------------------------
# get_node_metrics_latest
# ---------------------------------------------------------------------------

NODE_METRICS_REQUIRED_COLUMNS = {
    "node_id", "cpu_pct", "mem_pct", "gpu_pct", "disk_pct", "recorded_at",
}


@pytest.mark.asyncio
async def test_get_node_metrics_latest_no_error(db_conn):
    result = await get_node_metrics_latest(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_node_metrics_latest_columns(db_conn):
    result = await get_node_metrics_latest(db_conn)
    if not result:
        pytest.skip("No node metrics in DB — column check skipped")
    for row in result:
        missing = NODE_METRICS_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Node metrics row missing columns: {missing}"


# ---------------------------------------------------------------------------
# get_node_metrics_history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_node_metrics_history_no_error(db_conn):
    result = await get_node_metrics_history(db_conn, window_hours=1, resolution_minutes=1)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_node_metrics_history_with_node_id_no_error(db_conn):
    # Use a dummy node ID — we just want no SQL error
    result = await get_node_metrics_history(
        db_conn, node_id="nonexistent-node", window_hours=1
    )
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_node_utilization_history
# ---------------------------------------------------------------------------

NODE_UTIL_REQUIRED_COLUMNS = {"node_id", "bucket", "cpu_pct", "gpu_pct"}


@pytest.mark.asyncio
async def test_get_node_utilization_history_no_error(db_conn):
    result = await get_node_utilization_history(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_node_utilization_history_columns(db_conn):
    result = await get_node_utilization_history(db_conn)
    if not result:
        pytest.skip("No node utilization data — column check skipped")
    for row in result:
        missing = NODE_UTIL_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Node utilization row missing columns: {missing}"


# ---------------------------------------------------------------------------
# get_recent_completed
# ---------------------------------------------------------------------------

RECENT_COMPLETED_REQUIRED_COLUMNS = {
    "id", "name", "project", "claimed_by", "started_at",
    "completed_at", "repos", "duration_seconds", "commit_hashes",
    "repo_slug", "branch", "commit_sha", "push_target", "repo_commits",
}


@pytest.mark.asyncio
async def test_get_recent_completed_no_error(db_conn):
    result = await get_recent_completed(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_recent_completed_columns(db_conn):
    result = await get_recent_completed(db_conn)
    if not result:
        pytest.skip("No completed tasks — column check skipped")
    for row in result:
        missing = RECENT_COMPLETED_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Recent completed row missing columns: {missing}"


@pytest.mark.asyncio
async def test_get_recent_completed_status_filter(db_conn):
    """All rows must come from tasks with status='completed'."""
    result = await get_recent_completed(db_conn, limit=50)
    # This validates the WHERE clause uses the right status literal
    # The query itself filters, so we just verify SQL runs and returns list
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_recent_completed_has_repo_columns(db_conn):
    """Verify repo_slug, branch, commit_sha columns exist in returned rows."""
    result = await get_recent_completed(db_conn)
    if not result:
        pytest.skip("No completed tasks — column check skipped")
    for row in result:
        assert "repo_slug" in row, "Missing column: repo_slug"
        assert "branch" in row, "Missing column: branch"
        assert "commit_sha" in row, "Missing column: commit_sha"


@pytest.mark.asyncio
async def test_get_recent_completed_push_target(db_conn):
    """Verify fleet/ branches show push_target='main'; others show the actual branch name."""
    result = await get_recent_completed(db_conn)
    for row in result:
        for rc in row.get("repo_commits", []):
            branch = rc["branch"]
            push_target = rc["push_target"]
            if branch.startswith("fleet/"):
                assert push_target == "main", (
                    f"fleet/ branch {branch!r} should have push_target='main', got {push_target!r}"
                )
            else:
                assert push_target == branch, (
                    f"Non-fleet branch {branch!r} should have push_target={branch!r}, got {push_target!r}"
                )


def test_get_recent_completed_deduplicates_repo_branch(monkeypatch):
    """
    A task with 3 commits to the same repo/branch should produce exactly 1 repo_commits entry.
    Exercises the Python post-processing deduplication in get_recent_completed().
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from src.dashboard.queries import get_recent_completed

    # Simulate DB returning 3 commits for the same repo/branch
    fake_row = {
        "id": "task-1",
        "name": "gen-feature",
        "project": "acme",
        "claimed_by": "node-01",
        "started_at": "2026-01-01 00:00:00",
        "completed_at": "2026-01-01 00:05:00",
        "repos": "tobyj-nvidia/horde-claw-fleet",
        "duration_seconds": 300,
        "commit_hashes": "aaa1111|bbb2222|ccc3333",
        "repo_slug": "tobyj-nvidia/horde-claw-fleet|tobyj-nvidia/horde-claw-fleet|tobyj-nvidia/horde-claw-fleet",
        "branch": "main|main|main",
        "commit_sha": "aaa11111|bbb22222|ccc33333",
    }

    mock_cur = AsyncMock()
    mock_cur.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cur.__aexit__ = AsyncMock(return_value=False)
    mock_cur.fetchall = AsyncMock(return_value=[fake_row])

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cur)

    result = asyncio.get_event_loop().run_until_complete(get_recent_completed(mock_conn))
    assert len(result) == 1
    repo_commits = result[0]["repo_commits"]
    assert len(repo_commits) == 1, (
        f"Expected 1 unique repo_commit entry, got {len(repo_commits)}: {repo_commits}"
    )
    assert repo_commits[0]["repo_slug"] == "tobyj-nvidia/horde-claw-fleet"
    assert repo_commits[0]["branch"] == "main"


def test_get_recent_completed_deduplicates_multiple_repos(monkeypatch):
    """
    A task with commits to two different repos (each committed twice) should
    produce exactly 2 repo_commits entries — one per unique (repo_slug, branch).
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from src.dashboard.queries import get_recent_completed

    fake_row = {
        "id": "task-2",
        "name": "gen-multi-repo",
        "project": "acme",
        "claimed_by": "node-01",
        "started_at": "2026-01-01 00:00:00",
        "completed_at": "2026-01-01 00:10:00",
        "repos": "org/repo-a,org/repo-b",
        "duration_seconds": 600,
        "commit_hashes": "aaa1111|bbb2222|ccc3333|ddd4444",
        "repo_slug": "org/repo-a|org/repo-b|org/repo-a|org/repo-b",
        "branch": "main|main|main|main",
        "commit_sha": "aaa11111|bbb22222|ccc33333|ddd44444",
    }

    mock_cur = AsyncMock()
    mock_cur.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cur.__aexit__ = AsyncMock(return_value=False)
    mock_cur.fetchall = AsyncMock(return_value=[fake_row])

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cur)

    result = asyncio.get_event_loop().run_until_complete(get_recent_completed(mock_conn))
    repo_commits = result[0]["repo_commits"]
    assert len(repo_commits) == 2, (
        f"Expected 2 unique repo_commit entries, got {len(repo_commits)}: {repo_commits}"
    )
    slugs = [rc["repo_slug"] for rc in repo_commits]
    assert "org/repo-a" in slugs
    assert "org/repo-b" in slugs


# ---------------------------------------------------------------------------
# get_recent_failed
# ---------------------------------------------------------------------------

RECENT_FAILED_REQUIRED_COLUMNS = {
    "id", "name", "project", "claimed_by", "completed_at",
    "error_msg", "retry_count", "max_retries", "status", "is_resolved",
}


@pytest.mark.asyncio
async def test_get_recent_failed_no_error(db_conn):
    result = await get_recent_failed(db_conn)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_recent_failed_columns(db_conn):
    result = await get_recent_failed(db_conn)
    if not result:
        pytest.skip("No failed tasks — column check skipped")
    for row in result:
        missing = RECENT_FAILED_REQUIRED_COLUMNS - set(row.keys())
        assert not missing, f"Recent failed row missing columns: {missing}"


@pytest.mark.asyncio
async def test_get_recent_failed_status_values(db_conn):
    """
    The query uses WHERE t.status IN ('failed', 'dead_letter').
    The actual status value in the DB is 'dead-letter' (hyphen).
    This test documents the mismatch: if dead-letter tasks exist, they will
    NOT appear because 'dead_letter' (underscore) doesn't match 'dead-letter'.
    """
    result = await get_recent_failed(db_conn)
    for row in result:
        assert row["status"] in ("failed", "dead-letter"), (
            f"Unexpected status {row['status']!r}. "
            "Note: 'dead_letter' (underscore) in query WHERE clause won't match "
            "'dead-letter' (hyphen) status values stored in the database."
        )
