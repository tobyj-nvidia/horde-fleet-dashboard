# Task Conventions

## Required: Write Result File
Before exiting, you MUST write `.task-result.json` in this directory with:
```json
{"outcome": "success", "summary": "what you did", "artifacts": ["files created"]}
```
If `outcome` is `"failure"`, explain why in `summary`.
**Failure to write this file means the task fails regardless of exit code.**

## Required: Commit Your Changes
When you are done, stage and commit ALL your changes **except `.task-result.json`** before exiting:
```bash
git add -A
git reset HEAD .task-result.json 2>/dev/null || true
git commit -m '<short description of what you did>'
```
Do NOT commit `.task-result.json` — the worker reads it directly and it must not appear in the repo history.
The worker will handle pushing and merging to the target branch.
**Uncommitted changes are lost when the task completes.**

## Working Directory
You are in: `/tmp/fleet-workspaces/horde-fleet-dashboard/slot-2`
Repos are checked out here. Use files directly — do not clone.

