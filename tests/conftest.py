"""Pytest fixtures for horde-fleet-dashboard tests.

Provides two modes:
  1. WITH a real Dolt database (hub) — full integration tests
  2. WITHOUT a database (workers) — mocked DB, route + template tests still run

Detection is automatic: if the DB is unreachable, fixtures switch to mocks.
"""

import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import aiomysql
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Database availability detection
# ---------------------------------------------------------------------------

DB_CONFIG = dict(
    host=os.environ.get("DOLT_HOST", "127.0.0.1"),
    port=int(os.environ.get("DOLT_PORT", "3306")),
    db=os.environ.get("DOLT_DB", "dolt-tasks"),
    user=os.environ.get("DOLT_USER", "root"),
    password=os.environ.get("DOLT_PASSWORD", ""),
    autocommit=True,
)

_db_available: bool | None = None


def _check_db_available() -> bool:
    """Synchronous check: can we connect to Dolt?"""
    global _db_available
    if _db_available is not None:
        return _db_available
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect((DB_CONFIG["host"], DB_CONFIG["port"]))
        _db_available = True
    except (ConnectionRefusedError, OSError, socket.timeout):
        _db_available = False
    finally:
        sock.close()
    return _db_available


requires_db = pytest.mark.skipif(
    not _check_db_available(),
    reason="Dolt database not reachable"
)


# ---------------------------------------------------------------------------
# Mock DB classes (used when Dolt is unavailable)
# ---------------------------------------------------------------------------

# Maps SQL pattern substrings to (fetchall_rows, fetchone_row) tuples.
# Populated by mock data sections below.
_MOCK_QUERY_MAP: dict[str, tuple[list[dict], dict | None]] = {
    'select status, count': (
        [
            {'status': 'pending', 'cnt': 5},
            {'status': 'running', 'cnt': 2},
            {'status': 'completed', 'cnt': 100},
            {'status': 'failed', 'cnt': 10},
            {'status': 'dead-letter', 'cnt': 3},
        ],
        None,
    ),
    'is_resolved': (
        [
            {
                'id': 'task-mock-failed-001',
                'name': 'gen-feature-z',
                'project': 'acme',
                'claimed_by': 'node-gpu-01',
                'completed_at': '2026-04-06 09:10:00',
                'error_msg': 'RuntimeError: segfault',
                'retry_count': 1,
                'max_retries': 3,
                'status': 'failed',
                'is_resolved': False,
            }
        ],
        None,
    ),
    'where t.status in': (
        [
            {
                'id': 'task-mock-active-001',
                'name': 'mock-active-task',
                'type': 'code-gen',
                'project': 'acme',
                'status': 'running',
                'claimed_by': 'node-gpu-01',
                'started_at': '2026-04-06 10:00:00',
                'retry_count': 0,
                'resource_class': 'gpu',
                'running_sec': 120,
                'is_blocked': False,
            }
        ],
        None,
    ),
    'order by t.priority': (
        [
            {
                'id': 'task-mock-pending-001',
                'name': 'pending-task',
                'project': 'acme',
                'priority': 30,
                'submitted_at': '2026-04-06 09:00:00',
                'status': 'pending',
                'queue_seconds': 3600,
                'is_blocked': False,
            }
        ],
        None,
    ),
    'from nodes': ([{
        'node_id': 'node-gpu-01',
        'status': 'active',
        'capabilities': 'gpu',
        'active_tasks': 1,
        'max_concurrent': 4,
        'gpu_capacity': 1,
        'last_heartbeat': '2026-04-06 10:01:00',
        'deployed_version': 'a1b2c3d4e5f6',
        'heartbeat_age_sec': 30,
    }], None),
    'left join task_results tr on t.id': ([{
        'id': 'task-mock-dead-001',
        'type': 'code-gen',
        'project': 'acme',
        'status': 'dead-letter',
        'retry_count': 3,
        'submitted_at': '2026-04-06 09:00:00',
        'prompt_snippet': 'Generate a unit test for...',
        'error_msg': 'TimeoutError: model call timed out',
        'completed_at': '2026-04-06 09:05:00',
        'failure_age_sec': 3600,
    }], None),
    'outcome !=': (
        [
            {'date': '2026-04-01', 'total': 10, 'failures': 2, 'failure_pct': 20.0},
            {'date': '2026-04-02', 'total': 15, 'failures': 1, 'failure_pct': 6.67},
        ],
        None,
    ),
    'group by date(completed_at)': (
        [
            {'date': '2026-04-01', 'total': 10, 'success': 8, 'failure': 2, 'dead_letter': 0},
            {'date': '2026-04-02', 'total': 15, 'success': 14, 'failure': 1, 'dead_letter': 0},
        ],
        None,
    ),
    'percent_rank': (
        [],
        {'p50_sec': 120, 'p95_sec': 300, 'p99_sec': 600, 'avg_sec': 150},
    ),
    'total_cost_usd': ([{
        'source': 'anthropic',
        'model': 'claude-sonnet-4-6',
        'total_tokens': 100000,
        'total_cost_usd': 0.50,
    }], None),
    'total_usd': ([{
        'provider': 'anthropic',
        'model': 'claude-sonnet-4-6',
        'total_tokens': 100000,
        'total_usd': 0.50,
    }], None),
    'from tool_invocations\nwhere': (
        [],
        {'total_invocations': 150, 'high_flags': 8, 'blocks': 5},
    ),
    "decision = %s": (
        [
            {
                'tool_name': 'bash',
                'tool_args': 'rm -rf / --no-preserve-root',
                'classifier_rule': 'destructive_command',
                'worker_node_id': 'node-gpu-01',
                'timestamp': '2026-04-06 10:05:00',
            },
            {
                'tool_name': 'write_file',
                'tool_args': '/etc/shadow with malicious content that is very long and should be truncated in the UI display',
                'classifier_rule': 'sensitive_path',
                'worker_node_id': 'node-cpu-01',
                'timestamp': '2026-04-06 09:55:00',
            },
        ],
        None,
    ),
    'from security_alerts where reviewed': (
        [],
        {'unreviewed_alerts': 3},
    ),
    'classifier_rule is not null': (
        [
            {'classifier_rule': 'destructive_command', 'tool_name': 'bash', 'risk_level': 'critical', 'hit_count': 42},
            {'classifier_rule': 'sensitive_path', 'tool_name': 'write_file', 'risk_level': 'high', 'hit_count': 17},
        ],
        None,
    ),
    'from audit_sessions': (
        [
            {'worker_node_id': 'node-gpu-01', 'total': 500, 'blocks': 25, 'highs': 10, 'criticals': 3, 'block_rate_pct': 5.0},
            {'worker_node_id': 'node-cpu-01', 'total': 300, 'blocks': 3, 'highs': 2, 'criticals': 0, 'block_rate_pct': 1.0},
            {'worker_node_id': 'node-gpu-02', 'total': 200, 'blocks': 30, 'highs': 15, 'criticals': 5, 'block_rate_pct': 15.0},
        ],
        None,
    ),
    'select count': ([], {'cnt': 1}),
    'select * from tasks': ([{
        'id': 'task-mock-001',
        'type': 'code-gen',
        'name': 'mock-task',
        'project': 'acme',
        'status': 'pending',
        'claimed_by': None,
        'started_at': None,
        'completed_at': None,
        'submitted_at': '2026-04-06 09:00:00',
        'prompt': 'Generate a test',
        'repos': 'acme/core',
        'retry_count': 0,
        'max_retries': 3,
        'resource_class': 'cpu',
        'priority': 30,
    }], None),
    'max(recorded_at) as max_recorded_at': ([{
        'node_id': 'node-gpu-01',
        'cpu_pct': 45.0,
        'mem_pct': 60.0,
        'mem_used_gb': 24.0,
        'mem_total_gb': 40.0,
        'gpu_pct': 80.0,
        'gpu_mem_pct': 70.0,
        'gpu_mem_used_gb': 16.0,
        'gpu_mem_total_gb': 24.0,
        'disk_pct': 30.0,
        'recorded_at': '2026-04-06 10:01:00',
    }], None),
    'interval 48 hour': ([{
        'node_id': 'node-gpu-01',
        'bucket': '2026-04-06 10:00:00',
        'cpu_pct': 45.0,
        'gpu_pct': 80.0,
    }], None),
    'floor(unix_timestamp': ([{
        'timestamp': '2026-04-06 10:00:00',
        'node_id': 'node-gpu-01',
        'cpu_pct': 45.0,
        'gpu_pct': 80.0,
        'gpu_mem_pct': 70.0,
        'mem_pct': 60.0,
        'disk_pct': 30.0,
    }], None),
    # MOCK-8: DESCRIBE responses for schema tests
    'describe `tasks`': ([
        {'Field': f} for f in [
            'id', 'type', 'name', 'project', 'status', 'claimed_by', 'started_at',
            'completed_at', 'submitted_at', 'prompt', 'repos', 'retry_count',
            'max_retries', 'resource_class', 'priority', 'claim_expires_at',
        ]
    ], None),
    'describe `task_results`': ([
        {'Field': f} for f in [
            'task_id', 'outcome', 'summary', 'error_msg', 'completed_at', 'duration_sec',
        ]
    ], None),
    'describe `task_commits`': ([
        {'Field': f} for f in ['task_id', 'repo_slug', 'branch', 'commit_sha', 'target_branch']
    ], None),
    'describe `task_dependencies`': ([
        {'Field': f} for f in ['task_id', 'depends_on']
    ], None),
    'describe `task_telemetry`': ([
        {'Field': f} for f in [
            'task_id', 'provider', 'source', 'model', 'input_tokens', 'output_tokens',
            'estimated_cost_usd', 'recorded_at',
        ]
    ], None),
    'describe `nodes`': ([
        {'Field': f} for f in [
            'id', 'status', 'capabilities', 'active_tasks', 'max_concurrent',
            'gpu_capacity', 'last_heartbeat', 'deployed_version',
        ]
    ], None),
    'describe `node_metrics`': ([
        {'Field': f} for f in [
            'node_id', 'cpu_pct', 'mem_pct', 'mem_used_gb', 'mem_total_gb',
            'gpu_pct', 'gpu_mem_pct', 'gpu_mem_used_gb', 'gpu_mem_total_gb',
            'disk_pct', 'recorded_at',
        ]
    ], None),
    'select distinct status': ([
        {'status': 'pending'},
        {'status': 'running'},
        {'status': 'completed'},
        {'status': 'failed'},
        {'status': 'dead-letter'},
    ], None),
    'group_concat': ([{
        'id': 'task-mock-done-001',
        'name': 'gen-feature-y',
        'project': 'acme',
        'claimed_by': 'node-gpu-01',
        'started_at': '2026-04-06 09:30:00',
        'completed_at': '2026-04-06 09:35:00',
        'repos': 'acme/core',
        'duration_seconds': 300,
        'commit_hashes': 'abc1234',
        'repo_slug': 'acme/core',
        'branch': 'fleet/abc1234-task',
        'commit_sha': 'abc12345',
        'target_branch': 'main',
    }], None),
}


class MockCursor:
    """Mock aiomysql.DictCursor that pattern-matches SQL and returns sample data."""

    def __init__(self):
        self._rows = []
        self._row = None

    async def execute(self, sql, args=None):
        sql_lower = sql.lower().strip()
        self._rows, self._row = self._match_sql(sql_lower, args)

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def _match_sql(self, sql, args):
        for key, value in _MOCK_QUERY_MAP.items():
            if key in sql:
                return value
        # Default: COUNT(*) queries return a single zero-row so fetchone() is not None
        if "count(*)" in sql:
            return [], {"cnt": 0, "count(*)": 0}
        return [], None


class MockConnection:
    def cursor(self, cursor_class=None):
        return MockCursor()

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _MockPoolAcquireCtx:
    async def __aenter__(self):
        return MockConnection()

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Database fixtures (real DB on hub, mock on workers)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def db_pool():
    """Session-scoped connection pool to the real Dolt database.

    Returns a MockPool when DB is unavailable so that schema tests still run
    using the DESCRIBE mock responses defined in _MOCK_QUERY_MAP.
    """
    if not _check_db_available():
        yield MockPool()
        return
    pool = await aiomysql.create_pool(minsize=1, maxsize=3, **DB_CONFIG)
    yield pool
    pool.close()
    await pool.wait_closed()


@pytest_asyncio.fixture
async def db_conn():
    """Per-test database connection. Yields MockConnection when DB unavailable
    so that tests exercising query logic still run on workers."""
    if not _check_db_available():
        yield MockConnection()
        return
    pool = await aiomysql.create_pool(minsize=1, maxsize=5, **DB_CONFIG)
    async with pool.acquire() as conn:
        yield conn
    pool.close()
    await pool.wait_closed()


# ---------------------------------------------------------------------------
# App / HTTP client fixtures (work with or without DB)
# ---------------------------------------------------------------------------

class MockPool:
    """Mock aiomysql pool that returns MockConnections."""

    def acquire(self):
        return _MockPoolAcquireCtx()

    def close(self):
        pass

    async def wait_closed(self):
        pass


def _make_mock_pool():
    """Create a mock pool using MockConnection/MockCursor classes."""
    return MockPool()


@pytest_asyncio.fixture(scope="session")
async def app():
    """Create the FastAPI app. Uses real DB on hub, mock on workers."""
    import dashboard.db as db_module
    from dashboard.main import app as _app

    if _check_db_available():
        _pool = await aiomysql.create_pool(minsize=1, maxsize=3, **DB_CONFIG)
        db_module._pool = _pool
        yield _app
        _pool.close()
        await _pool.wait_closed()
        db_module._pool = None
    else:
        mock_pool = _make_mock_pool()
        db_module._pool = mock_pool
        yield _app
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
        {"date": "2026-04-01", "total": 10, "success": 8, "failure": 2, "dead_letter": 0},
        {"date": "2026-04-02", "total": 15, "success": 14, "failure": 1, "dead_letter": 0},
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


@pytest.fixture
def sample_blocked_ops():
    return [
        {
            "tool_name": "bash",
            "tool_args": "rm -rf / --no-preserve-root",
            "classifier_rule": "destructive_command",
            "worker_node_id": "node-gpu-01",
            "timestamp": "2026-04-06 10:05:00",
        },
        {
            "tool_name": "write_file",
            "tool_args": "/etc/shadow with malicious content that is very long and should be truncated in the UI display",
            "classifier_rule": "sensitive_path",
            "worker_node_id": "node-cpu-01",
            "timestamp": "2026-04-06 09:55:00",
        },
    ]


@pytest.fixture
def sample_worker_security_health():
    return [
        {
            "worker_node_id": "node-gpu-02",
            "total": 200,
            "blocks": 30,
            "highs": 15,
            "criticals": 5,
            "block_rate_pct": 15.0,
        },
        {
            "worker_node_id": "node-gpu-01",
            "total": 500,
            "blocks": 25,
            "highs": 10,
            "criticals": 3,
            "block_rate_pct": 5.0,
        },
        {
            "worker_node_id": "node-cpu-01",
            "total": 300,
            "blocks": 3,
            "highs": 2,
            "criticals": 0,
            "block_rate_pct": 1.0,
        },
    ]
