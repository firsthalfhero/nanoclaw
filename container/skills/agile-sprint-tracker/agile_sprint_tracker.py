#!/usr/bin/env python3
"""
Nanoclaw Skill: agile-sprint-tracker

Bridge between Nanoclaw's LLM and the agile-sprint-tracker REST API on hp-server.
Never caches state — every call goes to the API. Conversation history is not a data source.

Calling convention: Action-based dispatch via ACTION_MAP
Entry point: main() reads action from CLI args or stdin, dispatches to action handler
"""

import os
import json
import sys
import requests
from typing import Any, Dict, Optional
import urllib3
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[AGILE-SKILL] %(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Suppress SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
API_BASE = os.getenv("AGILE_API_BASE", "https://agilelife.home")
REQUEST_TIMEOUT = int(os.getenv("AGILE_API_TIMEOUT", "10"))
logger.debug(f"API_BASE: {API_BASE}, TIMEOUT: {REQUEST_TIMEOUT}")

# HTTP Methods
GET = "GET"
POST = "POST"
PATCH = "PATCH"
DELETE = "DELETE"


def call_api(
    method: str,
    endpoint: str,
    payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Call the agile-sprint-tracker API and return structured response.

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        endpoint: API endpoint path (e.g., "/sprint/current")
        payload: Request body (for POST/PATCH)

    Returns:
        {
            "ok": bool,
            "status": int,
            "data": dict | None,
            "error": str | None
        }
    """
    url = f"{API_BASE}{endpoint}"
    logger.debug(f"{method} {url}")

    try:
        response = requests.request(
            method,
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            verify=False
        )

        # Try to parse JSON response
        try:
            data = response.json()
        except:
            data = response.text

        logger.debug(f"Response: {response.status_code}")
        return {
            "ok": response.ok,
            "status": response.status_code,
            "data": data if response.ok else None,
            "error": (
                data.get("error") if isinstance(data, dict)
                else f"HTTP {response.status_code}: {data}"
            ) if not response.ok else None
        }

    except requests.exceptions.ConnectionError as e:
        logger.error(f"ConnectionError: {e}")
        return {
            "ok": False,
            "status": 0,
            "data": None,
            "error": "Cannot reach agile-sprint-tracker API — is hp-server running?"
        }

    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout: {e}")
        return {
            "ok": False,
            "status": 0,
            "data": None,
            "error": f"API request timeout (>{REQUEST_TIMEOUT}s) — hp-server may be slow"
        }

    except Exception as e:
        logger.error(f"Exception: {type(e).__name__}: {e}")
        return {
            "ok": False,
            "status": 0,
            "data": None,
            "error": f"Unexpected error: {str(e)}"
        }


# ═══════════════════════════════════════════════════════════════════════════
# SPRINT ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_sprint() -> Dict[str, Any]:
    """Get current active sprint or null if none."""
    return call_api(GET, "/sprint/current")


def start_sprint(goal_item_ids: list) -> Dict[str, Any]:
    """
    Start new sprint with selected goals.

    Args:
        goal_item_ids: List of UUID strings for sprint goals (1-5 items)
    """
    return call_api(POST, "/sprint/start", {"goalItemIds": goal_item_ids})


def update_sprint_state(sprint_id: str, state: str) -> Dict[str, Any]:
    """
    Transition sprint to new state.

    Args:
        sprint_id: Sprint UUID
        state: Target state (active, mid-review, retro, paused)
    """
    return call_api(PATCH, "/sprint/state", {
        "sprintId": sprint_id,
        "state": state
    })


def close_sprint(sprint_id: str) -> Dict[str, Any]:
    """Close sprint, defer incomplete items, archive."""
    return call_api(POST, "/sprint/close", {"sprintId": sprint_id})


def update_sprint_goal(goal_id: str, completed_at: Optional[str] = None) -> Dict[str, Any]:
    """
    Mark sprint goal as complete/incomplete.

    Args:
        goal_id: Sprint goal UUID
        completed_at: ISO 8601 timestamp (complete) or None (incomplete)
    """
    return call_api(PATCH, f"/sprint/goal/{goal_id}", {
        "completedAt": completed_at
    })


# ═══════════════════════════════════════════════════════════════════════════
# BACKLOG ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_backlog() -> Dict[str, Any]:
    """Get all backlog items grouped by status."""
    return call_api(GET, "/backlog")


def add_backlog_item(
    item_type: str,
    title: str,
    life_area: str,
    priority: str = "medium",
    sub_area: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add new backlog item.

    Args:
        item_type: epic, story, or task
        title: Item title
        life_area: health, next-chapter, or home-family
        priority: low, medium, high, or asap
        sub_area: Optional sub-area (e.g., gym, learning)
        description: Optional long-form description
    """
    payload = {
        "type": item_type,
        "title": title,
        "lifeArea": life_area,
        "priority": priority,
    }
    if sub_area:
        payload["subArea"] = sub_area
    if description:
        payload["description"] = description

    return call_api(POST, "/backlog", payload)


def update_backlog_item(item_id: str, **fields) -> Dict[str, Any]:
    """
    Update backlog item.

    Args:
        item_id: Item UUID
        **fields: Any updatable fields (status, title, description, priority, etc.)
    """
    return call_api(PATCH, f"/backlog/{item_id}", fields)


def delete_backlog_item(item_id: str, reason: str = "User dropped this item") -> Dict[str, Any]:
    """
    Soft-delete backlog item.

    Args:
        item_id: Item UUID
        reason: Reason for deletion
    """
    return update_backlog_item(item_id, status="dropped", droppedReason=reason)


def decompose_epic(epic_id: str, child_stories: list) -> Dict[str, Any]:
    """
    Decompose epic into child stories.

    Args:
        epic_id: Epic item UUID
        child_stories: List of {title, description?, subArea?, priority?}
    """
    return call_api(POST, f"/backlog/{epic_id}/decompose", {
        "stories": child_stories
    })


def add_backlog_items_batch(items_list: list) -> Dict[str, Any]:
    """
    Add multiple backlog items one by one.

    Args:
        items_list: List of items, each with {type, title, life_area, priority?, sub_area?, description?}

    Returns:
        {
            "ok": bool (True only if all items added successfully),
            "total": int,
            "added": int,
            "failed": int,
            "items": [result for each add],
            "error": str or None
        }
    """
    results = []
    added_count = 0

    for item in items_list:
        result = add_backlog_item(
            item_type=item.get("type"),
            title=item.get("title"),
            life_area=item.get("life_area"),
            priority=item.get("priority", "medium"),
            sub_area=item.get("sub_area"),
            description=item.get("description")
        )
        results.append(result)
        if result["ok"]:
            added_count += 1

    return {
        "ok": added_count == len(items_list),
        "total": len(items_list),
        "added": added_count,
        "failed": len(items_list) - added_count,
        "items": results,
        "error": None if added_count == len(items_list) else "Some items failed to add"
    }


# ═══════════════════════════════════════════════════════════════════════════
# MOBILITY ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def log_mobility(done: bool) -> Dict[str, Any]:
    """
    Log today's mobility.

    Args:
        done: True if completed, False if missed
    """
    return call_api(POST, "/mobility/log", {"done": done})


def get_mobility_status() -> Dict[str, Any]:
    """Get mobility streak and sprint history."""
    return call_api(GET, "/mobility/status")


# ═══════════════════════════════════════════════════════════════════════════
# CEREMONY ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_refinement_data() -> Dict[str, Any]:
    """Get data for backlog refinement ceremony."""
    return call_api(GET, "/ceremony/refinement")


def get_mid_sprint_data() -> Dict[str, Any]:
    """Get data for mid-sprint review ceremony."""
    return call_api(GET, "/ceremony/mid-sprint")


def get_retro_data() -> Dict[str, Any]:
    """Get data for retrospective ceremony."""
    return call_api(GET, "/ceremony/retro")


def save_retro_responses(responses: dict) -> Dict[str, Any]:
    """
    Submit retrospective responses.

    Args:
        responses: {
            "whatWentWell": [...],
            "improvements": [...],
            "blockers": [...],
            "nextSprintFocus": "..." (optional)
        }
    """
    return call_api(POST, "/ceremony/retro", {"responses": responses})


# ═══════════════════════════════════════════════════════════════════════════
# CHECK-IN ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_morning_checkin() -> Dict[str, Any]:
    """Get morning check-in data (sprint status, mobility reminder)."""
    return call_api(GET, "/cron/morning")


def get_evening_checkin() -> Dict[str, Any]:
    """Get evening check-in data (ask for mobility, escalate if missed)."""
    return call_api(GET, "/cron/evening")


# ═══════════════════════════════════════════════════════════════════════════
# HISTORY ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_history() -> Dict[str, Any]:
    """Get all closed sprints."""
    return call_api(GET, "/history")


def get_sprint_history(sprint_id: str) -> Dict[str, Any]:
    """Get closed sprint details."""
    return call_api(GET, f"/history/{sprint_id}")


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_full_state() -> Dict[str, Any]:
    """
    Get full state: sprint + backlog + mobility in one call.
    Used at start of every ceremony and check-in.
    """
    sprint = call_api(GET, "/sprint/current")
    backlog = call_api(GET, "/backlog")
    mobility = call_api(GET, "/mobility/status")

    # Backlog must succeed; sprint/mobility can be null if no active sprint
    backlog_ok = backlog["ok"]

    errors = []
    if not sprint["ok"]:
        errors.append(f"sprint={sprint.get('error')}")
    if not backlog["ok"]:
        errors.append(f"backlog={backlog.get('error')}")
    if not mobility["ok"]:
        errors.append(f"mobility={mobility.get('error')}")

    return {
        "ok": backlog_ok,
        "status": 200 if backlog_ok else 500,
        "data": {
            "sprint": sprint.get("data"),
            "backlog": backlog.get("data"),
            "mobility": mobility.get("data")
        },
        "error": ", ".join(errors) if errors and not backlog_ok else None
    }


def triage_and_add_item(
    item_type: str,
    title: str,
    life_area: str,
    priority: str = "medium",
    sub_area: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add item and return updated backlog in one call.
    Used for mid-sprint item additions.
    """
    # Add the item
    add_result = add_backlog_item(
        item_type=item_type,
        title=title,
        life_area=life_area,
        priority=priority,
        sub_area=sub_area,
        description=description
    )

    if not add_result["ok"]:
        return add_result

    # Get updated backlog
    backlog = call_api(GET, "/backlog")

    return {
        "ok": backlog["ok"],
        "status": backlog["status"],
        "data": {
            "item": add_result.get("data"),
            "backlog": backlog.get("data")
        },
        "error": backlog.get("error")
    }


def complete_sprint(responses: dict) -> Dict[str, Any]:
    """
    Save retro responses and close sprint in one call.
    Used at end of retrospective.
    """
    # Get current sprint first
    sprint_result = call_api(GET, "/sprint/current")
    if not sprint_result["ok"]:
        return sprint_result

    sprint_id = sprint_result["data"]["id"]

    # Save retro
    retro = call_api(POST, "/ceremony/retro", {"responses": responses})
    if not retro["ok"]:
        return retro

    # Close sprint
    close = call_api(POST, "/sprint/close", {"sprintId": sprint_id})

    return {
        "ok": close["ok"],
        "status": close["status"],
        "data": {
            "retro": retro.get("data"),
            "archivedSprint": close.get("data")
        },
        "error": close.get("error")
    }


# ═══════════════════════════════════════════════════════════════════════════
# ACTION DISPATCH
# ═══════════════════════════════════════════════════════════════════════════

ACTION_MAP = {
    # Sprint
    "get_sprint": lambda args: get_sprint(),
    "start_sprint": lambda args: start_sprint(args.get("goal_item_ids", [])),
    "update_sprint_state": lambda args: update_sprint_state(
        args.get("sprint_id"),
        args.get("state")
    ),
    "close_sprint": lambda args: close_sprint(args.get("sprint_id")),
    "update_sprint_goal": lambda args: update_sprint_goal(
        args.get("goal_id"),
        args.get("completed_at")
    ),

    # Backlog
    "get_backlog": lambda args: get_backlog(),
    "add_backlog_item": lambda args: add_backlog_item(
        args.get("type"),
        args.get("title"),
        args.get("life_area"),
        args.get("priority", "medium"),
        args.get("sub_area"),
        args.get("description")
    ),
    "add_backlog_items_batch": lambda args: add_backlog_items_batch(args.get("items_list", [])),
    "update_backlog_item": lambda args: update_backlog_item(
        args.get("item_id"),
        **{k: v for k, v in args.items() if k != "item_id" and k != "action"}
    ),
    "delete_backlog_item": lambda args: delete_backlog_item(
        args.get("item_id"),
        args.get("reason", "User dropped this item")
    ),
    "decompose_epic": lambda args: decompose_epic(
        args.get("epic_id"),
        args.get("child_stories", [])
    ),

    # Mobility
    "log_mobility": lambda args: log_mobility(args.get("done", False)),
    "get_mobility_status": lambda args: get_mobility_status(),

    # Ceremonies
    "get_refinement_data": lambda args: get_refinement_data(),
    "get_mid_sprint_data": lambda args: get_mid_sprint_data(),
    "get_retro_data": lambda args: get_retro_data(),
    "save_retro_responses": lambda args: save_retro_responses(args.get("responses", {})),

    # Check-ins
    "get_morning_checkin": lambda args: get_morning_checkin(),
    "get_evening_checkin": lambda args: get_evening_checkin(),

    # History
    "get_history": lambda args: get_history(),
    "get_sprint_history": lambda args: get_sprint_history(args.get("sprint_id")),

    # Composites
    "get_full_state": lambda args: get_full_state(),
    "triage_and_add_item": lambda args: triage_and_add_item(
        args.get("type"),
        args.get("title"),
        args.get("life_area"),
        args.get("priority", "medium"),
        args.get("sub_area"),
        args.get("description")
    ),
    "complete_sprint": lambda args: complete_sprint(args.get("responses", {})),
}


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """
    Entry point: dispatch action from CLI args or stdin.

    Usage:
        python agile_sprint_tracker.py --action get_sprint
        python agile_sprint_tracker.py --action start_sprint --goal_item_ids '["uuid1","uuid2"]'
        echo '{"action": "get_sprint"}' | python agile_sprint_tracker.py
    """

    # Try to parse from CLI args first
    action = None
    args = {}

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--action" and i + 1 < len(sys.argv) - 1:
            action = sys.argv[i + 2]
        elif arg.startswith("--") and i + 1 < len(sys.argv) - 1:
            key = arg[2:]  # strip --
            value = sys.argv[i + 2]
            # Try to parse as JSON, fallback to string
            try:
                args[key] = json.loads(value)
            except:
                args[key] = value

    # If no action from CLI, try stdin
    if not action:
        try:
            input_data = json.loads(sys.stdin.read())
            action = input_data.get("action")
            args = input_data.get("params", {})
        except:
            pass

    # Log the action
    logger.info(f"Action: {action}, Args: {args}")

    # Dispatch or error
    if action and action in ACTION_MAP:
        try:
            result = ACTION_MAP[action](args)
            logger.info(f"Action succeeded: {action}")
        except Exception as e:
            logger.error(f"Action failed: {action}, Error: {type(e).__name__}: {e}")
            result = {
                "ok": False,
                "status": 500,
                "data": None,
                "error": f"Action failed: {str(e)}"
            }
    else:
        logger.warning(f"Unknown action: {action}")
        result = {
            "ok": False,
            "status": 400,
            "data": None,
            "error": f"Unknown action: {action}. Available: {', '.join(ACTION_MAP.keys())}"
        }

    # Output JSON response
    print(json.dumps(result, indent=2))
    logger.debug(f"Response: {result}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
