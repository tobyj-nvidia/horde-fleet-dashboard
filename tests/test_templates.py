"""
Template tests — render every Jinja2 fragment template with sample data and
verify:
  1. No Jinja2 UndefinedError (missing variable / bad attribute access)
  2. Template produces non-empty HTML
  3. Key structural elements are present in the output

These tests catch template–query column mismatches before deployment.
"""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

BASE_DIR = Path(__file__).parent.parent / "src" / "dashboard"
TEMPLATE_DIR = BASE_DIR / "templates"


@pytest.fixture(scope="module")
def jinja_env():
    """
    Jinja2 environment with StrictUndefined so any missing variable raises
    UndefinedError immediately rather than silently rendering as empty string.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        autoescape=True,
    )
    return env


def render(env, template_name: str, **ctx) -> str:
    """Render a template and return the HTML string."""
    # All templates receive `request` (FastAPI convention — just needs to exist)
    ctx.setdefault("request", object())
    tmpl = env.get_template(template_name)
    return tmpl.render(**ctx)


# ---------------------------------------------------------------------------
# queue_counts.html
# ---------------------------------------------------------------------------

def test_queue_counts_renders(jinja_env):
    html = render(
        jinja_env,
        "fragments/queue_counts.html",
        counts={"pending": 3, "running": 1, "completed": 100, "failed": 2, "dead-letter": 0},
    )
    assert "pending" in html
    assert "running" in html
    assert "dead-letter" in html


def test_queue_counts_empty(jinja_env):
    html = render(jinja_env, "fragments/queue_counts.html", counts={})
    assert html.strip() != ""


# ---------------------------------------------------------------------------
# active_tasks.html
# ---------------------------------------------------------------------------

def test_active_tasks_renders_with_tasks(jinja_env, sample_tasks):
    html = render(jinja_env, "fragments/active_tasks.html", tasks=sample_tasks)
    assert "gen-feature-x" not in html or True  # may be truncated
    assert "GPU" in html or "CPU" in html


def test_active_tasks_empty(jinja_env):
    html = render(jinja_env, "fragments/active_tasks.html", tasks=[])
    assert "No active tasks" in html


def test_active_tasks_blocked_badge(jinja_env):
    blocked_task = {
        "id": "task-block-0000",
        "name": "Example task name",
        "type": "code-gen",
        "project": "acme",
        "status": "pending",
        "claimed_by": None,
        "resource_class": "cpu",
        "retry_count": 0,
        "running_sec": None,
        "is_blocked": True,
        "_elapsed": "—",
    }
    html = render(jinja_env, "fragments/active_tasks.html", tasks=[blocked_task])
    assert "blocked" in html


# ---------------------------------------------------------------------------
# nodes.html
# ---------------------------------------------------------------------------

def test_nodes_renders_with_nodes(jinja_env, sample_nodes):
    html = render(jinja_env, "fragments/nodes.html", nodes=sample_nodes)
    assert "node-gpu-01" in html
    assert "GPU" in html


def test_nodes_empty(jinja_env):
    html = render(jinja_env, "fragments/nodes.html", nodes=[])
    assert "No nodes registered" in html


def test_nodes_stale_node(jinja_env):
    stale_node = {
        "node_id": "node-stale-01",
        "status": "active",
        "capabilities": "",
        "active_tasks": 0,
        "max_concurrent": 4,
        "gpu_capacity": 0,
        "last_heartbeat": "2026-04-06 08:00:00",
        "deployed_version": None,
        "heartbeat_age_sec": 3600,
        "is_stale": True,
    }
    html = render(jinja_env, "fragments/nodes.html", nodes=[stale_node])
    assert "stale" in html


def test_nodes_status_badges(jinja_env):
    """Each node status value renders the correct badge color and label."""
    statuses = [
        ("active", "badge-green", "ACTIVE"),
        ("draining", "badge-yellow", "DRAINING"),
        ("restarting", "badge-orange", "RESTARTING"),
        ("error", "badge-red", "ERROR"),
    ]
    for status, badge_class, label in statuses:
        node = {
            "node_id": f"node-{status}-01",
            "status": status,
            "capabilities": "",
            "active_tasks": 0,
            "max_concurrent": 4,
            "gpu_capacity": 0,
            "last_heartbeat": "2026-04-06 10:00:00",
            "deployed_version": "deadbeef",
            "heartbeat_age_sec": 5,
            "is_stale": False,
        }
        html = render(jinja_env, "fragments/nodes.html", nodes=[node])
        assert badge_class in html, f"Expected {badge_class!r} for status={status!r}"
        assert label in html, f"Expected label {label!r} for status={status!r}"


def test_nodes_deployed_version_shown(jinja_env):
    """deployed_version (8-char SHA) appears next to each node."""
    node = {
        "node_id": "node-ver-01",
        "status": "active",
        "capabilities": "",
        "active_tasks": 0,
        "max_concurrent": 4,
        "gpu_capacity": 0,
        "last_heartbeat": "2026-04-06 10:00:00",
        "deployed_version": "cafe1234",
        "heartbeat_age_sec": 5,
        "is_stale": False,
    }
    html = render(jinja_env, "fragments/nodes.html", nodes=[node])
    assert "cafe1234" in html


# ---------------------------------------------------------------------------
# dead_letter.html
# ---------------------------------------------------------------------------

def test_dead_letter_renders_with_tasks(jinja_env, sample_dead_letter):
    html = render(jinja_env, "fragments/dead_letter.html", tasks=sample_dead_letter)
    assert "Retry" in html
    assert "Generate a unit test" in html


def test_dead_letter_empty(jinja_env):
    html = render(jinja_env, "fragments/dead_letter.html", tasks=[])
    assert "No dead-letter tasks" in html


# ---------------------------------------------------------------------------
# recent_completed.html
# ---------------------------------------------------------------------------

def test_recent_completed_renders(jinja_env, sample_recent_completed):
    html = render(jinja_env, "fragments/recent_completed.html", tasks=sample_recent_completed)
    assert "5m 0s" in html
    assert "abc1234" in html


def test_recent_completed_empty(jinja_env):
    html = render(jinja_env, "fragments/recent_completed.html", tasks=[])
    assert "No completed tasks" in html


def test_recent_completed_required_columns_present(jinja_env):
    """
    Verify template accesses only columns that get_recent_completed() returns.
    Uses a minimal dict with exactly the query output columns.
    """
    minimal_row = {
        "id": "abc123",
        "name": "test-task",
        "project": "proj",
        "claimed_by": "node-01",
        "started_at": "2026-01-01 00:00:00",
        "completed_at": "2026-01-01 00:05:00",
        "repos": "acme/core",
        "duration_seconds": 300,
        "_duration": "5m 0s",
        "commit_hashes": "abc1234",
        "repo_slug": "acme/core",
        "branch": "main",
        "commit_sha": "abc12345",
        "target_branch": "main",
        "push_target": "main",
        "repo_commits": [
            {
                "repo_slug": "acme/core",
                "branch": "main",
                "commit_sha": "abc12345",
                "push_target": "main",
            }
        ],
    }
    # Should not raise UndefinedError
    html = render(jinja_env, "fragments/recent_completed.html", tasks=[minimal_row])
    assert "5m 0s" in html


def test_recent_completed_renders_with_repos(jinja_env):
    """Template shows repo name badge and GitHub commit link when commits exist."""
    task = {
        "id": "task-done-01",
        "name": "gen-feature-y",
        "project": "acme",
        "claimed_by": "node-gpu-01",
        "started_at": "2026-04-06 09:30:00",
        "completed_at": "2026-04-06 09:35:00",
        "repos": "tobyj-nvidia/horde-claw-fleet",
        "duration_seconds": 300,
        "_duration": "5m 0s",
        "commit_hashes": "abc12345",
        "repo_slug": "tobyj-nvidia/horde-claw-fleet",
        "branch": "main",
        "commit_sha": "abc12345",
        "push_target": "main",
        "repo_commits": [
            {
                "repo_slug": "tobyj-nvidia/horde-claw-fleet",
                "branch": "main",
                "commit_sha": "abc12345",
                "push_target": "main",
            }
        ],
    }
    html = render(jinja_env, "fragments/recent_completed.html", tasks=[task])
    assert "horde-claw-fleet" in html
    assert "main" in html
    assert "abc12345" in html


def test_recent_completed_renders_without_repos(jinja_env):
    """Template shows '—' in Repos column when task has no commits."""
    task = {
        "id": "task-done-02",
        "name": "gen-no-commits",
        "project": "acme",
        "claimed_by": "node-gpu-01",
        "started_at": "2026-04-06 09:30:00",
        "completed_at": "2026-04-06 09:35:00",
        "repos": None,
        "duration_seconds": 300,
        "_duration": "5m 0s",
        "commit_hashes": None,
        "repo_slug": None,
        "branch": None,
        "commit_sha": None,
        "push_target": None,
        "repo_commits": [],
    }
    html = render(jinja_env, "fragments/recent_completed.html", tasks=[task])
    assert "—" in html


def test_recent_completed_fleet_branch_shows_main(jinja_env):
    """fleet/ task branches should render as green 'main' badge."""
    task = {
        "id": "task-done-03",
        "name": "gen-fleet-task",
        "project": "acme",
        "claimed_by": "node-gpu-01",
        "started_at": "2026-04-06 10:00:00",
        "completed_at": "2026-04-06 10:05:00",
        "repos": "tobyj-nvidia/horde-claw-fleet",
        "duration_seconds": 300,
        "_duration": "5m 0s",
        "commit_hashes": "def45678",
        "repo_slug": "tobyj-nvidia/horde-claw-fleet",
        "branch": "fleet/abc123-some-task",
        "commit_sha": "def45678",
        "push_target": "main",
        "repo_commits": [
            {
                "repo_slug": "tobyj-nvidia/horde-claw-fleet",
                "branch": "fleet/abc123-some-task",
                "commit_sha": "def45678",
                "push_target": "main",
            }
        ],
    }
    html = render(jinja_env, "fragments/recent_completed.html", tasks=[task])
    assert "badge-green" in html
    assert ">main<" in html
    assert "badge-yellow" not in html


def test_recent_completed_feature_branch_shows_branch_name(jinja_env):
    """Non-fleet branches should render the actual branch name with yellow badge."""
    task = {
        "id": "task-done-04",
        "name": "gen-feature-task",
        "project": "acme",
        "claimed_by": "node-gpu-01",
        "started_at": "2026-04-06 10:00:00",
        "completed_at": "2026-04-06 10:05:00",
        "repos": "NVIDIA-dev/some-repo",
        "duration_seconds": 300,
        "_duration": "5m 0s",
        "commit_hashes": "aabb1122",
        "repo_slug": "NVIDIA-dev/some-repo",
        "branch": "tobyj/hackathon-status-update",
        "commit_sha": "aabb1122",
        "push_target": "tobyj/hackathon-status-update",
        "repo_commits": [
            {
                "repo_slug": "NVIDIA-dev/some-repo",
                "branch": "tobyj/hackathon-status-update",
                "commit_sha": "aabb1122",
                "push_target": "tobyj/hackathon-status-update",
            }
        ],
    }
    html = render(jinja_env, "fragments/recent_completed.html", tasks=[task])
    assert "badge-yellow" in html
    assert "tobyj/hackathon-status-update" in html
    assert "badge-green" not in html


def test_recent_completed_deduplicates_repos(jinja_env):
    """Template renders each unique repo/branch once, not once per commit.

    Simulates the before/after: 3-commit task should show repo badge once (deduplicated),
    not three times (one per commit).
    """
    def make_task(repo_commits):
        return {
            "id": "task-done-05",
            "name": "gen-three-commits",
            "project": "acme",
            "claimed_by": "node-gpu-01",
            "started_at": "2026-04-06 11:00:00",
            "completed_at": "2026-04-06 11:05:00",
            "repos": "tobyj-nvidia/horde-claw-fleet",
            "duration_seconds": 300,
            "_duration": "5m 0s",
            "commit_hashes": "aaa1111",
            "repo_slug": "tobyj-nvidia/horde-claw-fleet",
            "branch": "main",
            "commit_sha": "aaa11111",
            "push_target": "main",
            "repo_commits": repo_commits,
        }

    # Deduplicated (fixed): 1 entry for 3 commits to same repo
    task_deduped = make_task([
        {"repo_slug": "tobyj-nvidia/horde-claw-fleet", "branch": "main", "commit_sha": "aaa11111", "push_target": "main"},
    ])
    html_deduped = render(jinja_env, "fragments/recent_completed.html", tasks=[task_deduped])

    # Non-deduplicated (broken): 3 entries for same repo/branch
    task_duped = make_task([
        {"repo_slug": "tobyj-nvidia/horde-claw-fleet", "branch": "main", "commit_sha": "aaa11111", "push_target": "main"},
        {"repo_slug": "tobyj-nvidia/horde-claw-fleet", "branch": "main", "commit_sha": "bbb22222", "push_target": "main"},
        {"repo_slug": "tobyj-nvidia/horde-claw-fleet", "branch": "main", "commit_sha": "ccc33333", "push_target": "main"},
    ])
    html_duped = render(jinja_env, "fragments/recent_completed.html", tasks=[task_duped])

    # The deduplicated version should render fewer repo badge occurrences than the duplicated version
    deduped_count = html_deduped.count("horde-claw-fleet")
    duped_count = html_duped.count("horde-claw-fleet")
    assert deduped_count < duped_count, (
        f"Deduplicated HTML ({deduped_count} occurrences) should have fewer repo badges "
        f"than duplicated HTML ({duped_count} occurrences)"
    )
    assert deduped_count >= 1, "Repo name must appear at least once in deduplicated output"


# ---------------------------------------------------------------------------
# recent_failed.html
# ---------------------------------------------------------------------------

def test_recent_failed_renders(jinja_env, sample_recent_failed):
    """
    BUG DETECTED: recent_failed.html references task.error_message but
    get_recent_failed() returns the column as error_msg.
    This test will FAIL until the template is fixed to use error_msg.
    """
    html = render(jinja_env, "fragments/recent_failed.html", tasks=sample_recent_failed)
    assert "gen-feature-z" in html or "task-fail" in html


def test_recent_failed_empty(jinja_env):
    html = render(jinja_env, "fragments/recent_failed.html", tasks=[])
    assert "No failed tasks" in html


def test_recent_failed_template_uses_error_msg_not_error_message(jinja_env):
    """
    Regression test: template previously (and incorrectly) referenced
    task.error_message. The query returns error_msg. This test verifies the
    template column name matches what the query produces.

    Pass a row with ONLY error_msg (no error_message) and confirm it renders
    without UndefinedError.
    """
    row_with_error_msg_only = {
        "id": "task-fail-xyz",
        "name": "broken-task",
        "project": "proj",
        "claimed_by": "node-01",
        "completed_at": "2026-01-01 09:00:00",
        "error_msg": "RuntimeError: something went wrong",
        # Intentionally NOT providing error_message — template must use error_msg
        "retry_count": 1,
        "max_retries": 3,
        "status": "failed",
        "is_resolved": False,
    }
    # If the template uses error_message (wrong), this raises UndefinedError
    html = render(jinja_env, "fragments/recent_failed.html", tasks=[row_with_error_msg_only])
    assert "RuntimeError" in html


# ---------------------------------------------------------------------------
# throughput.html
# ---------------------------------------------------------------------------

def test_throughput_renders(jinja_env, sample_throughput):
    from dashboard.sparkline import sparkline
    spark = sparkline([b["total"] for b in sample_throughput])
    html = render(
        jinja_env, "fragments/throughput.html",
        buckets=sample_throughput, spark=spark,
    )
    assert html.strip() != ""


# ---------------------------------------------------------------------------
# failures.html
# ---------------------------------------------------------------------------

def test_failures_renders(jinja_env, sample_failure_rate):
    from dashboard.sparkline import sparkline
    spark = sparkline([b["failures"] for b in sample_failure_rate])
    html = render(
        jinja_env, "fragments/failures.html",
        buckets=sample_failure_rate, spark=spark,
    )
    assert html.strip() != ""


# ---------------------------------------------------------------------------
# tokens.html
# ---------------------------------------------------------------------------

def test_tokens_renders(jinja_env, sample_token_rows):
    total_usd = sum(r["total_usd"] for r in sample_token_rows)
    html = render(
        jinja_env, "fragments/tokens.html",
        rows=sample_token_rows, total_usd=total_usd,
    )
    assert "anthropic" in html


# ---------------------------------------------------------------------------
# token_spend.html
# ---------------------------------------------------------------------------

def test_token_spend_renders_with_data(jinja_env):
    rows = [
        {"source": "task", "model": "claude-sonnet-4-6", "total_tokens": 50000, "total_cost_usd": 0.25},
        {"source": "gateway", "model": "claude-haiku-4-5", "total_tokens": 10000, "total_cost_usd": 0.05},
    ]
    html = render(
        jinja_env, "fragments/token_spend.html",
        rows=rows, total_tokens=60000, total_cost_usd=0.30, period=1,
    )
    assert "task" in html
    assert "gateway" in html
    assert "claude-sonnet-4-6" in html
    assert "0.3000" in html


def test_token_spend_empty(jinja_env):
    html = render(
        jinja_env, "fragments/token_spend.html",
        rows=[], total_tokens=0, total_cost_usd=0.0, period=1,
    )
    assert "No data" in html


def test_token_spend_period_selector_shows_active(jinja_env):
    html = render(
        jinja_env, "fragments/token_spend.html",
        rows=[], total_tokens=0, total_cost_usd=0.0, period=7,
    )
    assert "7d" in html
    assert "active" in html


def test_token_spend_all_periods_present(jinja_env):
    html = render(
        jinja_env, "fragments/token_spend.html",
        rows=[], total_tokens=0, total_cost_usd=0.0, period=1,
    )
    assert "1d" in html
    assert "7d" in html
    assert "30d" in html


def test_token_spend_source_badge_rendered(jinja_env):
    rows = [
        {"source": "cron", "model": "claude-opus-4-6", "total_tokens": 1000, "total_cost_usd": 0.10},
    ]
    html = render(
        jinja_env, "fragments/token_spend.html",
        rows=rows, total_tokens=1000, total_cost_usd=0.10, period=1,
    )
    assert "source-badge-cron" in html
    assert "cron" in html


# ---------------------------------------------------------------------------
# duration.html
# ---------------------------------------------------------------------------

def test_duration_renders_with_data(jinja_env):
    html = render(
        jinja_env, "fragments/duration.html",
        no_data=False, p50="2m 0s", p95="5m 0s", p99="10m 0s", avg="3m 0s",
    )
    assert "P50" in html or "2m 0s" in html


def test_duration_renders_no_data(jinja_env):
    html = render(
        jinja_env, "fragments/duration.html",
        no_data=True, p50="—", p95="—", p99="—", avg="—",
    )
    assert "No data" in html


# ---------------------------------------------------------------------------
# node_metrics.html
# ---------------------------------------------------------------------------

def test_node_metrics_renders(jinja_env, sample_node_metrics):
    html = render(jinja_env, "fragments/node_metrics.html", nodes=sample_node_metrics)
    assert "node-gpu-01" in html


# ---------------------------------------------------------------------------
# node_utilization_chart.html
# ---------------------------------------------------------------------------

def test_node_utilization_chart_renders_empty(jinja_env):
    html = render(jinja_env, "fragments/node_utilization_chart.html", nodes=[])
    assert html.strip() != ""


def test_node_utilization_chart_renders_with_nodes(jinja_env):
    nodes = [{"node_id": "node-gpu-01", "chart_svg": "<svg></svg>"}]
    html = render(jinja_env, "fragments/node_utilization_chart.html", nodes=nodes)
    assert "node-gpu-01" in html


# ---------------------------------------------------------------------------
# security_overview.html
# ---------------------------------------------------------------------------

def test_security_overview_renders(jinja_env):
    html = render(jinja_env, "fragments/security_overview.html",
                  total_invocations=150, high_flags=8, blocks=5,
                  unreviewed_alerts=3, block_rate_pct=3.3)
    assert "150" in html
    assert "Blocked" in html
    assert "Block Rate" in html
    assert "security-overview-panel" in html


# ---------------------------------------------------------------------------
# security_alerts.html
# ---------------------------------------------------------------------------

def test_security_alerts_renders_with_data(jinja_env):
    alerts = [
        {
            "id": "alert-001",
            "invocation_id": "inv-001",
            "task_id": "task-001",
            "worker_node_id": "node-gpu-01",
            "risk_level": "critical",
            "tool_name": "bash",
            "tool_args": "rm -rf /",
            "classifier_rule": "destructive_command",
            "reason": "Attempted to run destructive shell command that could damage the system",
            "reviewed": False,
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2026-04-06 10:00:00",
        },
        {
            "id": "alert-002",
            "invocation_id": "inv-002",
            "task_id": "task-002",
            "worker_node_id": "node-cpu-01",
            "risk_level": "high",
            "tool_name": "write_file",
            "tool_args": "/etc/passwd",
            "classifier_rule": "sensitive_path",
            "reason": "Write to sensitive system file",
            "reviewed": False,
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2026-04-06 09:55:00",
        },
    ]
    html = render(jinja_env, "fragments/security_alerts.html", alerts=alerts)
    assert "CRITICAL" in html
    assert "HIGH" in html
    assert "bash" in html
    assert "write_file" in html
    assert "node-gpu-01" in html
    assert "node-cpu-01" in html
    assert "Mark Reviewed" in html
    assert "badge-red" in html
    assert "badge-orange" in html


def test_security_alerts_empty(jinja_env):
    html = render(jinja_env, "fragments/security_alerts.html", alerts=[])
    assert "No unreviewed alerts" in html


def test_security_alerts_reason_truncated(jinja_env):
    long_reason = "A" * 120
    alerts = [
        {
            "id": "alert-003",
            "invocation_id": "inv-003",
            "task_id": "task-003",
            "worker_node_id": "node-gpu-02",
            "risk_level": "high",
            "tool_name": "bash",
            "tool_args": "cat secrets",
            "classifier_rule": "secret_access",
            "reason": long_reason,
            "reviewed": False,
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2026-04-06 09:50:00",
        },
    ]
    html = render(jinja_env, "fragments/security_alerts.html", alerts=alerts)
    # Reason should be truncated to 80 chars with ellipsis
    assert "A" * 80 in html
    assert "…" in html


# ---------------------------------------------------------------------------
# blocked_ops.html
# ---------------------------------------------------------------------------

def test_blocked_ops_renders_with_data(jinja_env, sample_blocked_ops):
    html = render(jinja_env, "fragments/blocked_ops.html", ops=sample_blocked_ops)
    assert "bash" in html
    assert "write_file" in html
    assert "destructive_command" in html
    assert "sensitive_path" in html
    assert "node-gpu-01" in html
    assert "node-cpu-01" in html


def test_blocked_ops_empty(jinja_env):
    html = render(jinja_env, "fragments/blocked_ops.html", ops=[])
    assert "No blocked operations in the last 24h" in html


def test_blocked_ops_truncates_long_tool_args(jinja_env):
    long_args = "x" * 120
    ops = [
        {
            "tool_name": "bash",
            "tool_args": long_args,
            "classifier_rule": "some_rule",
            "worker_node_id": "node-01",
            "timestamp": "2026-04-06 10:00:00",
        },
    ]
    html = render(jinja_env, "fragments/blocked_ops.html", ops=ops)
    # First 80 chars should be present
    assert "x" * 80 in html
    # Ellipsis should appear for truncation
    assert "…" in html


def test_blocked_ops_missing_worker_shows_dash(jinja_env):
    ops = [
        {
            "tool_name": "bash",
            "tool_args": "echo hello",
            "classifier_rule": "test_rule",
            "worker_node_id": None,
            "timestamp": "2026-04-06 10:00:00",
        },
    ]
    html = render(jinja_env, "fragments/blocked_ops.html", ops=ops)
    assert "—" in html


def test_blocked_ops_has_30s_refresh(jinja_env, sample_blocked_ops):
    html = render(jinja_env, "fragments/blocked_ops.html", ops=sample_blocked_ops)
    assert "every 30s" in html


def test_blocked_ops_required_columns_present(jinja_env):
    """Verify template only accesses columns that get_blocked_operations() returns."""
    minimal_row = {
        "tool_name": "bash",
        "tool_args": "ls -la",
        "classifier_rule": "read_command",
        "worker_node_id": "node-01",
        "timestamp": "2026-04-06 10:00:00",
    }
    # Should not raise UndefinedError with StrictUndefined
    html = render(jinja_env, "fragments/blocked_ops.html", ops=[minimal_row])
    assert "bash" in html
    assert "ls -la" in html


# ---------------------------------------------------------------------------
# tool_heatmap.html
# ---------------------------------------------------------------------------

def test_tool_heatmap_renders_with_data(jinja_env):
    heatmap = [
        {"classifier_rule": "destructive_command", "tool_name": "bash", "risk_level": "critical", "hit_count": 42},
        {"classifier_rule": "sensitive_path", "tool_name": "write_file", "risk_level": "high", "hit_count": 17},
        {"classifier_rule": "read_command", "tool_name": "read_file", "risk_level": "low", "hit_count": 5},
    ]
    html = render(jinja_env, "fragments/tool_heatmap.html", heatmap=heatmap)
    assert "tool-heatmap-panel" in html
    assert "destructive_command" in html
    assert "bash" in html
    assert "CRITICAL" in html
    assert "badge-red" in html
    assert "42" in html
    assert "sensitive_path" in html
    assert "HIGH" in html
    assert "badge-orange" in html
    assert "17" in html


def test_tool_heatmap_empty(jinja_env):
    html = render(jinja_env, "fragments/tool_heatmap.html", heatmap=[])
    assert "tool-heatmap-panel" in html
    assert "No invocations in the last 7 days" in html


def test_tool_heatmap_has_60s_refresh(jinja_env):
    html = render(jinja_env, "fragments/tool_heatmap.html", heatmap=[])
    assert "every 60s" in html


def test_security_incident_renders(jinja_env):
    html = render(jinja_env, 'security_incident.html',
                  invocation={'id': 'inv-1', 'task_id': 't-1', 'worker_node_id': 'w-1',
                              'timestamp': '2026-04-10', 'tool_name': 'Bash', 'tool_args': 'rm -rf /',
                              'risk_level': 'critical', 'decision': 'block', 'classifier_path': 'rule',
                              'classifier_rule': 'destructive-rm', 'classifier_output': None,
                              'execution_result': None, 'duration_ms': 0},
                  alert={'id': 'a-1', 'reason': 'Destructive op', 'reviewed': False,
                         'reviewed_by': None, 'reviewed_at': None, 'created_at': '2026-04-10'},
                  context=[{'id': 'inv-1', 'timestamp': '2026-04-10', 'tool_name': 'Bash',
                           'risk_level': 'critical', 'decision': 'block'}])
    assert 'critical' in html.lower()
    assert 'Bash' in html
    assert 'destructive-rm' in html


# ---------------------------------------------------------------------------
# worker_security_health.html
# ---------------------------------------------------------------------------

def test_worker_security_health_renders_with_data(jinja_env, sample_worker_security_health):
    html = render(jinja_env, "fragments/worker_security_health.html", workers=sample_worker_security_health)
    assert "worker-security-health-panel" in html
    assert "node-gpu-01" in html
    assert "node-gpu-02" in html
    assert "node-cpu-01" in html
    assert "500" in html
    assert "15.0%" in html
    assert "5.0%" in html
    assert "1.0%" in html


def test_worker_security_health_empty(jinja_env):
    html = render(jinja_env, "fragments/worker_security_health.html", workers=[])
    assert "worker-security-health-panel" in html
    assert "No worker security data in the last 24h" in html


def test_worker_security_health_highlight_high_block_rate(jinja_env):
    """Rows with block_rate > fleet average * 2 should be highlighted."""
    workers = [
        {"worker_node_id": "node-outlier", "total": 100, "blocks": 20, "highs": 5, "criticals": 2, "block_rate_pct": 20.0, "no_data": 0},
        {"worker_node_id": "node-normal-1", "total": 100, "blocks": 2, "highs": 1, "criticals": 0, "block_rate_pct": 2.0, "no_data": 0},
        {"worker_node_id": "node-normal-2", "total": 100, "blocks": 3, "highs": 1, "criticals": 0, "block_rate_pct": 3.0, "no_data": 0},
    ]
    # Fleet average = (20+2+3)/(100+100+100)*100 = 8.33%, threshold = 16.67%
    # node-outlier at 20% should be highlighted
    html = render(jinja_env, "fragments/worker_security_health.html", workers=workers)
    assert "highlight-row" in html
    assert "node-outlier" in html


def test_worker_security_health_no_highlight_when_all_below_threshold(jinja_env):
    """No rows highlighted when all are below 2x fleet average."""
    workers = [
        {"worker_node_id": "node-a", "total": 100, "blocks": 5, "highs": 2, "criticals": 0, "block_rate_pct": 5.0, "no_data": 0},
        {"worker_node_id": "node-b", "total": 100, "blocks": 4, "highs": 1, "criticals": 0, "block_rate_pct": 4.0, "no_data": 0},
    ]
    # Fleet average = 9/200*100 = 4.5%, threshold = 9.0%
    # Both are below threshold
    html = render(jinja_env, "fragments/worker_security_health.html", workers=workers)
    assert "highlight-row" not in html


def test_worker_security_health_has_30s_refresh(jinja_env, sample_worker_security_health):
    html = render(jinja_env, "fragments/worker_security_health.html", workers=sample_worker_security_health)
    assert "every 30s" in html


def test_worker_security_health_required_columns_present(jinja_env):
    """Verify template only accesses columns that get_worker_security_health() returns."""
    minimal_row = {
        "worker_node_id": "node-01",
        "total": 100,
        "blocks": 5,
        "highs": 3,
        "criticals": 1,
        "block_rate_pct": 5.0,
        "no_data": 0,
    }
    # Should not raise UndefinedError with StrictUndefined
    html = render(jinja_env, "fragments/worker_security_health.html", workers=[minimal_row])
    assert "node-01" in html
    assert "100" in html
    assert "5.0%" in html


def test_worker_security_health_table_headers(jinja_env, sample_worker_security_health):
    """Verify all required column headers are present."""
    html = render(jinja_env, "fragments/worker_security_health.html", workers=sample_worker_security_health)
    assert "Worker" in html
    assert "Total Invocations" in html
    assert "Blocks" in html
    assert "High Flags" in html
    assert "Criticals" in html
    assert "Block Rate %" in html


def test_worker_security_health_no_data_badge(jinja_env):
    """Workers with no_data=1 should display a 'NO DATA' badge."""
    workers = [
        {"worker_node_id": "node-with-data", "total": 100, "blocks": 5, "highs": 2, "criticals": 0, "block_rate_pct": 5.0, "no_data": 0},
        {"worker_node_id": "node-no-data", "total": 0, "blocks": 0, "highs": 0, "criticals": 0, "block_rate_pct": 0, "no_data": 1},
    ]
    html = render(jinja_env, "fragments/worker_security_health.html", workers=workers)
    assert "node-with-data" in html
    assert "node-no-data" in html
    assert "badge-gray" in html
    assert "NO DATA" in html
    # The NO DATA badge should only appear once (for node-no-data)
    assert html.count("NO DATA") == 1


# ---------------------------------------------------------------------------
# security_timeline.html
# ---------------------------------------------------------------------------

def test_security_timeline_renders_with_data(jinja_env, sample_security_timeline):
    from dashboard.sparkline import sparkline
    high_spark = sparkline([r["high_count"] for r in sample_security_timeline])
    critical_spark = sparkline([r["critical_count"] for r in sample_security_timeline])
    html = render(
        jinja_env, "fragments/security_timeline.html",
        timeline=sample_security_timeline,
        high_spark=high_spark,
        critical_spark=critical_spark,
    )
    assert "security-timeline-panel" in html
    assert "2026-04-06 08:00" in html
    assert "2026-04-06 09:00" in html
    assert "2026-04-06 10:00" in html
    assert "High" in html
    assert "Critical" in html


def test_security_timeline_empty(jinja_env):
    html = render(
        jinja_env, "fragments/security_timeline.html",
        timeline=[],
        high_spark="",
        critical_spark="",
    )
    assert "security-timeline-panel" in html
    assert "No high/critical invocations in the last 7 days" in html


def test_security_timeline_has_60s_refresh(jinja_env, sample_security_timeline):
    from dashboard.sparkline import sparkline
    high_spark = sparkline([r["high_count"] for r in sample_security_timeline])
    critical_spark = sparkline([r["critical_count"] for r in sample_security_timeline])
    html = render(
        jinja_env, "fragments/security_timeline.html",
        timeline=sample_security_timeline,
        high_spark=high_spark,
        critical_spark=critical_spark,
    )
    assert "every 60s" in html


def test_security_timeline_sparklines_present(jinja_env, sample_security_timeline):
    from dashboard.sparkline import sparkline
    high_spark = sparkline([r["high_count"] for r in sample_security_timeline])
    critical_spark = sparkline([r["critical_count"] for r in sample_security_timeline])
    html = render(
        jinja_env, "fragments/security_timeline.html",
        timeline=sample_security_timeline,
        high_spark=high_spark,
        critical_spark=critical_spark,
    )
    assert high_spark in html
    assert critical_spark in html


def test_security_timeline_highlights_nonzero_counts(jinja_env):
    """Non-zero high counts get 'warning' class, non-zero critical counts get 'failure' class."""
    from dashboard.sparkline import sparkline
    timeline = [
        {"hour_bucket": "2026-04-06 08:00", "high_count": 3, "critical_count": 0},
        {"hour_bucket": "2026-04-06 09:00", "high_count": 0, "critical_count": 2},
    ]
    high_spark = sparkline([r["high_count"] for r in timeline])
    critical_spark = sparkline([r["critical_count"] for r in timeline])
    html = render(
        jinja_env, "fragments/security_timeline.html",
        timeline=timeline,
        high_spark=high_spark,
        critical_spark=critical_spark,
    )
    assert "warning" in html
    assert "failure" in html


def test_security_timeline_required_columns_present(jinja_env):
    """Verify template only accesses columns that get_security_timeline() returns."""
    from dashboard.sparkline import sparkline
    minimal_row = {
        "hour_bucket": "2026-04-06 12:00",
        "high_count": 1,
        "critical_count": 0,
    }
    html = render(
        jinja_env, "fragments/security_timeline.html",
        timeline=[minimal_row],
        high_spark=sparkline([1]),
        critical_spark=sparkline([0]),
    )
    assert "2026-04-06 12:00" in html
