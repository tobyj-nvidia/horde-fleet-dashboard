"""Pytest fixtures for horde-fleet-dashboard tests."""

import asyncio
import os
from typing import AsyncGenerator

import aiomysql
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

DB_CONFIG = dict(
    host=os.environ.get("DOLT_HOST", "127.0.0.1"),
    port=int(os.environ.get("DOLT_PORT", "3306")),
    db=os.environ.get("DOLT_DB", "dolt-tasks"),
    user=os.environ.get("DOLT_USER", "root"),
    password=os.environ.get("DOLT_PASSWORD", ""),
    autocommit=True,
)


@pytest_asyncio.fixture(scope="session")
async def db_pool():
    """Session-scoped connection pool to the real Dolt database."""
    pool = await aiomysql.create_pool(minsize=1, maxsize=3, **DB_CONFIG)
    yield pool
    pool.close()
    await pool.wait_closed()


@pytest_asyncio.fixture
async def db_conn(db_pool):
    """Per-test database connection acquired from the session pool."""
    async with db_pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# App / HTTP client fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def app():
    """Create the FastAPI app with a live DB pool."""
    import dashboard.db as db_module
    from dashboard.main import app as _app

    # Point the module pool at our test pool
    _pool = await aiomysql.create_pool(minsize=1, maxsize=3, **DB_CONFIG)
    db_module._pool = _pool

    yield _app

    _pool.close()
    await _pool.wait_closed()
    db_module._pool = None


@pytest_asyncio.fixture(scope="session")
async def client(app):
    """HTTPX async client backed by the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Sample data fixtures (used for template-rendering tests; no DB needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_tasks():
    return [
        {
            "id": "task-00000001-0000-0000-0000-000000000001",
            "type": "code-gen",
            "name": "gen-feature-x",
            "project": "acme",
            "status": "running",
            "claimed_by": "node-gpu-01",
            "started_at": "2026-04-06 10:00:00",
            "completed_at": None,
            "resource_class": "gpu",
            "retry_count": 0,
            "max_retries": 3,
            "running_sec": 120,
            "is_blocked": False,
            "_elapsed": "2m 0s",
        }
    ]


@pytest.fixture
def sample_nodes():
    return [
        {
            "node_id": "node-gpu-01",
            "status": "active",
            "capabilities": "gpu",
            "active_tasks": 1,
            "max_concurrent": 4,
            "gpu_capacity": 1,
            "last_heartbeat": "2026-04-06 10:01:00",
            "deployed_version": "a1b2c3d4",
            "heartbeat_age_sec": 30,
            "is_stale": False,
        }
    ]


@pytest.fixture
def sample_dead_letter():
    return [
        {
            "id": "task-dead-0000-0000-0000-000000000002",
            "type": "code-gen",
            "project": "acme",
            "status": "dead-letter",
            "retry_count": 3,
            "submitted_at": "2026-04-06 09:00:00",
            "prompt_snippet": "Generate a unit test for...",
            "error_msg": "TimeoutError: model call timed out",
            "completed_at": "2026-04-06 09:05:00",
            "failure_age_sec": 3600,
        }
    ]


@pytest.fixture
def sample_recent_completed():
    return [
        {
            "id": "task-done-0000-0000-0000-000000000003",
            "name": "gen-feature-y",
            "project": "acme",
            "claimed_by": "node-gpu-01",
            "started_at": "2026-04-06 09:30:00",
            "completed_at": "2026-04-06 09:35:00",
            "repos": "acme/core",
            "duration_seconds": 300,
            "_duration": "5m 0s",
            "commit_hashes": "abc1234,def5678",
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
    ]


@pytest.fixture
def sample_recent_failed():
    return [
        {
            "id": "task-fail-0000-0000-0000-000000000004",
            "name": "gen-feature-z",
            "project": "acme",
            "claimed_by": "node-gpu-01",
            "completed_at": "2026-04-06 09:10:00",
            "error_msg": "RuntimeError: segfault",
            "retry_count": 1,
            "max_retries": 3,
            "status": "failed",
            "is_resolved": False,
        }
    ]


@pytest.fixture
def sample_throughput():
    return [
        {"date": "2026-04-01", "total": 10, "success": 8, "failure": 2},
        {"date": "2026-04-02", "total": 15, "success": 14, "failure": 1},
    ]


@pytest.fixture
def sample_failure_rate():
    return [
        {"date": "2026-04-01", "total": 10, "failures": 2, "failure_pct": 20.0},
        {"date": "2026-04-02", "total": 15, "failures": 1, "failure_pct": 6.67},
    ]


@pytest.fixture
def sample_token_rows():
    return [
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "total_tokens": 100000,
            "total_usd": 0.50,
        }
    ]


@pytest.fixture
def sample_duration():
    return {"p50_sec": 120, "p95_sec": 300, "p99_sec": 600, "avg_sec": 150}


@pytest.fixture
def sample_node_metrics():
    return [
        {
            "node_id": "node-gpu-01",
            "cpu_pct": 45.0,
            "mem_pct": 60.0,
            "mem_used_gb": 24.0,
            "mem_total_gb": 40.0,
            "gpu_pct": 80.0,
            "gpu_mem_pct": 70.0,
            "gpu_mem_used_gb": 16.0,
            "gpu_mem_total_gb": 24.0,
            "disk_pct": 30.0,
            "recorded_at": "2026-04-06 10:01:00",
            "cpu_spark": "",
            "gpu_spark": "",
        }
    ]
