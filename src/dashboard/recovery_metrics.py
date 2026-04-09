"""Analytics queries for ADR-0026 recovery data (task_investigations)."""

import aiomysql


async def failure_patterns_by_cause(conn, days: int = 30) -> list[dict]:
    """GROUP BY root_cause from task_investigations with recovery stats."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                root_cause,
                COUNT(*) AS count,
                SUM(CASE WHEN retry_task_id IS NOT NULL THEN 1 ELSE 0 END) AS auto_retry_count,
                SUM(CASE WHEN fix_successful = 1 THEN 1 ELSE 0 END) AS success_count,
                ROUND(
                    100.0 * SUM(CASE WHEN fix_successful = 1 THEN 1 ELSE 0 END) / COUNT(*),
                    2
                ) AS recovery_rate_pct
            FROM task_investigations
            WHERE investigated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY root_cause
            ORDER BY count DESC
            """,
            (days,),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def fragile_test_commands(conn, limit: int = 20) -> list[dict]:
    """Tasks where root_cause = 'fragile-test-cmd' with task name, test command, error summary."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.name AS task_name,
                t.type AS test_command,
                ti.error_summary
            FROM task_investigations ti
            JOIN tasks t ON t.id = ti.task_id
            WHERE ti.root_cause = %s
            ORDER BY ti.investigated_at DESC
            LIMIT %s
            """,
            ("fragile-test-cmd", limit),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def auto_recovery_success_rate(conn) -> dict:
    """Total investigations, auto-retried count, successful retries, rate percentage."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                COUNT(*) AS total_investigations,
                SUM(CASE WHEN retry_task_id IS NOT NULL THEN 1 ELSE 0 END) AS auto_retried_count,
                SUM(CASE WHEN retry_task_id IS NOT NULL AND fix_successful = 1 THEN 1 ELSE 0 END) AS successful_retries
            FROM task_investigations
            """
        )
        row = await cur.fetchone()
    if row is None:
        return {
            "total_investigations": 0,
            "auto_retried_count": 0,
            "successful_retries": 0,
            "success_rate_pct": None,
        }
    d = dict(row)
    if d["auto_retried_count"]:
        d["success_rate_pct"] = round(
            100.0 * d["successful_retries"] / d["auto_retried_count"], 2
        )
    else:
        d["success_rate_pct"] = None
    return d


async def retry_chain_depths(conn, min_depth: int = 2) -> list[dict]:
    """Find retry chains using task_investigations.retry_task_id.

    Returns chains with depth >= min_depth, including original task id,
    chain depth, and final status.
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        # Find root investigations (not themselves a retry of another)
        await cur.execute(
            """
            SELECT ti.task_id AS original_task_id
            FROM task_investigations ti
            WHERE ti.task_id NOT IN (
                SELECT retry_task_id
                FROM task_investigations
                WHERE retry_task_id IS NOT NULL
            )
              AND ti.retry_task_id IS NOT NULL
            """
        )
        roots = await cur.fetchall()

    results = []
    async with conn.cursor(aiomysql.DictCursor) as cur:
        for root in roots:
            original_task_id = root["original_task_id"]
            depth = 1
            current_task_id = original_task_id

            # Walk the chain
            while True:
                await cur.execute(
                    """
                    SELECT retry_task_id
                    FROM task_investigations
                    WHERE task_id = %s AND retry_task_id IS NOT NULL
                    LIMIT 1
                    """,
                    (current_task_id,),
                )
                link = await cur.fetchone()
                if link is None:
                    break
                current_task_id = link["retry_task_id"]
                depth += 1

            if depth >= min_depth:
                # Get final status
                await cur.execute(
                    "SELECT status FROM tasks WHERE id = %s",
                    (current_task_id,),
                )
                status_row = await cur.fetchone()
                results.append(
                    {
                        "original_task_id": original_task_id,
                        "chain_depth": depth,
                        "final_status": status_row["status"] if status_row else None,
                    }
                )

    return results


async def get_blocked_chains(conn) -> list[dict]:
    """Find pending tasks blocked by dead-letter upstream dependencies.

    Returns one row per dead-letter upstream task: its name, count of blocked
    downstream tasks, and the names of the first 3 blocked tasks.
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t_up.name AS upstream_task_name,
                COUNT(td.downstream_task_id) AS blocked_count,
                GROUP_CONCAT(t_down.name ORDER BY t_down.id SEPARATOR '|||') AS blocked_names_concat
            FROM task_dependencies td
            JOIN tasks t_up ON t_up.id = td.upstream_task_id
            JOIN tasks t_down ON t_down.id = td.downstream_task_id
            WHERE t_up.status = 'dead-letter'
              AND t_down.status = 'pending'
            GROUP BY td.upstream_task_id, t_up.name
            ORDER BY blocked_count DESC
            """
        )
        rows = await cur.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        names_concat = d.pop("blocked_names_concat") or ""
        all_names = [n for n in names_concat.split("|||") if n]
        d["blocked_task_names"] = all_names[:3]
        result.append(d)
    return result


async def get_failure_patterns(conn, days: int = 7) -> list[dict]:
    """Root cause breakdown for the last `days` days — alias with a 7-day default."""
    return await failure_patterns_by_cause(conn, days=days)


async def get_recovery_overview(conn, days: int = 1) -> dict:
    """Stat card data: total investigations, auto-recovery rate, pending retries, escalated count."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                COUNT(*) AS total_investigations,
                SUM(CASE WHEN retry_task_id IS NOT NULL AND fix_successful = 1 THEN 1 ELSE 0 END) AS successful_retries,
                SUM(CASE WHEN retry_task_id IS NOT NULL THEN 1 ELSE 0 END) AS auto_retried_count,
                SUM(CASE WHEN action_taken = 'resubmitted' AND fix_successful IS NULL THEN 1 ELSE 0 END) AS pending_retries,
                SUM(CASE WHEN action_taken = 'escalated' THEN 1 ELSE 0 END) AS escalated_count
            FROM task_investigations
            WHERE investigated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            """,
            (days,),
        )
        row = await cur.fetchone()
    if row is None:
        return {
            "total_investigations": 0,
            "auto_recovery_rate": None,
            "pending_retries": 0,
            "escalated_count": 0,
        }
    d = dict(row)
    auto_retried = d.pop("auto_retried_count") or 0
    successful = d.pop("successful_retries") or 0
    if auto_retried:
        d["auto_recovery_rate"] = round(100.0 * successful / auto_retried, 1)
    else:
        d["auto_recovery_rate"] = None
    d["pending_retries"] = int(d["pending_retries"] or 0)
    d["escalated_count"] = int(d["escalated_count"] or 0)
    return d


async def get_active_investigations(conn) -> list[dict]:
    """In-flight retries: action_taken=resubmitted AND fix_successful IS NULL."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t_orig.name AS original_task_name,
                t_retry.status AS retry_task_status,
                TIMESTAMPDIFF(SECOND, ti.investigated_at, NOW()) AS age_seconds
            FROM task_investigations ti
            JOIN tasks t_orig ON t_orig.id = ti.task_id
            JOIN tasks t_retry ON t_retry.id = ti.retry_task_id
            WHERE ti.action_taken = 'resubmitted'
              AND ti.fix_successful IS NULL
            ORDER BY ti.investigated_at ASC
            """
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def project_failure_rates(conn) -> list[dict]:
    """Per-project total tasks, failed, completed, failure_rate_pct ordered by failure_rate DESC."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                project,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN status IN ('failed', 'dead-letter') THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                ROUND(
                    100.0 * SUM(CASE WHEN status IN ('failed', 'dead-letter') THEN 1 ELSE 0 END) / COUNT(*),
                    2
                ) AS failure_rate_pct
            FROM tasks
            GROUP BY project
            ORDER BY failure_rate_pct DESC
            """
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]
