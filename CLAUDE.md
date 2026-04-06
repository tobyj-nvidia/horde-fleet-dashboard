# Task Conventions

## Required: Write Result File
Before exiting, you MUST write `.task-result.json` in this directory with:
```json
{"outcome": "success", "summary": "what you did", "artifacts": ["files created"]}
```
If `outcome` is `"failure"`, explain why in `summary`.
**Failure to write this file means the task fails regardless of exit code.**

## Required: Commit Your Changes
When you are done, stage and commit ALL your changes before exiting:
```bash
git add -A
git commit -m '<short description of what you did>'
```
The worker will handle pushing and merging to the target branch.
**Uncommitted changes are lost when the task completes.**

## Working Directory
You are in: `/tmp/fleet-workspaces/tobyj-nvidia/horde-fleet-dashboard/slot-0`
Repos are checked out here. Use files directly — do not clone.

