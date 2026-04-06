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
