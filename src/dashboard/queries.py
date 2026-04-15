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
                t.name,
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


async def get_pending_tasks(conn, limit: int = 50) -> list[dict]:
    """Tasks WHERE status='pending' with queue_seconds and is_blocked."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                t.id,
                t.name,
                t.project,
                t.priority,
                t.submitted_at,
                t.status,
                TIMESTAMPDIFF(SECOND, t.submitted_at, NOW()) AS queue_seconds,
                EXISTS(
                    SELECT 1 FROM task_dependencies td
                    JOIN tasks dep ON dep.id = td.depends_on
                    WHERE td.task_id = t.id AND dep.status != 'completed'
                ) AS is_blocked
            FROM tasks t
            WHERE t.status = %s
            ORDER BY t.priority ASC, t.submitted_at ASC
            LIMIT %s
            """,
            ("pending", limit),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_nodes(conn) -> list[dict]:
    """All nodes with heartbeat_age_sec, is_stale (>60s), and deployed_version."""
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
                deployed_version,
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
        if d["deployed_version"]:
            d["deployed_version"] = d["deployed_version"][:8]
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
    """Daily throughput counts based on final task outcomes only.

    Only counts tasks in a terminal state — excludes tasks still retrying
    (status='failed' with retry_count < max_retries) so retried tasks are
    not double-counted.
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                DATE(completed_at) AS date,
                COUNT(*) AS total,
                SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status = %s AND retry_count >= max_retries
                         THEN 1 ELSE 0 END) AS failure,
                SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) AS dead_letter
            FROM tasks
            WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
              AND (
                status = %s
                OR (status = %s AND retry_count >= max_retries)
                OR status = %s
              )
            GROUP BY DATE(completed_at)
            ORDER BY date ASC
            """,
            ("completed", "failed", "dead-letter",
             window_days,
             "completed", "failed", "dead-letter"),
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
    """Daily failure rate based on final task outcomes only.

    Uses the same terminal-state logic as get_throughput() so that:
      - A retried task that eventually succeeded counts as 1 success, not
        as 1 failure + 1 success.
      - Dead-lettered originals whose retry succeeded are excluded.
      - The denominator (total) is consistent with throughput.

    Queries the *tasks* table (not task_results) to avoid double-counting
    intermediate retry attempts.
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                DATE(completed_at) AS date,
                COUNT(*) AS total,
                SUM(CASE WHEN status = %s AND retry_count >= max_retries
                         THEN 1 ELSE 0 END)
                + SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) AS failures,
                ROUND(
                    100.0
                    * (
                        SUM(CASE WHEN status = %s AND retry_count >= max_retries
                                 THEN 1 ELSE 0 END)
                        + SUM(CASE WHEN status = %s THEN 1 ELSE 0 END)
                    )
                    / COUNT(*),
                    2
                ) AS failure_pct
            FROM tasks
            WHERE completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
              AND (
                status = %s
                OR (status = %s AND retry_count >= max_retries)
                OR status = %s
              )
            GROUP BY DATE(completed_at)
            ORDER BY date ASC
            """,
            (
                "failed", "dead-letter",
                "failed", "dead-letter",
                window_days,
                "completed", "failed", "dead-letter",
            ),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_token_spend_summary(conn, days: int = 1) -> dict:
    """Summary and per-source/provider/model token usage and cost from task_telemetry.

    Returns a dict with:
      - total_input, total_output, total_tokens, total_cost, total_rows
      - breakdown: list of dicts with source, provider, model, input_tokens, output_tokens, cost
      - days: the period requested
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        # Summary totals — use MAX per task to avoid double-counting
        # cumulative snapshots, then SUM across tasks.
        await cur.execute(
            """
            SELECT
                COALESCE(SUM(max_input), 0) AS total_input,
                COALESCE(SUM(max_output), 0) AS total_output,
                COALESCE(SUM(max_input + max_output), 0) AS total_tokens,
                COALESCE(SUM(max_cost), 0) AS total_cost,
                COALESCE(SUM(row_count), 0) AS total_rows
            FROM (
                SELECT task_id,
                       MAX(input_tokens) AS max_input,
                       MAX(output_tokens) AS max_output,
                       MAX(estimated_cost_usd) AS max_cost,
                       COUNT(*) AS row_count
                FROM task_telemetry
                WHERE recorded_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY task_id
            ) per_task
            """,
            (days,),
        )
        summary_row = await cur.fetchone()

        # Breakdown by source, provider, model — use MAX per task to
        # avoid double-counting cumulative snapshots.
        await cur.execute(
            """
            SELECT source, provider, model,
                   SUM(max_input) AS input_tokens,
                   SUM(max_output) AS output_tokens,
                   SUM(max_cost) AS cost
            FROM (
                SELECT task_id, source, provider, model,
                       MAX(input_tokens) AS max_input,
                       MAX(output_tokens) AS max_output,
                       MAX(estimated_cost_usd) AS max_cost
                FROM task_telemetry
                WHERE recorded_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY task_id, source, provider, model
            ) per_task
            GROUP BY source, provider, model
            ORDER BY cost DESC
            """,
            (days,),
        )
        breakdown_rows = await cur.fetchall()

    summary = dict(summary_row) if summary_row else {
        "total_input": 0,
        "total_output": 0,
        "total_tokens": 0,
        "total_cost": 0,
        "total_rows": 0,
    }
    summary["breakdown"] = [dict(row) for row in breakdown_rows]
    summary["days"] = days
    return summary


async def get_token_spend(conn, window_days: int = 7) -> list[dict]:
    """Per provider/model token usage from task_telemetry."""
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            """
            SELECT
                provider,
                model,
                SUM(max_tokens) AS total_tokens,
                SUM(max_cost) AS total_usd
            FROM (
                SELECT task_id, provider, model,
                       MAX(input_tokens + output_tokens) AS max_tokens,
                       MAX(estimated_cost_usd) AS max_cost
                FROM task_telemetry
                WHERE recorded_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY task_id, provider, model
            ) per_task
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
                MAX(input_tokens) AS total_input_tokens,
                MAX(output_tokens) AS total_output_tokens,
                MAX(cost_usd) AS total_cost_usd,
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
                GROUP_CONCAT(SUBSTRING(tc.commit_sha, 1, 8) ORDER BY tc.repo_slug SEPARATOR '|') AS commit_sha,
                GROUP_CONCAT(tc.target_branch ORDER BY tc.repo_slug SEPARATOR '|') AS target_branch
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
            raw_targets = d["target_branch"].split("|") if d.get("target_branch") else [None] * len(slugs)
            seen = set()
            unique_commits = []
            for slug, branch, sha, raw_target in zip(slugs, branches, shas, raw_targets):
                key = (slug, branch)
                if key not in seen:
                    seen.add(key)
                    if raw_target and raw_target != "None":
                        push_target = raw_target
                    elif branch.startswith("fleet/"):
                        push_target = "main"
                    else:
                        push_target = branch
                    unique_commits.append(
                        {
                            "repo_slug": slug,
                            "branch": branch,
                            "commit_sha": sha,
                            "push_target": push_target,
                        }
                    )
            d["repo_commits"] = unique_commits
            all_targets = [rc["push_target"] for rc in unique_commits]
            d["push_target"] = all_targets[0] if all_targets else None
        else:
            d["repo_commits"] = []
            d["push_target"] = None
        result.append(d)
    return result


async def get_recent_failed(conn, limit: int = 10, window_days: int = 7) -> list[dict]:
    """Recent failed/dead_letter tasks with resolution status.

    Only returns failures from the last *window_days* days so that stale
    failures don't crowd out today's problems.  Results are ordered newest-
    first using ``completed_at`` with a ``submitted_at`` fallback for rows
    where ``completed_at`` is NULL.
    """
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
              AND COALESCE(t.completed_at, t.submitted_at)
                  >= DATE_SUB(NOW(), INTERVAL %s DAY)
            ORDER BY COALESCE(t.completed_at, t.submitted_at) DESC
            LIMIT %s
            """,
            (window_days, limit),
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_security_overview(conn) -> dict:
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT COALESCE(SUM(total_invocations),0) AS total_invocations,
                          COALESCE(SUM(high_count + critical_count),0) AS high_flags,
                          COALESCE(SUM(block_count),0) AS blocks
                   FROM audit_sessions
                   WHERE pushed_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"""
            )
            inv = await cur.fetchone() or {}
            await cur.execute(
                """SELECT COUNT(*) AS unreviewed_alerts
                   FROM security_alerts WHERE reviewed = false"""
            )
            alerts = await cur.fetchone() or {}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("security_overview query failed: %s", e)
        inv = {}
        alerts = {}
    total = int(inv.get('total_invocations', 0) or 0)
    blocks = int(inv.get('blocks', 0) or 0)
    return {
        'total_invocations': total,
        'high_flags': int(inv.get('high_flags', 0) or 0),
        'blocks': blocks,
        'unreviewed_alerts': alerts.get('unreviewed_alerts', 0) or 0,
        'block_rate_pct': round(blocks / total * 100, 1) if total > 0 else 0.0,
    }


async def get_unreviewed_alerts(conn, limit: int = 20) -> list[dict]:
    """Unreviewed security alerts, critical first, then by created_at DESC."""
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT
                    id,
                    invocation_id,
                    task_id,
                    worker_node_id,
                    risk_level,
                    tool_name,
                    tool_args,
                    classifier_rule,
                    reason,
                    reviewed,
                    reviewed_by,
                    reviewed_at,
                    created_at
                FROM security_alerts
                WHERE reviewed = false
                ORDER BY FIELD(risk_level, 'critical', 'high') DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    except Exception:
        # Security tables may not exist yet
        return []
    return [dict(row) for row in rows]


async def get_blocked_operations(conn, limit: int = 20) -> list[dict]:
    """Last N blocked tool invocations from the last 24h."""
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT
                    tool_name,
                    tool_args,
                    classifier_rule,
                    worker_node_id,
                    timestamp
                FROM tool_invocations
                WHERE decision = %s
                  AND timestamp > DATE_SUB(NOW(), INTERVAL 24 HOUR)
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                ("block", limit),
            )
            rows = await cur.fetchall()
    except Exception:
        # Security tables may not exist yet
        return []
    return [dict(row) for row in rows]


async def get_security_incident(conn, invocation_id: str) -> dict | None:
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute('SELECT * FROM tool_invocations WHERE id = %s', (invocation_id,))
            invocation = await cur.fetchone()
            if not invocation:
                return None
            await cur.execute('SELECT * FROM security_alerts WHERE invocation_id = %s', (invocation_id,))
            alert = await cur.fetchone()
            await cur.execute(
                'SELECT id, timestamp, tool_name, risk_level, decision FROM tool_invocations WHERE task_id = %s ORDER BY timestamp LIMIT 11',
                (invocation['task_id'],))
            context = await cur.fetchall()
        return {'invocation': dict(invocation), 'alert': dict(alert) if alert else None, 'context': [dict(r) for r in context]}
    except Exception:
        return None


async def get_tool_heatmap(conn, limit: int = 20) -> list[dict]:
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT classifier_rule, tool_name, risk_level, COUNT(*) as hit_count
                   FROM tool_invocations
                   WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                   AND classifier_rule IS NOT NULL
                   GROUP BY classifier_rule, tool_name, risk_level
                   ORDER BY hit_count DESC LIMIT %s""",
                (limit,),
            )
            return [dict(r) for r in await cur.fetchall()]
    except Exception:
        return []


async def get_worker_security_health(conn) -> list[dict]:
    """Per-worker security stats for last 24h, including all active workers."""
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT n.id AS worker_node_id,
                    COALESCE(SUM(a.total_invocations), 0) AS total,
                    COALESCE(SUM(a.block_count), 0) AS blocks,
                    COALESCE(SUM(a.high_count), 0) AS highs,
                    COALESCE(SUM(a.critical_count), 0) AS criticals,
                    CASE WHEN COALESCE(SUM(a.total_invocations), 0) > 0
                        THEN ROUND(COALESCE(SUM(a.block_count), 0) / SUM(a.total_invocations) * 100, 1)
                        ELSE 0 END AS block_rate_pct,
                    CASE WHEN SUM(a.total_invocations) IS NULL THEN 1 ELSE 0 END AS no_data
                FROM nodes n
                LEFT JOIN audit_sessions a ON a.worker_node_id = n.id
                  AND a.pushed_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
                WHERE n.status IN ('active', 'online')
                GROUP BY n.id
                ORDER BY block_rate_pct DESC
                """
            )
            rows = await cur.fetchall()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("worker_security_health query failed: %s", e)
        return []
    return [dict(row) for row in rows]


async def get_security_timeline(conn, hours: int = 168) -> list[dict]:
    """Hourly bucket counts of high/critical invocations over last N hours."""
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT DATE_FORMAT(pushed_at, '%%Y-%%m-%%d %%H:00') AS hour_bucket,
                       COALESCE(SUM(high_count),0) AS high_count,
                       COALESCE(SUM(critical_count),0) AS critical_count
                FROM audit_sessions
                WHERE pushed_at > DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
                """,
                (hours,),
            )
            rows = await cur.fetchall()
    except Exception:
        return []
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
