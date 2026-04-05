"""SQL queries for the Horde Fleet Dashboard."""

import aiomysql


async def get_queue_counts(conn) -> dict[str, int]:
    """COUNT(*) grouped by tasks.status."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status")
        rows = await cur.fetchall()
    return {row["status"]: row["cnt"] for row in rows}


async def get_active_tasks(conn) -> list[dict]:
    """Tasks WHERE status IN ('claimed','running') with running_sec."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.task_id,
                t.task_type,
                t.status,
                t.claimed_by,
                t.started_at,
                t.retry_count,
                TIMESTAMPDIFF(SECOND, t.started_at, NOW()) AS running_sec
            FROM tasks t
            WHERE t.status IN (%s, %s)
            ORDER BY t.started_at ASC
            """,
            ("claimed", "running"),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_nodes(conn) -> list[dict]:
    """All nodes with heartbeat_age_sec and is_stale (>60s)."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                node_id,
                status,
                capabilities,
                active_tasks,
                max_concurrent,
                last_heartbeat,
                TIMESTAMPDIFF(SECOND, last_heartbeat, NOW()) AS heartbeat_age_sec
            FROM nodes
            ORDER BY node_id ASC
            """
        )
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["is_stale"] = (d["heartbeat_age_sec"] or 0) > 60
        result.append(d)
    return result


async def get_dead_letter(conn, limit: int = 20) -> list[dict]:
    """Tasks WHERE status='dead-letter' joined with task_results for error_msg."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.task_id,
                t.task_type,
                t.status,
                t.retry_count,
                t.created_at,
                t.updated_at,
                tr.error_msg,
                tr.completed_at
            FROM tasks t
            LEFT JOIN task_results tr ON t.task_id = tr.task_id
            WHERE t.status = %s
            ORDER BY t.updated_at DESC
            LIMIT %s
            """,
            ("dead-letter", limit),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_throughput(conn, window_days: int = 7) -> list[dict]:
    """Daily total/success/failure counts from task_results."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                DATE(completed_at) AS date,
                COUNT(*) AS total,
                SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status != %s THEN 1 ELSE 0 END) AS failure
            FROM task_results
            WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE(completed_at)
            ORDER BY date ASC
            """,
            ("completed", "completed", window_days),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_duration_percentiles(conn, window_days: int = 7) -> dict:
    """p50, p95, p99, avg duration_sec from task_results."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                AVG(duration_sec) AS avg_sec,
                MAX(CASE WHEN pct_rank <= 0.50 THEN duration_sec END) AS p50_sec,
                MAX(CASE WHEN pct_rank <= 0.95 THEN duration_sec END) AS p95_sec,
                MAX(CASE WHEN pct_rank <= 0.99 THEN duration_sec END) AS p99_sec
            FROM (
                SELECT
                    duration_sec,
                    PERCENT_RANK() OVER (ORDER BY duration_sec) AS pct_rank
                FROM task_results
                WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                  AND duration_sec IS NOT NULL
            ) ranked
            """,
            (window_days,),
        )
        row = await cur.fetchone()
    if row is None:
        return {"p50_sec": None, "p95_sec": None, "p99_sec": None, "avg_sec": None}
    return {
        "p50_sec": row["p50_sec"],
        "p95_sec": row["p95_sec"],
        "p99_sec": row["p99_sec"],
        "avg_sec": row["avg_sec"],
    }


async def get_failure_rate(conn, window_days: int = 7) -> list[dict]:
    """Daily total/failures/failure_pct from task_results."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                DATE(completed_at) AS date,
                COUNT(*) AS total,
                SUM(CASE WHEN status != %s THEN 1 ELSE 0 END) AS failures,
                ROUND(
                    100.0 * SUM(CASE WHEN status != %s THEN 1 ELSE 0 END) / COUNT(*),
                    2
                ) AS failure_pct
            FROM task_results
            WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE(completed_at)
            ORDER BY date ASC
            """,
            ("completed", "completed", window_days),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_token_spend(conn, window_days: int = 7) -> list[dict]:
    """Per provider/model token usage from task_telemetry."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                provider,
                model,
                SUM(input_tokens + output_tokens) AS total_tokens,
                SUM(cost_usd) AS total_usd
            FROM task_telemetry
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY provider, model
            ORDER BY total_usd DESC
            """,
            (window_days,),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_task(conn, task_id: str) -> dict | None:
    """Full task + result + telemetry aggregates for a single task."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            "SELECT * FROM tasks WHERE task_id = %s",
            (task_id,),
        )
        task_row = await cur.fetchone()
        if task_row is None:
            return None

        await cur.execute(
            "SELECT * FROM task_results WHERE task_id = %s",
            (task_id,),
        )
        result_row = await cur.fetchone()

        await cur.execute(
            """
            SELECT
                SUM(input_tokens) AS total_input_tokens,
                SUM(output_tokens) AS total_output_tokens,
                SUM(cost_usd) AS total_cost_usd,
                COUNT(*) AS api_calls
            FROM task_telemetry
            WHERE task_id = %s
            """,
            (task_id,),
        )
        telemetry_row = await cur.fetchone()

    return {
        "task": dict(task_row),
        "result": dict(result_row) if result_row else None,
        "telemetry": dict(telemetry_row) if telemetry_row else None,
    }


async def get_tasks(
    conn, status: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    """Paginated task list with optional status filter. Returns (tasks, total)."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        if status is not None:
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE status = %s",
                (status,),
            )
        else:
            await cur.execute("SELECT COUNT(*) AS cnt FROM tasks")
        count_row = await cur.fetchone()
        total = count_row["cnt"] if count_row else 0

        if status is not None:
            await cur.execute(
                """
                SELECT * FROM tasks
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (status, limit, offset),
            )
        else:
            await cur.execute(
                """
                SELECT * FROM tasks
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        rows = await cur.fetchall()

    return [dict(row) for row in rows], total


async def retry_task(conn, task_id: str) -> bool:
    """SET status='pending' WHERE status='dead-letter'. Returns True if updated."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            UPDATE tasks
            SET
                status = %s,
                claimed_by = NULL,
                claim_expires_at = NULL,
                started_at = NULL
            WHERE task_id = %s
              AND status = %s
            """,
            ("pending", task_id, "dead-letter"),
        )
        affected = cur.rowcount
    await conn.commit()
    return affected > 0
