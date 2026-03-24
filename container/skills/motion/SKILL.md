---
name: motion
description: >
  Motion task management — the user's task manager. Use when the user asks about their tasks,
  what's scheduled, what to work on next, what's coming up, their to-do list, task priorities,
  overdue tasks, or anything related to Motion. Also use when they ask to add, create, delete,
  update, or search for a task. Motion auto-schedules tasks, so always retrieve real data — never guess.
  For upcoming tasks, list and sort by scheduledStart ascending. For priority tasks, sort by
  priority (ASAP > HIGH > MEDIUM > LOW) then scheduledStart. To fix tasks with no scheduledStart,
  update them with today's date as the start-date.
metadata:
  {
    "nanoclaw":
      {
        "emoji": "⚡",
        "requires": { "bins": ["python3"], "env": ["MOTION_API_KEY", "MOTION_WORKSPACE_ID"] },
        "primaryEnv": "MOTION_API_KEY",
      },
  }
---

# ⚡ Motion

Motion is the user's task management app. It auto-schedules tasks into their calendar.
Always retrieve live data — never guess or make up task info.

Script location: `/home/node/.claude/skills/motion/motion_cli.py`
Fallback path: `/home/node/.claude/skills/motion/scripts/motion_cli.py`

**ALWAYS run the script — never fabricate task data.**

## Listing & Displaying Tasks

### Upcoming tasks (sorted by schedule)

```bash
python3 /home/node/.claude/skills/motion/motion_cli.py list --limit 20
```

The output is JSON. Sort the returned tasks by `scheduledStart` (ascending) to get what's
coming up next. Tasks without a `scheduledStart` fall back to `dueDate` for ordering.
Filter out completed tasks. Show the user a clean formatted list: priority, name, scheduled
time, and due date.

### Priority tasks

List tasks, then sort by priority order: ASAP → HIGH → MEDIUM → LOW, then by `scheduledStart`.

### Search Tasks

```bash
python3 /home/node/.claude/skills/motion/motion_cli.py search "keyword"
```

### Create Task

```bash
python3 /home/node/.claude/skills/motion/motion_cli.py create "Task Name" [OPTIONS]
```

Options:
- `--description "text"` - Task description
- `--duration 30` - Duration in minutes (default: 30)
- `--priority MEDIUM` - Priority: ASAP, HIGH, MEDIUM, LOW (default: MEDIUM)
- `--due-days 7` - Due in N days from now
- `--labels tag1,tag2` - Comma-separated labels

**IMPORTANT:** After creating a task, always immediately call `update` with `--start-date` set
to today's date (or the user's requested start date). Without a start date, Motion will not
schedule the task. Never create a task without following up with an update to set the start date.

### Delete Task

```bash
python3 /home/node/.claude/skills/motion/motion_cli.py delete <task_id>
```

### Update Task

Use to set the start date (so Motion auto-schedules the task) or change priority.

```bash
python3 /home/node/.claude/skills/motion/motion_cli.py update <task_id> --start-date YYYY-MM-DD
python3 /home/node/.claude/skills/motion/motion_cli.py update <task_id> --priority HIGH
python3 /home/node/.claude/skills/motion/motion_cli.py update <task_id> --start-date YYYY-MM-DD --priority MEDIUM
```

**When tasks have no `scheduledStart`**, set `--start-date` to today's date so Motion picks them
up for scheduling. Always search for the task first to get its `id`.

### Bulk Update Start Date (preferred for multiple tasks)

**Use this instead of looping search+update separately** — it runs everything in one process with
built-in delays, avoiding rate limit errors from rapid sequential script invocations.

```bash
python3 /home/node/.claude/skills/motion/motion_cli.py bulk-update-start-date \
  "Task Name One" "Task Name Two" "Task Name Three" \
  --start-date YYYY-MM-DD
```

Options:
- `--start-date YYYY-MM-DD` (required) — date to set as start date
- `--delay 3` — seconds between tasks (default: 3, increase to 5 if still rate limited)

Output: JSON with `updated`, `not_found`, and `failed` lists.

## Task Fields (in JSON output)

- `name` — task title
- `scheduledStart` — ISO 8601 datetime when Motion has scheduled the task
- `dueDate` — ISO 8601 date the task must be done by
- `priority` — ASAP, HIGH, MEDIUM, or LOW
- `status.name` — e.g. "Todo", "In Progress", "Completed"
- `id` — task ID (needed for delete)

## Priority Levels

ASAP > HIGH > MEDIUM > LOW

## Notes

- Motion auto-schedules tasks — `scheduledStart` reflects when Motion plans to do the task
- Tasks without a `scheduledStart` haven't been scheduled yet (no available time slot found)
- Rate limiting: 1 second between requests (handled automatically)
- All output is JSON
