# Horde Fleet Dashboard

Fleet Observability Dashboard for the [horde](https://github.com/tobyj-nvidia/horde) distributed task scheduler.

## Overview

This dashboard provides real-time visibility into the horde fleet: worker health, task throughput, queue depth, and job history. It connects to a [Dolt](https://github.com/dolthub/dolt) sql-server for data.

## Tech Stack

- **Python 3.11+**
- **FastAPI** — async web framework
- **HTMX** — dynamic UI without a JavaScript build step
- **aiomysql** — async MySQL-compatible driver for Dolt
- **Jinja2** — server-side HTML templating

## Prerequisites

- Python 3.11 or later
- A running Dolt sql-server instance

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in your Dolt connection details
uvicorn horde_fleet_dashboard.main:app --reload
```

Then open http://localhost:8000 in your browser.

## Configuration

Set the following environment variables (or put them in a `.env` file):

| Variable | Description | Default |
|---|---|---|
| `DOLT_HOST` | Dolt sql-server host | `127.0.0.1` |
| `DOLT_PORT` | Dolt sql-server port | `3306` |
| `DOLT_USER` | Database user | `root` |
| `DOLT_PASSWORD` | Database password | `` |
| `DOLT_DATABASE` | Database name | `horde` |
