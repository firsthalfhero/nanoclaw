---
name: openproject
description: >
  OpenProject centralized multi-project task management. Use when the user asks about their tasks
  across projects, workload, what's due, deadlines, or anything related to project management.
  Also use when they ask to create, update, complete, or link tasks; assign tasks to team members;
  or view project status. Queries work across ALL projects the user has access to — never guess
  task data, always retrieve live from OpenProject. For weekly/daily views, use date-range queries.
  For project status, retrieve summaries. Always run the script — never fabricate data.
metadata:
  {
    "nanoclaw":
      {
        "emoji": "📊",
        "requires": { "bins": ["python3", "curl"], "env": ["OPENPROJECT_MCP_URL"] },
        "primaryEnv": "OPENPROJECT_MCP_URL",
        "description": "Multi-project task management with HP server build and concurrent initiatives",
      },
  }
---

# 📊 OpenProject

Centralized task management across all projects. OpenProject is the single source of truth for
all work — HP server build, Nutrition tracker, and other concurrent initiatives.

**ALWAYS run the script — never fabricate task data.**

Script location: `C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py`
MCP Server: http://localhost:8085 (or set via OPENPROJECT_MCP_URL)

## Daily & Weekly Task Views

### What am I working on today?

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_tasks_by_date --date_range "today" --status open
```

Output: JSON with tasks grouped by project, sorted by due date.

### This week's workload

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_tasks_by_date --date_range "this week" --status open
```

Includes all projects. Format for user: list by project, sort by date due.

### Next week's outlook

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_tasks_by_date --date_range "next week" --status open
```

### Custom date range

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_tasks_by_date --date_range "2026-05-21 to 2026-05-28" --status open
```

Supports:
- `"today"` — today only
- `"tomorrow"` — tomorrow only
- `"this week"` — Monday through Sunday of current week
- `"next week"` — Monday through Sunday of next week
- `"this month"` — entire current month
- `"next month"` — entire next month
- `"today to +N"` — today through N days ahead (e.g., "today to +2")
- `"YYYY-MM-DD to YYYY-MM-DD"` — explicit range

## Task Management

### Create a task

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py create_task \
  --project_id {project_id} \
  --subject "Task title" \
  --description "Description" \
  --due_date "YYYY-MM-DD" \
  --assignee_email "user@example.com" \
  --estimated_hours 2
```

First, get the project ID:
```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py list_projects
```

Examples:
- HP Server Build: project_id = 5
- Nutrition Tracker: project_id = 2

Always set a due_date so the task appears in date-range queries.

### Update a task

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py update_task \
  --task_id {work_package_id} \
  --status "In Progress" \
  --due_date "YYYY-MM-DD"
```

Status options depend on project, but typically:
- "New"
- "In Progress"
- "Closed"
- "On Hold"

### Link tasks (create dependency)

Use when a task depends on another or they're related:

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py create_dependency \
  --from_task_id {source_task_id} \
  --to_task_id {dependent_task_id} \
  --relation_type "follows" \
  --description "Why they're linked"
```

Relation types:
- `"follows"` — to_task depends on from_task (from_task must finish first)
- `"precedes"` — from_task comes before to_task
- `"blocks"` — from_task blocks to_task
- `"relates"` — general relationship

### Mark task complete

Update task status to "Closed":

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py update_task \
  --task_id {work_package_id} \
  --status "Closed"
```

## Project Management

### List all projects

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py list_projects
```

Returns all accessible projects with IDs. Use project_id for creating tasks.

### Project status

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_project_summary --project_id {project_id}
```

Returns:
- Total task count
- Tasks by status (New, In Progress, Closed, etc.)
- Overdue task count
- Tasks due this week

### Create a project

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py create_project \
  --name "Project Name" \
  --description "Description"
```

## Team Management

### Who's on a project?

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_project_team --project_id {project_id}
```

Shows team members, roles, and emails. Use emails for task assignment.

### Assign task to team member

Use the assignee_email flag when creating a task:

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py create_task \
  --project_id 5 \
  --subject "Task" \
  --assignee_email "george@example.com" \
  --due_date "2026-05-22"
```

Or update existing task:

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py update_task \
  --task_id {work_package_id} \
  --assignee_email "user@example.com"
```

## Multi-Project Queries

The key feature of OpenProject in NanoClaw: **single query returns tasks from ALL projects**.

### Compare workload across projects

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_tasks_by_date --date_range "this week"
```

Returns:
```
HP Server Build: 3 tasks (due dates, statuses)
Nutrition Tracker: 2 tasks (due dates, statuses)
Other Project: 1 task (due dates, statuses)
```

Display sorted by project, then by due date within each project.

### Filter to specific projects

```bash
python3 C:\Users\George\LLM-Projects\openproject-mcp-server\nanoclaw_skill\openproject_cli.py get_tasks_by_date \
  --date_range "this week" \
  --projects "5,2"
```

Projects 5 and 2 only. Use `--projects "all"` or omit for all projects (default).

## Task Fields (JSON Output)

When you query tasks, the JSON includes:
- `id` — work package ID (use for update/link/delete)
- `subject` — task title
- `description` — full description
- `project_id` — which project the task is in
- `due_date` — due date (YYYY-MM-DD)
- `start_date` — when work starts
- `status` — current status (New, In Progress, etc.)
- `assignee` — who it's assigned to
- `url` — link to task in OpenProject UI

## Configuration

Set the MCP server URL via environment variable (optional, defaults to http://localhost:8085):

```bash
export OPENPROJECT_MCP_URL=http://openproject-mcp:8085
```

Or pass in commands:
```bash
OPENPROJECT_MCP_URL=http://openproject-mcp:8085 python3 openproject_cli.py list_projects
```

## Tips

**Always retrieve live data** — run the script for current task info. Never guess or make up tasks.

**Multi-project is the strength** — when the user asks "what am I working on", query across all projects
to get the complete picture. Don't ask which project — just get everything.

**Date ranges** — use human-friendly formats ("this week", "today to +2") for natural language matching.
The script handles parsing.

**Dependencies matter** — when a user says "Task B depends on Task A", use `create_dependency` to link them.
This shows in the Gantt chart and helps with scheduling.

**Always search before update** — if you need to update a task by name (not ID), search for it first
to get the ID.

## Error Handling

If a command fails:
- Check that OPENPROJECT_MCP_URL points to a running MCP server
- Verify project IDs exist (run `list_projects` to confirm)
- Ensure task IDs are valid (run `get_tasks_by_date` to find them)
- Confirm user has access to the project

## Related Skills

- **Motion**: Personal task scheduling (auto-scheduled tasks)
- **Gmail**: Email integration
- **Google Calendar**: Calendar sync

OpenProject is for **shared project management** across teams and initiatives.
Use OpenProject when the user asks about work across projects or team assignments.
Use Motion for their personal to-do list auto-scheduling.

---

**Last Updated**: May 21, 2026  
**Version**: 1.0.0  
**Status**: Ready for use with NanoClaw
