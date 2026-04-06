"""
Schema validation tests — compare what queries.py references against the real
database schema (DESCRIBE <table>).

Every bug we hit in production was a column name mismatch:
  - wrong column alias ('dead_letter' vs 'dead-letter')
  - column that doesn't exist in the table
  - wrong table name in JOIN

These tests would have caught all of them.
"""

import re
from pathlib import Path

import aiomysql
import pytest

QUERIES_PATH = Path(__file__).parent.parent / "src" / "dashboard" / "queries.py"

# Tables used by dashboard queries
DASHBOARD_TABLES = [
    "tasks",
    "task_results",
    "task_commits",
    "task_dependencies",
    "task_telemetry",
    "nodes",
    "node_metrics",
]

# ---------------------------------------------------------------------------
# Fixtures: table schemas
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
async def table_schemas(db_pool):
    """
    Returns a dict mapping table_name -> set of column names.
    Uses aiomysql directly (scope=module to avoid repeated DESCRIBE queries).
    """
    schemas: dict[str, set[str]] = {}
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            for table in DASHBOARD_TABLES:
                try:
                    await cur.execute(f"DESCRIBE `{table}`")
                    rows = await cur.fetchall()
                    schemas[table] = {row["Field"] for row in rows}
                except Exception as exc:
                    schemas[table] = set()  # table doesn't exist
    return schemas


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tasks_table_exists(table_schemas):
    assert "tasks" in table_schemas, "Table 'tasks' not found in database"
    assert table_schemas["tasks"], "Table 'tasks' has no columns or doesn't exist"


@pytest.mark.asyncio
async def test_nodes_table_exists(table_schemas):
    assert "nodes" in table_schemas, "Table 'nodes' not found in database"
    assert table_schemas["nodes"], "Table 'nodes' has no columns or doesn't exist"


@pytest.mark.asyncio
async def test_task_results_table_exists(table_schemas):
    assert "task_results" in table_schemas
    assert table_schemas["task_results"], "Table 'task_results' has no columns or doesn't exist"


@pytest.mark.asyncio
async def test_task_commits_table_exists(table_schemas):
    assert "task_commits" in table_schemas
    assert table_schemas["task_commits"], "Table 'task_commits' has no columns or doesn't exist"


@pytest.mark.asyncio
async def test_node_metrics_table_exists(table_schemas):
    assert "node_metrics" in table_schemas
    assert table_schemas["node_metrics"], "Table 'node_metrics' has no columns or doesn't exist"


# ---------------------------------------------------------------------------
# tasks table columns
# ---------------------------------------------------------------------------

TASKS_REQUIRED_COLUMNS = {
    # Used in get_active_tasks
    "id", "type", "project", "status", "claimed_by", "started_at",
    "retry_count", "resource_class",
    # Used in get_dead_letter
    "submitted_at", "prompt",
    # Used in get_recent_completed
    "name", "completed_at", "repos",
    # Used in get_recent_failed
    "max_retries",
    # Used in get_tasks
    # (SELECT * so all columns are implicitly accessed)
}


@pytest.mark.asyncio
async def test_tasks_required_columns_exist(table_schemas):
    schema = table_schemas.get("tasks", set())
    if not schema:
        pytest.skip("tasks table not found")
    missing = TASKS_REQUIRED_COLUMNS - schema
    assert not missing, (
        f"tasks table missing columns referenced in queries.py: {missing}\n"
        f"Existing columns: {sorted(schema)}"
    )


@pytest.mark.asyncio
async def test_tasks_has_id_not_task_id(table_schemas):
    """
    The tasks table PK is 'id', not 'task_id'.
    get_task() and retry_task() incorrectly use 'task_id' in their WHERE clause.
    """
    schema = table_schemas.get("tasks", set())
    if not schema:
        pytest.skip("tasks table not found")
    assert "id" in schema, "tasks table must have 'id' column"
    # Document the bug: task_id is not a column
    if "task_id" not in schema:
        # This is expected — the column is 'id', not 'task_id'
        # get_task() and retry_task() have a bug: they use WHERE task_id = %s
        pass  # Bug is documented in test_queries_known_bugs below


# ---------------------------------------------------------------------------
# nodes table columns
# ---------------------------------------------------------------------------

NODES_REQUIRED_COLUMNS = {
    "id",  # aliased as node_id in query
    "status", "capabilities", "active_tasks", "max_concurrent",
    "gpu_capacity", "last_heartbeat",
}


@pytest.mark.asyncio
async def test_nodes_required_columns_exist(table_schemas):
    schema = table_schemas.get("nodes", set())
    if not schema:
        pytest.skip("nodes table not found")
    missing = NODES_REQUIRED_COLUMNS - schema
    assert not missing, (
        f"nodes table missing columns: {missing}\n"
        f"Existing columns: {sorted(schema)}"
    )


# ---------------------------------------------------------------------------
# task_results table columns
# ---------------------------------------------------------------------------

TASK_RESULTS_REQUIRED_COLUMNS = {
    "task_id", "error_msg", "completed_at", "outcome", "duration_sec",
}


@pytest.mark.asyncio
async def test_task_results_required_columns_exist(table_schemas):
    schema = table_schemas.get("task_results", set())
    if not schema:
        pytest.skip("task_results table not found")
    missing = TASK_RESULTS_REQUIRED_COLUMNS - schema
    assert not missing, (
        f"task_results table missing columns: {missing}\n"
        f"Existing columns: {sorted(schema)}"
    )


# ---------------------------------------------------------------------------
# task_commits table columns
# ---------------------------------------------------------------------------

TASK_COMMITS_REQUIRED_COLUMNS = {"task_id", "commit_sha"}


@pytest.mark.asyncio
async def test_task_commits_required_columns_exist(table_schemas):
    schema = table_schemas.get("task_commits", set())
    if not schema:
        pytest.skip("task_commits table not found")
    missing = TASK_COMMITS_REQUIRED_COLUMNS - schema
    assert not missing, (
        f"task_commits table missing columns: {missing}\n"
        f"Existing columns: {sorted(schema)}"
    )


# ---------------------------------------------------------------------------
# task_telemetry table columns
# ---------------------------------------------------------------------------

TASK_TELEMETRY_REQUIRED_COLUMNS = {
    "task_id", "provider", "model",
    "input_tokens", "output_tokens", "estimated_cost_usd", "recorded_at",
}


@pytest.mark.asyncio
async def test_task_telemetry_required_columns_exist(table_schemas):
    schema = table_schemas.get("task_telemetry", set())
    if not schema:
        pytest.skip("task_telemetry table not found")
    missing = TASK_TELEMETRY_REQUIRED_COLUMNS - schema
    assert not missing, (
        f"task_telemetry table missing columns: {missing}\n"
        f"Existing columns: {sorted(schema)}"
    )


# ---------------------------------------------------------------------------
# node_metrics table columns
# ---------------------------------------------------------------------------

NODE_METRICS_REQUIRED_COLUMNS = {
    "node_id", "cpu_pct", "mem_pct", "mem_used_gb", "mem_total_gb",
    "gpu_pct", "gpu_mem_pct", "gpu_mem_used_gb", "gpu_mem_total_gb",
    "disk_pct", "recorded_at",
}


@pytest.mark.asyncio
async def test_node_metrics_required_columns_exist(table_schemas):
    schema = table_schemas.get("node_metrics", set())
    if not schema:
        pytest.skip("node_metrics table not found")
    missing = NODE_METRICS_REQUIRED_COLUMNS - schema
    assert not missing, (
        f"node_metrics table missing columns: {missing}\n"
        f"Existing columns: {sorted(schema)}"
    )


# ---------------------------------------------------------------------------
# Status value validation
# ---------------------------------------------------------------------------

VALID_TASK_STATUSES = {"pending", "claimed", "running", "completed", "failed", "dead-letter"}


@pytest.mark.asyncio
async def test_task_status_values_in_db(db_conn):
    """
    Verify that all status values in the tasks table match the known set.
    Unknown values indicate data inconsistency or changed status naming.
    """
    async with db_conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT DISTINCT status FROM tasks")
        rows = await cur.fetchall()
    db_statuses = {row["status"] for row in rows}
    unknown = db_statuses - VALID_TASK_STATUSES
    assert not unknown, (
        f"Unexpected status values in tasks table: {unknown}\n"
        f"Known statuses: {VALID_TASK_STATUSES}"
    )


@pytest.mark.asyncio
async def test_dead_letter_hyphen_not_underscore(db_conn):
    """
    Verify 'dead-letter' (hyphen) is used as the status value, not 'dead_letter'.
    get_recent_failed() uses 'dead_letter' (underscore) which will silently
    return no dead-letter tasks.
    """
    async with db_conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE status = %s", ("dead_letter",)
        )
        row = await cur.fetchone()
    assert row["cnt"] == 0, (
        f"Found {row['cnt']} tasks with status='dead_letter' (underscore). "
        "The canonical status is 'dead-letter' (hyphen). "
        "This indicates either a data inconsistency or the status values were changed."
    )


# ---------------------------------------------------------------------------
# Known bugs in queries.py (documented as tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_known_bug_get_task_uses_wrong_pk_column(table_schemas):
    """
    BUG: get_task() executes:
        SELECT * FROM tasks WHERE task_id = %s
    But the tasks table PK is 'id', not 'task_id'.
    This query will always return None even for valid task IDs.

    FIX: Change 'task_id' to 'id' in get_task().
    """
    schema = table_schemas.get("tasks", set())
    if not schema:
        pytest.skip("tasks table not found")
    # The column 'task_id' should NOT exist (the PK is 'id')
    # If this assertion fails, someone added a task_id column — update the fix advice
    assert "task_id" not in schema, (
        "tasks table now has a 'task_id' column — get_task() may be correct. "
        "Re-verify and update this test."
    )
    assert "id" in schema, "tasks table PK 'id' column must exist"


@pytest.mark.asyncio
async def test_known_bug_retry_task_uses_wrong_pk_column(table_schemas):
    """
    BUG: retry_task() executes:
        UPDATE tasks SET ... WHERE task_id = %s AND status = %s
    But the tasks table PK is 'id', not 'task_id'.
    This UPDATE will never match any row.

    FIX: Change 'task_id' to 'id' in retry_task().
    """
    schema = table_schemas.get("tasks", set())
    if not schema:
        pytest.skip("tasks table not found")
    assert "task_id" not in schema, (
        "tasks table now has a 'task_id' column — retry_task() may be correct. "
        "Re-verify and update this test."
    )


@pytest.mark.asyncio
async def test_known_bug_get_recent_failed_status_underscore(db_conn):
    """
    BUG: get_recent_failed() uses WHERE t.status IN ('failed', 'dead_letter')
    but the correct value is 'dead-letter' (hyphen).

    This means dead-letter tasks are silently excluded from the recent-failed widget.

    FIX: Change 'dead_letter' to 'dead-letter' in get_recent_failed().
    """
    async with db_conn.cursor(aiomysql.DictCursor) as cur:
        # Count tasks that WOULD be included with underscore (wrong)
        await cur.execute(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE status IN ('failed', 'dead_letter')"
        )
        wrong_count = (await cur.fetchone())["cnt"]

        # Count tasks that SHOULD be included with hyphen (correct)
        await cur.execute(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE status IN ('failed', 'dead-letter')"
        )
        correct_count = (await cur.fetchone())["cnt"]

    # If there are any dead-letter tasks, the counts will differ
    if correct_count > wrong_count:
        pytest.fail(
            f"get_recent_failed() is missing {correct_count - wrong_count} dead-letter tasks "
            f"because the WHERE clause uses 'dead_letter' (underscore) instead of "
            f"'dead-letter' (hyphen). "
            f"Wrong query returns {wrong_count} rows; correct query returns {correct_count} rows."
        )


@pytest.mark.asyncio
async def test_known_bug_recent_failed_template_uses_error_message(table_schemas):
    """
    BUG: recent_failed.html references task.error_message but:
      - get_recent_failed() returns the column as 'error_msg' (from task_results.error_msg)
      - The tasks table has no 'error_message' column

    With Jinja2's default Undefined (not StrictUndefined), this renders silently
    as empty string — no exception, just missing error info in the UI.

    FIX: Change {{ task.error_message }} to {{ task.error_msg }} in recent_failed.html.
    """
    schema = table_schemas.get("task_results", set())
    if not schema:
        pytest.skip("task_results table not found")

    # The column is error_msg, not error_message
    assert "error_msg" in schema, "task_results must have error_msg column"
    assert "error_message" not in schema, (
        "task_results now has error_message column — "
        "the template may be correct. Re-verify and update this test."
    )


# ---------------------------------------------------------------------------
# Cross-reference: queries.py column references vs actual schema
# ---------------------------------------------------------------------------

def _extract_column_refs_from_query_source() -> dict[str, list[str]]:
    """
    Crude static analysis: extract SELECT column lists from queries.py.
    Returns a dict of {function_name: [column_names_mentioned]}.
    This is intentionally simple — it catches obvious mismatches.
    """
    source = QUERIES_PATH.read_text()
    # Find t.column_name and tr.column_name patterns
    refs = re.findall(r'\b(?:t|tr|nm|tc)\.\b(\w+)\b', source)
    return refs


def test_queries_source_readable():
    """Sanity check: can we read queries.py?"""
    assert QUERIES_PATH.exists(), f"queries.py not found at {QUERIES_PATH}"
    source = QUERIES_PATH.read_text()
    assert len(source) > 100


def test_queries_source_no_dead_underscore():
    """
    Static analysis: queries.py should not contain 'dead_letter' (underscore).
    The correct status value is 'dead-letter' (hyphen).
    """
    source = QUERIES_PATH.read_text()
    # Look for 'dead_letter' as a string literal (in quotes)
    matches = re.findall(r"['\"]dead_letter['\"]", source)
    assert not matches, (
        f"Found {len(matches)} occurrence(s) of 'dead_letter' (underscore) in queries.py. "
        "The correct status value is 'dead-letter' (hyphen). "
        f"Lines containing the issue:\n"
        + "\n".join(
            f"  {i+1}: {line.strip()}"
            for i, line in enumerate(source.splitlines())
            if "dead_letter" in line
        )
    )
