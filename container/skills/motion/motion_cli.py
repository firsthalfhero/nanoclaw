#!/usr/bin/env python3
"""
Motion CLI - Command-line interface for Motion task management
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta

# Import Motion modules from the mounted location (in container) or local (on host)
motion_path = os.path.join('/opt', 'motion-scheduler', 'motion')
if not os.path.exists(motion_path):
    # Fallback to Windows path if running on host
    motion_path = r'C:\Users\George\Documents\projects\motion-scheduler\motion'
sys.path.insert(0, motion_path)

try:
    from motion_create import create_task, delete_task
    from motion_search import search_tasks, display_tasks
    from motion_config import API_BASE_URL, WORKSPACE_ID
except ImportError as e:
    print(f"Error importing Motion modules: {e}", file=sys.stderr)
    print("Make sure the motion-scheduler project is available", file=sys.stderr)
    sys.exit(1)

# Import requests for list functionality
import requests
import time


def request_with_retry(method, url, max_retries=4, base_delay=2.0, **kwargs):
    """Make an HTTP request with exponential backoff on 429 rate limit responses."""
    for attempt in range(max_retries):
        time.sleep(1.0)  # Base rate limit delay between all requests
        response = requests.request(method, url, **kwargs)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        retry_after = response.headers.get('Retry-After')
        wait = float(retry_after) if retry_after else base_delay * (2 ** attempt)
        print(f"Rate limited. Waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}...", file=sys.stderr)
        time.sleep(wait)
    # Final attempt
    time.sleep(1.0)
    response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response


def get_api_key():
    """Get Motion API key from environment"""
    api_key = os.getenv('MOTION_API_KEY')
    if not api_key:
        print("Error: MOTION_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    return api_key


def get_workspace_id():
    """Get Motion workspace ID from environment or config"""
    return os.getenv('MOTION_WORKSPACE_ID', WORKSPACE_ID)


def list_tasks(limit=10, workspace_id=None):
    """List recent tasks from Motion"""
    if not workspace_id:
        workspace_id = get_workspace_id()

    api_key = get_api_key()
    url = f"{API_BASE_URL}/tasks"

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    params = {
        "workspaceId": workspace_id,
    }

    try:
        response = request_with_retry('GET', url, headers=headers, params=params)
        data = response.json()
        tasks = data.get("tasks", [])[:limit]

        # Output JSON for programmatic use
        print(json.dumps(tasks, indent=2))
        return tasks

    except requests.exceptions.RequestException as e:
        print(f"Error listing tasks: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)


def cmd_search(args):
    """Search for tasks"""
    workspace_id = get_workspace_id()
    tasks = search_tasks(args.keyword, workspace_id=workspace_id)

    if args.json:
        print(json.dumps(tasks, indent=2))
    else:
        display_tasks(tasks)

    return 0 if tasks else 1


def cmd_create(args):
    """Create a new task"""
    workspace_id = get_workspace_id()

    # Calculate due date if --due-days is provided
    due_date = None
    if args.due_days:
        due_date = (datetime.now() + timedelta(days=args.due_days)).isoformat()

    # Parse labels
    labels = None
    if args.labels:
        labels = [l.strip() for l in args.labels.split(',')]

    task = create_task(
        name=args.name,
        workspace_id=workspace_id,
        description=args.description,
        duration=args.duration,
        priority=args.priority.upper(),
        labels=labels,
        due_date=due_date
    )

    if task and args.json:
        print(json.dumps(task, indent=2))

    return 0 if task else 1


def cmd_list(args):
    """List tasks"""
    workspace_id = get_workspace_id()
    tasks = list_tasks(limit=args.limit, workspace_id=workspace_id)
    return 0 if tasks else 1


def cmd_delete(args):
    """Delete a task"""
    success = delete_task(args.task_id)
    return 0 if success else 1


def cmd_bulk_update_start_date(args):
    """Search for multiple tasks by name and set their start date in one pass."""
    workspace_id = get_workspace_id()
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    results = {"updated": [], "not_found": [], "failed": []}

    for name in args.names:
        name = name.strip()
        print(f"\n--- Processing: {name} ---", file=sys.stderr)

        # Search
        tasks = search_tasks(name, workspace_id=workspace_id)
        if not tasks:
            print(f"  Not found: {name}", file=sys.stderr)
            results["not_found"].append(name)
            time.sleep(args.delay)
            continue

        task = tasks[0]
        task_id = task.get("id")
        print(f"  Found: {task_id}", file=sys.stderr)

        # Update
        time.sleep(args.delay)
        update_data = {"autoScheduled": {"startDate": args.start_date, "deadlineType": "SOFT", "schedule": "Work Hours"}}
        try:
            url = f"{API_BASE_URL}/tasks/{task_id}"
            request_with_retry('PATCH', url, headers=headers, json=update_data)
            print(f"  Updated start date to {args.start_date}", file=sys.stderr)
            results["updated"].append(name)
        except requests.exceptions.RequestException as e:
            print(f"  Failed to update: {e}", file=sys.stderr)
            results["failed"].append(name)

        time.sleep(args.delay)

    print(json.dumps(results, indent=2))
    return 0 if not results["failed"] else 1


def cmd_update(args):
    """Update a task's start date and/or priority"""
    api_key = get_api_key()
    url = f"{API_BASE_URL}/tasks/{args.task_id}"

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    update_data = {}

    if args.start_date:
        update_data["autoScheduled"] = {
            "startDate": args.start_date,
            "deadlineType": "SOFT",
            "schedule": "Work Hours"
        }

    if args.priority:
        update_data["priority"] = args.priority.upper()

    if not update_data:
        print("Error: no update fields provided", file=sys.stderr)
        return 1

    try:
        response = request_with_retry('PATCH', url, headers=headers, json=update_data)
        task = response.json()
        if args.json:
            print(json.dumps(task, indent=2))
        else:
            print(f"Updated task: {task.get('name', args.task_id)}")
        return 0
    except requests.exceptions.RequestException as e:
        print(f"Error updating task: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Motion CLI - Manage tasks in Motion',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--json', action='store_true',
                       help='Output JSON format')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Search command
    search_parser = subparsers.add_parser('search',
                                         help='Search for tasks')
    search_parser.add_argument('keyword',
                              help='Search keyword')

    # Create command
    create_parser = subparsers.add_parser('create',
                                         help='Create a new task')
    create_parser.add_argument('name',
                              help='Task name')
    create_parser.add_argument('--description',
                              help='Task description')
    create_parser.add_argument('--duration', type=int, default=30,
                              help='Duration in minutes (default: 30)')
    create_parser.add_argument('--priority', default='MEDIUM',
                              choices=['ASAP', 'HIGH', 'MEDIUM', 'LOW'],
                              help='Task priority (default: MEDIUM)')
    create_parser.add_argument('--due-days', type=int,
                              help='Due in N days from now')
    create_parser.add_argument('--labels',
                              help='Comma-separated labels')

    # List command
    list_parser = subparsers.add_parser('list',
                                       help='List tasks')
    list_parser.add_argument('--limit', type=int, default=10,
                            help='Number of tasks to list (default: 10)')

    # Delete command
    delete_parser = subparsers.add_parser('delete',
                                         help='Delete a task')
    delete_parser.add_argument('task_id',
                              help='Task ID to delete')

    # Bulk update start date command
    bulk_parser = subparsers.add_parser('bulk-update-start-date',
                                        help='Set start date on multiple tasks by name (one API session)')
    bulk_parser.add_argument('names', nargs='+',
                             help='Task names to update (exact or partial match)')
    bulk_parser.add_argument('--start-date', required=True,
                             help='Start date (YYYY-MM-DD)')
    bulk_parser.add_argument('--delay', type=float, default=3.0,
                             help='Seconds to wait between tasks (default: 3)')

    # Update command
    update_parser = subparsers.add_parser('update',
                                         help='Update a task (start date, priority)')
    update_parser.add_argument('task_id',
                              help='Task ID to update')
    update_parser.add_argument('--start-date',
                              help='Start date (YYYY-MM-DD) for auto-scheduling')
    update_parser.add_argument('--priority',
                              choices=['ASAP', 'HIGH', 'MEDIUM', 'LOW'],
                              help='Task priority')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to command handlers
    if args.command == 'search':
        return cmd_search(args)
    elif args.command == 'create':
        return cmd_create(args)
    elif args.command == 'list':
        return cmd_list(args)
    elif args.command == 'delete':
        return cmd_delete(args)
    elif args.command == 'update':
        return cmd_update(args)
    elif args.command == 'bulk-update-start-date':
        return cmd_bulk_update_start_date(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
