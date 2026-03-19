#!/usr/bin/env python3
"""ADHD Coach state manager. Data stored at /opt/state/adhd-coach.json."""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, date, timezone

# Ensure UTF-8 output on all platforms (important for Windows terminals)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_FILE = os.environ.get("ADHD_STATE_FILE", "/workspace/group/adhd-coach-state.json")
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    # Ensure all top-level keys exist with defaults
    data.setdefault("current_focus", None)
    data.setdefault("tasks", [])
    data.setdefault("today", {"date": date.today().isoformat(), "completed": [],
                              "sessions_completed": 0, "check_ins_sent": 0,
                              "last_physical_reminder": None})
    data.setdefault("preferences", {
        "work_duration_min": 15,
        "break_duration_min": 5,
        "long_break_duration_min": 15,
        "long_break_after": 4,
        "check_in_interval_min": 45,
        "work_hours_start": "08:30",
        "work_hours_end": "15:00",
        "timezone": "Australia/Sydney",
        "hyperfocus_alert_min": 90,
    })

    # Auto-reset today block if date has changed
    today_str = date.today().isoformat()
    if data["today"].get("date") != today_str:
        data["today"] = {
            "date": today_str,
            "completed": [],
            "sessions_completed": 0,
            "check_ins_sent": 0,
            "last_physical_reminder": None,
        }
        # Clear stale session state from yesterday
        if data.get("current_focus"):
            data["current_focus"] = None

    return data


def save(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=os.path.dirname(DATA_FILE))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status(_args):
    """Show current focus, session state, and today's completed count."""
    data = load()
    prefs = data["preferences"]
    focus = data["current_focus"]
    today = data["today"]

    print(f"Date: {today['date']}")
    print(f"Tasks completed today: {len(today['completed'])}")
    print(f"Focus sessions completed today: {today['sessions_completed']}")

    if focus:
        task = focus.get("task", "(none)")
        active = focus.get("session_active", False)
        stype = focus.get("session_type", "work")
        started = focus.get("started_at")

        elapsed_min = ""
        if started:
            try:
                start_dt = datetime.fromisoformat(started)
                elapsed = (datetime.now(timezone.utc) - start_dt).total_seconds() / 60
                elapsed_min = f" ({int(elapsed)} min elapsed)"
            except Exception:
                pass

        if active:
            dur = focus.get("session_duration_min", prefs["work_duration_min"])
            print(f"\nCurrent session: {stype.upper()} — {task}{elapsed_min}")
            print(f"Session length: {dur} min")
        else:
            print(f"\nCurrent focus task: {task} (no active timer)")
    else:
        print("\nNo current focus task.")

    backlog = data["tasks"]
    print(f"\nBacklog: {len(backlog)} task(s)")


def cmd_start_session(args):
    """Start a focus session. Usage: start-session <task> [--duration N]"""
    if not args:
        print("Error: provide a task name.")
        print("Usage: adhd_coach.py start-session <task> [--duration N]")
        sys.exit(1)

    data = load()
    prefs = data["preferences"]

    # Parse args: task name is everything before --duration
    duration = prefs["work_duration_min"]
    task_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--duration" and i + 1 < len(args):
            try:
                duration = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            task_parts.append(args[i])
            i += 1

    task = " ".join(task_parts)

    data["current_focus"] = {
        "task": task,
        "started_at": now_iso(),
        "session_active": True,
        "session_type": "work",
        "session_duration_min": duration,
    }
    save(data)
    print(f"Session started: {task}")
    print(f"Duration: {duration} min")
    print(f"Started at: {data['current_focus']['started_at']}")


def cmd_end_session(args):
    """End the current session. Usage: end-session [--completed|--paused|--pivoted]"""
    data = load()
    focus = data.get("current_focus")

    if not focus or not focus.get("session_active"):
        print("No active session.")
        return

    outcome = "paused"
    if "--completed" in args:
        outcome = "completed"
    elif "--pivoted" in args:
        outcome = "pivoted"

    task = focus.get("task", "(unknown)")

    if outcome == "completed":
        data["today"]["completed"].append({
            "task": task,
            "completed_at": now_iso(),
        })
        data["today"]["sessions_completed"] += 1
        # Remove from backlog if present
        data["tasks"] = [t for t in data["tasks"] if t["task"].lower() != task.lower()]
        data["current_focus"] = None
        print(f"Session complete: {task}")
        print(f"Tasks completed today: {len(data['today']['completed'])}")
    elif outcome == "pivoted":
        data["today"]["sessions_completed"] += 1
        data["current_focus"]["session_active"] = False
        print(f"Pivoted away from: {task}")
    else:
        data["current_focus"]["session_active"] = False
        print(f"Session paused: {task}")

    save(data)


def cmd_start_break(args):
    """Start a break. Usage: start-break [--duration N]"""
    data = load()
    prefs = data["preferences"]

    duration = prefs["break_duration_min"]
    if "--duration" in args:
        idx = args.index("--duration")
        if idx + 1 < len(args):
            try:
                duration = int(args[idx + 1])
            except ValueError:
                pass

    # Preserve current task but mark as break
    focus = data.get("current_focus") or {}
    data["current_focus"] = {
        "task": focus.get("task", ""),
        "started_at": now_iso(),
        "session_active": True,
        "session_type": "break",
        "session_duration_min": duration,
    }
    save(data)
    print(f"Break started: {duration} min")


def cmd_end_break(_args):
    """End break. Usage: end-break"""
    data = load()
    focus = data.get("current_focus")
    task = focus.get("task", "") if focus else ""

    data["current_focus"] = {
        "task": task,
        "started_at": None,
        "session_active": False,
        "session_type": "work",
        "session_duration_min": data["preferences"]["work_duration_min"],
    } if task else None

    save(data)
    print("Break ended." + (f" Ready to continue: {task}" if task else " No current task."))


def cmd_set_focus(args):
    """Set focus task without a timer. Usage: set-focus <task>"""
    if not args:
        print("Error: provide a task name.")
        sys.exit(1)
    task = " ".join(args)
    data = load()
    data["current_focus"] = {
        "task": task,
        "started_at": now_iso(),
        "session_active": False,
        "session_type": "work",
        "session_duration_min": data["preferences"]["work_duration_min"],
    }
    save(data)
    print(f"Focus set: {task}")


def cmd_clear_focus(_args):
    """Clear current focus. Usage: clear-focus"""
    data = load()
    data["current_focus"] = None
    save(data)
    print("Focus cleared.")


def cmd_add(args):
    """Add a task. Usage: add <task> [--priority high|medium|low]"""
    if not args:
        print("Error: provide a task name.")
        sys.exit(1)

    priority = "medium"
    task_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--priority" and i + 1 < len(args):
            p = args[i + 1].lower()
            if p in PRIORITY_ORDER:
                priority = p
            i += 2
        else:
            task_parts.append(args[i])
            i += 1

    task = " ".join(task_parts)
    data = load()
    data["tasks"].append({
        "id": uuid.uuid4().hex[:6],
        "task": task,
        "priority": priority,
        "added_date": date.today().isoformat(),
    })
    save(data)
    print(f"Added ({priority}): {task}")
    print(f"Backlog: {len(data['tasks'])} task(s)")


def cmd_add_tasks(args):
    """Brain dump: add multiple tasks separated by --. Usage: add-tasks <t1> -- <t2> -- ..."""
    if not args:
        print("Error: provide at least one task.")
        sys.exit(1)

    chunks = []
    current = []
    for a in args:
        if a == "--":
            if current:
                chunks.append(current)
            current = []
        else:
            current.append(a)
    if current:
        chunks.append(current)

    data = load()
    added = []
    for chunk in chunks:
        # Each chunk: task words, optionally ending with --priority X
        priority = "medium"
        task_parts = []
        i = 0
        while i < len(chunk):
            if chunk[i] == "--priority" and i + 1 < len(chunk):
                p = chunk[i + 1].lower()
                if p in PRIORITY_ORDER:
                    priority = p
                i += 2
            else:
                task_parts.append(chunk[i])
                i += 1
        task = " ".join(task_parts)
        entry = {
            "id": uuid.uuid4().hex[:6],
            "task": task,
            "priority": priority,
            "added_date": date.today().isoformat(),
        }
        data["tasks"].append(entry)
        added.append(entry)

    save(data)
    for item in added:
        print(f"Added ({item['priority']}): {item['task']}")
    print(f"\nBacklog: {len(data['tasks'])} task(s)")


def cmd_next_task(_args):
    """Show the single highest-priority task. Usage: next-task"""
    data = load()
    tasks = data.get("tasks", [])
    if not tasks:
        print("Backlog is empty. No tasks queued.")
        return

    # Sort by priority then FIFO (added_date)
    sorted_tasks = sorted(tasks, key=lambda t: (PRIORITY_ORDER.get(t.get("priority", "medium"), 1), t.get("added_date", "")))
    next_t = sorted_tasks[0]
    print(f"Next task: {next_t['task']} [{next_t['priority']}]")
    print(f"(Added: {next_t['added_date']} | {len(tasks)} total in backlog)")


def cmd_complete(args):
    """Mark a task as completed. Usage: complete <task name or partial>"""
    if not args:
        print("Error: provide a task name or partial match.")
        sys.exit(1)

    query = " ".join(args).lower()
    data = load()
    tasks = data["tasks"]

    # Try exact match first, then partial
    match = None
    for t in tasks:
        if t["task"].lower() == query:
            match = t
            break
    if not match:
        for t in tasks:
            if query in t["task"].lower():
                match = t
                break

    if not match:
        print(f"No task matched: {' '.join(args)}")
        print("Use list-tasks to see current backlog.")
        sys.exit(1)

    data["tasks"] = [t for t in tasks if t["id"] != match["id"]]
    data["today"]["completed"].append({
        "task": match["task"],
        "completed_at": now_iso(),
    })

    # Clear current focus if it was this task
    focus = data.get("current_focus")
    if focus and focus.get("task", "").lower() == match["task"].lower():
        data["today"]["sessions_completed"] += 1
        data["current_focus"] = None

    save(data)
    print(f"Completed: {match['task']}")
    print(f"Tasks done today: {len(data['today']['completed'])}")


def cmd_remove(args):
    """Remove a task from backlog. Usage: remove <task name or partial>"""
    if not args:
        print("Error: provide a task name.")
        sys.exit(1)

    query = " ".join(args).lower()
    data = load()
    tasks = data["tasks"]

    match = None
    for t in tasks:
        if t["task"].lower() == query:
            match = t
            break
    if not match:
        for t in tasks:
            if query in t["task"].lower():
                match = t
                break

    if not match:
        print(f"No task matched: {' '.join(args)}")
        sys.exit(1)

    data["tasks"] = [t for t in tasks if t["id"] != match["id"]]
    save(data)
    print(f"Removed: {match['task']}")
    print(f"Backlog: {len(data['tasks'])} task(s)")


def cmd_list_tasks(_args):
    """List all tasks in backlog. Usage: list-tasks"""
    data = load()
    tasks = data.get("tasks", [])
    if not tasks:
        print("Backlog is empty.")
        return

    sorted_tasks = sorted(tasks, key=lambda t: (PRIORITY_ORDER.get(t.get("priority", "medium"), 1), t.get("added_date", "")))
    print(f"Backlog ({len(sorted_tasks)} tasks)\n")
    for t in sorted_tasks:
        print(f"[{t['priority'].upper()}] {t['task']}  (added {t['added_date']})")


def cmd_today_summary(_args):
    """Show today's completed tasks and session count. Usage: today-summary"""
    data = load()
    today = data["today"]
    completed = today.get("completed", [])
    sessions = today.get("sessions_completed", 0)

    print(f"Date: {today['date']}")
    print(f"Focus sessions: {sessions}")
    print(f"Tasks completed: {len(completed)}")

    if completed:
        print()
        for item in completed:
            ts = item.get("completed_at", "")
            try:
                dt = datetime.fromisoformat(ts)
                time_str = dt.strftime("%H:%M")
            except Exception:
                time_str = ""
            suffix = f"  ({time_str})" if time_str else ""
            print(f"  ✓ {item['task']}{suffix}")


def cmd_set_pref(args):
    """Set a preference. Usage: set-pref <key> <value>"""
    if len(args) < 2:
        print("Usage: set-pref <key> <value>")
        print("Keys: work_duration_min, break_duration_min, long_break_duration_min,")
        print("      long_break_after, check_in_interval_min, work_hours_start,")
        print("      work_hours_end, timezone, hyperfocus_alert_min")
        sys.exit(1)

    key = args[0]
    value = args[1]
    data = load()

    INT_KEYS = {"work_duration_min", "break_duration_min", "long_break_duration_min",
                "long_break_after", "check_in_interval_min", "hyperfocus_alert_min"}

    if key in INT_KEYS:
        try:
            value = int(value)
        except ValueError:
            print(f"Error: {key} must be an integer.")
            sys.exit(1)

    if key not in data["preferences"]:
        print(f"Unknown preference: {key}")
        sys.exit(1)

    data["preferences"][key] = value
    save(data)
    print(f"Set {key} = {value}")


def cmd_get_prefs(_args):
    """Show all preferences. Usage: get-prefs"""
    data = load()
    prefs = data["preferences"]
    print("Preferences:")
    for k, v in prefs.items():
        print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS = {
    "status": cmd_status,
    "start-session": cmd_start_session,
    "end-session": cmd_end_session,
    "start-break": cmd_start_break,
    "end-break": cmd_end_break,
    "set-focus": cmd_set_focus,
    "clear-focus": cmd_clear_focus,
    "add": cmd_add,
    "add-tasks": cmd_add_tasks,
    "next-task": cmd_next_task,
    "complete": cmd_complete,
    "remove": cmd_remove,
    "list-tasks": cmd_list_tasks,
    "today-summary": cmd_today_summary,
    "set-pref": cmd_set_pref,
    "get-prefs": cmd_get_prefs,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("ADHD Coach — State Manager")
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        print("\nExamples:")
        print("  adhd_coach.py status")
        print('  adhd_coach.py start-session "Write report" --duration 15')
        print("  adhd_coach.py end-session --completed")
        print("  adhd_coach.py add \"Review PR\" --priority high")
        print("  adhd_coach.py add-tasks \"Task one\" -- \"Task two\" -- \"Task three\"")
        print("  adhd_coach.py next-task")
        print("  adhd_coach.py complete \"Review PR\"")
        print("  adhd_coach.py today-summary")
        sys.exit(1)

    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
