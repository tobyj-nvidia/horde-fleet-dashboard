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

## Token Usage Tracking
When writing `.task-result.json`, include a `tokens` block if available:
```json
{"outcome": "success", "summary": "what you did", "tokens": {"input": 12345, "output": 678}}
```
This helps track token spend across the fleet.

## Working Directory
You are in: `/tmp/fleet-workspaces/tobyj-nvidia/horde-fleet-dashboard/slot-2`
Repos are checked out here. Use files directly — do not clone.

---
## ⚠️  MANDATORY EXIT CHECKLIST — Read This Before You Stop

**WARNING: If you exit without writing `.task-result.json`, your ENTIRE TASK FAILS — even if all code changes are correct.**

Before exiting, you MUST complete these steps **in this exact order**:

1. **`git add -A`** — stage all changes
2. **`git reset HEAD .task-result.json 2>/dev/null || true`** — unstage the result file
3. **`git commit -m '<short description>'`** — commit your work
4. **Write `.task-result.json`** — this is your FINAL action:
   ```json
   {"outcome": "success", "summary": "what you did", "artifacts": ["files created"]}
   ```

**Failure to write `.task-result.json` means the task FAILS regardless of exit code.**
