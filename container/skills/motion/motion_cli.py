#!/usr/bin/env python3
"""
Motion CLI - Self-contained command-line interface for Motion task management.
Uses only Python stdlib (urllib) — no external dependencies.
Requires: MOTION_API_KEY, MOTION_WORKSPACE_ID environment variables.
"""

import json
import os
import sys
import argparse
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta

API_BASE_URL = "https://api.usemotion.com/v1"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_api_key():
    key = os.environ.get("MOTION_API_KEY")
    if not key:
        print("Error: MOTION_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    return key


def _get_workspace_id():
    wid = os.environ.get("MOTION_WORKSPACE_ID")
    if not wid:
        print("Error: MOTION_WORKSPACE_ID environment variable not set", file=sys.stderr)
        sys.exit(1)
    return wid


def _request(method, path, params=None, body=None, max_retries=4, base_delay=2.0):
    """Make a Motion API request with exponential backoff on 429s."""
    api_key = _get_api_key()
    url = API_BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    encoded_body = json.dumps(body).encode() if body is not None else None

    for attempt in range(max_retries + 1):
        time.sleep(1.0)  # base rate-limit courtesy delay
        req = urllib.request.Request(url, data=encoded_body, method=method)
        req.add_header("X-API-Key", api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; nanoclaw/1.0)")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else base_delay * (2 ** attempt)
                print(f"Rate limited. Waiting {wait:.0f}s (attempt {attempt + 1}/{max_retries})...",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            raw = e.read().decode()
            try:
                err = json.loads(raw)
            except Exception:
                err = {"raw": raw}
            print(f"HTTP {e.code}: {json.dumps(err, indent=2)}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Request error: {e}", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    workspace_id = _get_workspace_id()
    data = _request("GET", "/tasks", params={"workspaceId": workspace_id})
    tasks = data.get("tasks", [])[:args.limit]
    print(json.dumps(tasks, indent=2))
    return 0 if tasks else 1


def cmd_search(args):
    workspace_id = _get_workspace_id()
    data = _request("GET", "/tasks", params={"workspaceId": workspace_id})
    keyword = args.keyword.lower()
    tasks = [t for t in data.get("tasks", [])
             if keyword in t.get("name", "").lower()
             or keyword in t.get("description", "").lower()]
    print(json.dumps(tasks, indent=2))
    return 0 if tasks else 1


def cmd_create(args):
    workspace_id = _get_workspace_id()

    due_date = None
    if args.due_days:
        due_date = (datetime.now() + timedelta(days=args.due_days)).strftime("%Y-%m-%d")

    labels = None
    if args.labels:
        labels = [l.strip() for l in args.labels.split(",")]

    body = {
        "name": args.name,
        "workspaceId": workspace_id,
        "priority": args.priority.upper(),
        "duration": args.duration,
    }
    if args.description:
        body["description"] = args.description
    if due_date:
        body["dueDate"] = due_date
    if labels:
        body["labels"] = labels

    task = _request("POST", "/tasks", body=body)
    print(json.dumps(task, indent=2))
    return 0 if task else 1


def cmd_update(args):
    update_data = {}

    if args.start_date:
        update_data["autoScheduled"] = {
            "startDate": args.start_date,
            "deadlineType": "SOFT",
            "schedule": "Work Hours",
        }
    if args.priority:
        update_data["priority"] = args.priority.upper()

    if not update_data:
        print("Error: no update fields provided", file=sys.stderr)
        return 1

    task = _request("PATCH", f"/tasks/{args.task_id}", body=update_data)
    print(json.dumps(task, indent=2))
    return 0


def cmd_delete(args):
    _request("DELETE", f"/tasks/{args.task_id}")
    print(f"Deleted task {args.task_id}")
    return 0


def cmd_bulk_update_start_date(args):
    workspace_id = _get_workspace_id()
    results = {"updated": [], "not_found": [], "failed": []}

    for name in args.names:
        name = name.strip()
        print(f"\n--- Processing: {name} ---", file=sys.stderr)

        data = _request("GET", "/tasks", params={"workspaceId": workspace_id})
        keyword = name.lower()
        matches = [t for t in data.get("tasks", [])
                   if keyword in t.get("name", "").lower()]

        if not matches:
            print(f"  Not found: {name}", file=sys.stderr)
            results["not_found"].append(name)
            time.sleep(args.delay)
            continue

        task_id = matches[0]["id"]
        print(f"  Found: {task_id}", file=sys.stderr)

        time.sleep(args.delay)
        update_data = {
            "autoScheduled": {
                "startDate": args.start_date,
                "deadlineType": "SOFT",
                "schedule": "Work Hours",
            }
        }
        try:
            _request("PATCH", f"/tasks/{task_id}", body=update_data)
            print(f"  Updated start date to {args.start_date}", file=sys.stderr)
            results["updated"].append(name)
        except SystemExit:
            results["failed"].append(name)

        time.sleep(args.delay)

    print(json.dumps(results, indent=2))
    return 0 if not results["failed"] else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Motion CLI — manage Motion tasks")
    subparsers = parser.add_subparsers(dest="command")

    # list
    p = subparsers.add_parser("list", help="List tasks")
    p.add_argument("--limit", type=int, default=10)

    # search
    p = subparsers.add_parser("search", help="Search tasks by keyword")
    p.add_argument("keyword")

    # create
    p = subparsers.add_parser("create", help="Create a task")
    p.add_argument("name")
    p.add_argument("--description")
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--priority", default="MEDIUM", choices=["ASAP", "HIGH", "MEDIUM", "LOW"])
    p.add_argument("--due-days", type=int)
    p.add_argument("--labels")

    # update
    p = subparsers.add_parser("update", help="Update a task")
    p.add_argument("task_id")
    p.add_argument("--start-date")
    p.add_argument("--priority", choices=["ASAP", "HIGH", "MEDIUM", "LOW"])

    # delete
    p = subparsers.add_parser("delete", help="Delete a task")
    p.add_argument("task_id")

    # bulk-update-start-date
    p = subparsers.add_parser("bulk-update-start-date", help="Set start date on multiple tasks by name")
    p.add_argument("names", nargs="+")
    p.add_argument("--start-date", required=True)
    p.add_argument("--delay", type=float, default=3.0)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    dispatch = {
        "list": cmd_list,
        "search": cmd_search,
        "create": cmd_create,
        "update": cmd_update,
        "delete": cmd_delete,
        "bulk-update-start-date": cmd_bulk_update_start_date,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
