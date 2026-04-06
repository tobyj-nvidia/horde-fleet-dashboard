"""SQL queries for the Horde Fleet Dashboard."""

import aiomysql


async def get_queue_counts(conn) -> dict[str, int]:
    """COUNT(*) grouped by tasks.status."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status")
        rows = await cur.fetchall()
    return {row["status"]: row["cnt"] for row in rows}


async def get_active_tasks(conn) -> list[dict]:
    """Tasks WHERE status IN ('claimed','running') with running_sec and is_blocked."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.id,
                t.type,
                t.project,
                t.status,
                t.claimed_by,
                t.started_at,
                t.retry_count,
                t.resource_class,
                TIMESTAMPDIFF(SECOND, t.started_at, NOW()) AS running_sec,
                EXISTS(
                    SELECT 1 FROM task_dependencies td
                    JOIN tasks dep ON dep.id = td.depends_on
                    WHERE td.task_id = t.id AND dep.status != 'completed'
                ) AS is_blocked
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
                id AS node_id,
                status,
                capabilities,
                active_tasks,
                max_concurrent,
                gpu_capacity,
                last_heartbeat,
                TIMESTAMPDIFF(SECOND, last_heartbeat, NOW()) AS heartbeat_age_sec
            FROM nodes
            ORDER BY id ASC
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
                t.id,
                t.type,
                t.project,
                t.status,
                t.retry_count,
                t.submitted_at,
                LEFT(t.prompt, 60) AS prompt_snippet,
                tr.error_msg,
                tr.completed_at,
                TIMESTAMPDIFF(SECOND, tr.completed_at, NOW()) AS failure_age_sec
            FROM tasks t
            LEFT JOIN task_results tr ON t.id = tr.task_id
            WHERE t.status = %s
            ORDER BY t.submitted_at DESC
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
                SUM(CASE WHEN outcome = %s THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN outcome != %s THEN 1 ELSE 0 END) AS failure
            FROM task_results
            WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE(completed_at)
            ORDER BY date ASC
            """,
            ("success", "success", window_days),
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
                SUM(CASE WHEN outcome != %s THEN 1 ELSE 0 END) AS failures,
                ROUND(
                    100.0 * SUM(CASE WHEN outcome != %s THEN 1 ELSE 0 END) / COUNT(*),
                    2
                ) AS failure_pct
            FROM task_results
            WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE(completed_at)
            ORDER BY date ASC
            """,
            ("success", "success", window_days),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_token_spend_summary(conn, period_days: int = 1) -> list[dict]:
    """Per source/model token usage and cost from task_telemetry."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT source, model,
                   SUM(input_tokens + output_tokens) AS total_tokens,
                   SUM(estimated_cost_usd) AS total_cost_usd
            FROM task_telemetry
            WHERE recorded_at >= NOW() - INTERVAL %s DAY
            GROUP BY source, model
            ORDER BY total_cost_usd DESC
            """,
            (period_days,),
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
                SUM(estimated_cost_usd) AS total_usd
            FROM task_telemetry
            WHERE recorded_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
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
                ORDER BY submitted_at DESC
                LIMIT %s OFFSET %s
                """,
                (status, limit, offset),
            )
        else:
            await cur.execute(
                """
                SELECT * FROM tasks
                ORDER BY submitted_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        rows = await cur.fetchall()

    return [dict(row) for row in rows], total


async def get_node_metrics_latest(conn) -> list[dict]:
    """Most recent row per node from node_metrics."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT nm.node_id, nm.cpu_pct, nm.mem_pct, nm.mem_used_gb, nm.mem_total_gb,
                   nm.gpu_pct, nm.gpu_mem_pct, nm.gpu_mem_used_gb, nm.gpu_mem_total_gb,
                   nm.disk_pct, nm.recorded_at
            FROM node_metrics nm
            INNER JOIN (
                SELECT node_id, MAX(recorded_at) AS max_recorded_at
                FROM node_metrics
                GROUP BY node_id
            ) latest ON nm.node_id = latest.node_id AND nm.recorded_at = latest.max_recorded_at
            ORDER BY nm.node_id ASC
            """
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_node_metrics_history(
    conn,
    node_id: str | None = None,
    window_hours: int = 24,
    resolution_minutes: int = 5,
) -> list[dict]:
    """Downsampled node metrics history. If node_id is None, average across all nodes."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        if node_id is not None:
            await cur.execute(
                """
                SELECT
                    FROM_UNIXTIME(
                        FLOOR(UNIX_TIMESTAMP(recorded_at) / (%s * 60)) * (%s * 60)
                    ) AS timestamp,
                    node_id,
                    AVG(cpu_pct) AS cpu_pct,
                    AVG(gpu_pct) AS gpu_pct,
                    AVG(gpu_mem_pct) AS gpu_mem_pct,
                    AVG(mem_pct) AS mem_pct,
                    AVG(disk_pct) AS disk_pct
                FROM node_metrics
                WHERE node_id = %s
                  AND recorded_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY FLOOR(UNIX_TIMESTAMP(recorded_at) / (%s * 60)), node_id
                ORDER BY timestamp ASC
                """,
                (resolution_minutes, resolution_minutes, node_id, window_hours, resolution_minutes),
            )
        else:
            await cur.execute(
                """
                SELECT
                    FROM_UNIXTIME(
                        FLOOR(UNIX_TIMESTAMP(recorded_at) / (%s * 60)) * (%s * 60)
                    ) AS timestamp,
                    NULL AS node_id,
                    AVG(cpu_pct) AS cpu_pct,
                    AVG(gpu_pct) AS gpu_pct,
                    AVG(gpu_mem_pct) AS gpu_mem_pct,
                    AVG(mem_pct) AS mem_pct,
                    AVG(disk_pct) AS disk_pct
                FROM node_metrics
                WHERE recorded_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY FLOOR(UNIX_TIMESTAMP(recorded_at) / (%s * 60))
                ORDER BY timestamp ASC
                """,
                (resolution_minutes, resolution_minutes, window_hours, resolution_minutes),
            )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_node_utilization_history(conn) -> list[dict]:
    """5-minute bucketed CPU/GPU utilization per node over 48 hours."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                node_id,
                FROM_UNIXTIME(
                    FLOOR(UNIX_TIMESTAMP(recorded_at) / 300) * 300
                ) AS bucket,
                AVG(cpu_pct) AS cpu_pct,
                AVG(gpu_pct) AS gpu_pct
            FROM node_metrics
            WHERE recorded_at >= DATE_SUB(NOW(), INTERVAL 48 HOUR)
            GROUP BY node_id, FLOOR(UNIX_TIMESTAMP(recorded_at) / 300)
            ORDER BY node_id, bucket
            """
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_recent_completed(conn, limit: int = 10) -> list[dict]:
    """Recent completed tasks with duration, commit hashes, and repo info."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.id,
                t.name,
                t.project,
                t.claimed_by,
                t.started_at,
                t.completed_at,
                t.repos,
                TIMESTAMPDIFF(SECOND, t.started_at, t.completed_at) AS duration_seconds,
                GROUP_CONCAT(SUBSTRING(tc.commit_sha, 1, 7)) AS commit_hashes,
                GROUP_CONCAT(tc.repo_slug ORDER BY tc.repo_slug SEPARATOR '|') AS repo_slug,
                GROUP_CONCAT(tc.branch ORDER BY tc.repo_slug SEPARATOR '|') AS branch,
                GROUP_CONCAT(SUBSTRING(tc.commit_sha, 1, 8) ORDER BY tc.repo_slug SEPARATOR '|') AS commit_sha
            FROM tasks t
            LEFT JOIN task_commits tc ON tc.task_id = t.id
            WHERE t.status = %s
            GROUP BY t.id, t.name, t.project, t.claimed_by, t.started_at, t.completed_at, t.repos
            ORDER BY t.completed_at DESC
            LIMIT %s
            """,
            ("completed", limit),
        )
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d["repo_slug"]:
            slugs = d["repo_slug"].split("|")
            branches = d["branch"].split("|")
            shas = d["commit_sha"].split("|")
            d["repo_commits"] = [
                {
                    "repo_slug": slug,
                    "branch": branch,
                    "commit_sha": sha,
                    "push_target": "main" if branch.startswith("fleet/") else branch,
                }
                for slug, branch, sha in zip(slugs, branches, shas)
            ]
            d["push_target"] = "main" if any(b.startswith("fleet/") for b in branches) else branches[0]
        else:
            d["repo_commits"] = []
            d["push_target"] = None
        result.append(d)
    return result


async def get_recent_failed(conn, limit: int = 10) -> list[dict]:
    """Recent failed/dead_letter tasks with resolution status."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.id,
                t.name,
                t.project,
                t.claimed_by,
                t.completed_at,
                tr.error_msg,
                t.retry_count,
                t.max_retries,
                t.status,
                EXISTS(
                    SELECT 1 FROM tasks t2
                    WHERE t2.name = t.name
                      AND t2.status = 'completed'
                      AND t2.completed_at > t.completed_at
                ) AS is_resolved
            FROM tasks t
            LEFT JOIN task_results tr ON tr.task_id = t.id
            WHERE t.status IN ('failed', 'dead-letter')
            ORDER BY t.completed_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


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
