# Test Coverage Audits

This directory contains periodic coverage audits for the horde-fleet-dashboard project.

## Audits

| Date | Commit | Coverage | Report |
|------|--------|----------|--------|
| 2026-04-06 | `f7bb147` | 0% (no tests) | [audit-2026-04-06.md](audit-2026-04-06.md) |

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx

# Run tests (currently: 0 collected)
python3 -m pytest
```

## Current State

The project has **no tests**. See [audit-2026-04-06.md](audit-2026-04-06.md) for:
- Module-by-module breakdown
- Template coverage analysis
- Query coverage analysis
- Risk assessment of untested code paths
- Prioritized recommendations for adding tests

## Adding New Audits

When running a new coverage audit:
1. Run `python3 -m pytest --cov=src/dashboard --cov-report=term-missing`
2. Record the output and commit hash
3. Add a new `audit-YYYY-MM-DD.md` following the existing format
4. Update the table in this README
