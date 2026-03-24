#!/usr/bin/env python3
"""
Motion CLI — self-contained Motion REST API client.
No external dependencies. Uses stdlib urllib only.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

API_BASE = "https://api.usemotion.com/v1"


def get_api_key():
    key = os.environ.get("MOTION_API_KEY")
    if not key:
        print("Error: MOTION_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    return key


def get_workspace_id():
    wid = os.environ.get("MOTION_WORKSPACE_ID")
    if not wid:
        print("Error: MOTION_WORKSPACE_ID not set", file=sys.stderr)
        sys.exit(1)
    return wid


def _request(method, path, params=None, payload=None, retry=4):
    api_key = get_api_key()
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    body = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for attempt in range(retry + 1):
        time.sleep(1.0)  # base rate-limit courtesy delay
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retry:
                wait = float(e.headers.get("Retry-After", 2 * (2 ** attempt)))
                print(f"Rate limited — waiting {wait:.0f}s (attempt {attempt+1}/{retry})", file=sys.stderr)
                time.sleep(wait)
                continue
            body_text = e.read().decode()
            print(f"HTTP {e.code}: {body_text}", file=sys.stderr)
            sys.exit(1)
    print("Max retries exceeded", file=sys.stderr)
    sys.exit(1)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    data = _request("GET", "/tasks", params={
        "workspaceId": get_workspace_id(),
    })
    tasks = data.get("tasks", [])[:args.limit]
    print(json.dumps(tasks, indent=2))


def cmd_search(args):
    data = _request("GET", "/tasks", params={
        "workspaceId": get_workspace_id(),
        "name": args.keyword,
    })
    tasks = data.get("tasks", [])
    print(json.dumps(tasks, indent=2))


def cmd_create(args):
    workspace_id = get_workspace_id()
    due_date = None
    if args.due_days:
        due_date = (datetime.now() + timedelta(days=args.due_days)).strftime("%Y-%m-%d")

    payload = {
        "name": args.name,
        "workspaceId": workspace_id,
        "duration": args.duration,
        "priority": args.priority.upper(),
    }
    if args.description:
        payload["description"] = args.description
    if due_date:
        payload["dueDate"] = due_date
    if args.labels:
        payload["labels"] = [l.strip() for l in args.labels.split(",")]

    task = _request("POST", "/tasks", payload=payload)
    print(json.dumps(task, indent=2))

    # Immediately set start date so Motion schedules it
    task_id = task.get("id")
    if task_id and args.start_date:
        _set_start_date(task_id, args.start_date)
    elif task_id:
        today = datetime.now().strftime("%Y-%m-%d")
        _set_start_date(task_id, today)


def _set_start_date(task_id, start_date):
    _request("PATCH", f"/tasks/{task_id}", payload={
        "autoScheduled": {
            "startDate": start_date,
            "deadlineType": "SOFT",
            "schedule": "Work Hours",
        }
    })


def cmd_update(args):
    payload = {}
    if args.start_date:
        payload["autoScheduled"] = {
            "startDate": args.start_date,
            "deadlineType": "SOFT",
            "schedule": "Work Hours",
        }
    if args.priority:
        payload["priority"] = args.priority.upper()

    if not payload:
        print("Error: nothing to update", file=sys.stderr)
        sys.exit(1)

    task = _request("PATCH", f"/tasks/{args.task_id}", payload=payload)
    print(json.dumps(task, indent=2))


def cmd_delete(args):
    _request("DELETE", f"/tasks/{args.task_id}")
    print(f"Deleted: {args.task_id}")


def cmd_bulk_update_start_date(args):
    results = {"updated": [], "not_found": [], "failed": []}
    workspace_id = get_workspace_id()

    for name in args.names:
        name = name.strip()
        data = _request("GET", "/tasks", params={"workspaceId": workspace_id, "name": name})
        tasks = data.get("tasks", [])
        if not tasks:
            results["not_found"].append(name)
            time.sleep(args.delay)
            continue

        task_id = tasks[0].get("id")
        time.sleep(args.delay)
        try:
            _set_start_date(task_id, args.start_date)
            results["updated"].append(name)
        except SystemExit:
            results["failed"].append(name)
        time.sleep(args.delay)

    print(json.dumps(results, indent=2))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Motion CLI")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("search")
    p.add_argument("keyword")

    p = sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--description")
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--priority", default="MEDIUM", choices=["ASAP", "HIGH", "MEDIUM", "LOW"])
    p.add_argument("--due-days", type=int)
    p.add_argument("--labels")
    p.add_argument("--start-date")

    p = sub.add_parser("update")
    p.add_argument("task_id")
    p.add_argument("--start-date")
    p.add_argument("--priority", choices=["ASAP", "HIGH", "MEDIUM", "LOW"])

    p = sub.add_parser("delete")
    p.add_argument("task_id")

    p = sub.add_parser("bulk-update-start-date")
    p.add_argument("names", nargs="+")
    p.add_argument("--start-date", required=True)
    p.add_argument("--delay", type=float, default=3.0)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {
        "list": cmd_list,
        "search": cmd_search,
        "create": cmd_create,
        "update": cmd_update,
        "delete": cmd_delete,
        "bulk-update-start-date": cmd_bulk_update_start_date,
    }[args.command](args)


if __name__ == "__main__":
    main()
