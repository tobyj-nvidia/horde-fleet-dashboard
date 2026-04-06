"""
Route tests — hit every fragment endpoint with the test HTTP client and verify:
  1. HTTP 200 (not 500)
  2. Content-Type is text/html
  3. Response body contains expected structural markers

A 500 means a query failed or a template crashed. These tests catch both.
"""

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_ok(client, path: str) -> str:
    """GET path, assert 200, return response text."""
    response = await client.get(path)
    assert response.status_code == 200, (
        f"GET {path} returned {response.status_code}. "
        f"Body: {response.text[:500]}"
    )
    assert "text/html" in response.headers.get("content-type", ""), (
        f"GET {path} did not return HTML"
    )
    return response.text


# ---------------------------------------------------------------------------
# Fragment endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fragment_queue_counts(client):
    html = await _get_ok(client, "/fragments/queue-counts")
    assert "queue-counts" in html or "status-box" in html or "pending" in html


@pytest.mark.asyncio
async def test_fragment_active_tasks(client):
    html = await _get_ok(client, "/fragments/active-tasks")
    # Either a table of tasks or the empty-state message
    assert "active-tasks" in html or "active_tasks" in html or "No active tasks" in html


@pytest.mark.asyncio
async def test_fragment_nodes(client):
    html = await _get_ok(client, "/fragments/nodes")
    assert "Node ID" in html or "No nodes registered" in html


@pytest.mark.asyncio
async def test_fragment_dead_letter(client):
    html = await _get_ok(client, "/fragments/dead-letter")
    assert "Task ID" in html or "No dead-letter tasks" in html


@pytest.mark.asyncio
async def test_fragment_throughput(client):
    html = await _get_ok(client, "/fragments/throughput")
    # Contains sparkline SVG or empty state
    assert html.strip() != ""


@pytest.mark.asyncio
async def test_fragment_tokens(client):
    html = await _get_ok(client, "/fragments/tokens")
    assert html.strip() != ""


@pytest.mark.asyncio
async def test_fragment_failures(client):
    html = await _get_ok(client, "/fragments/failures")
    assert html.strip() != ""


@pytest.mark.asyncio
async def test_fragment_node_metrics(client):
    html = await _get_ok(client, "/fragments/node-metrics")
    assert html.strip() != ""


@pytest.mark.asyncio
async def test_fragment_node_utilization_chart(client):
    html = await _get_ok(client, "/fragments/node-utilization-chart")
    assert html.strip() != ""


@pytest.mark.asyncio
async def test_fragment_recent_completed(client):
    html = await _get_ok(client, "/fragments/recent-completed")
    assert "Name" in html or "No completed tasks" in html


@pytest.mark.asyncio
async def test_fragment_recent_failed(client):
    html = await _get_ok(client, "/fragments/recent-failed")
    assert "Name" in html or "No failed tasks" in html


@pytest.mark.asyncio
async def test_fragment_duration(client):
    html = await _get_ok(client, "/fragments/duration")
    # Contains duration labels or no-data message
    assert "P50" in html or "No data" in html


# ---------------------------------------------------------------------------
# Health / index
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healthz(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] in ("connected", "unavailable")


@pytest.mark.asyncio
async def test_index(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 404 for unknown routes (sanity check)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_route_404(client):
    response = await client.get("/fragments/does-not-exist")
    assert response.status_code == 404
