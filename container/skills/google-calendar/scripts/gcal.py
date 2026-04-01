#!/usr/bin/env python3
"""
Google Calendar CLI - Manage Google Calendar events via the REST API.
Uses OAuth2 device flow. Token stored at GCAL_TOKEN_PATH.
No external dependencies — stdlib only (urllib, json, os, sys).
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta


class TokenRevokedException(Exception):
    pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN_PATH = os.environ.get(
    "GCAL_TOKEN_PATH",
    "/workspace/group/.gcal-token.json"
)
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
DEVICE_URL   = "https://oauth2.googleapis.com/device/code"
SCOPE        = "https://www.googleapis.com/auth/calendar"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request(method, url, data=None, headers=None, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if body and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
        except Exception:
            err = {"raw": body}
        if err.get("error") == "invalid_grant":
            raise TokenRevokedException(err.get("error_description", "invalid_grant"))
        print(f"HTTP {e.code}: {json.dumps(err, indent=2)}", file=sys.stderr)
        sys.exit(1)


def _api_get(token, path, params=None):
    return _request("GET", f"{CALENDAR_API}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params)


def _api_post(token, path, payload):
    body = json.dumps(payload).encode()
    url = f"{CALENDAR_API}{path}"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _api_patch(token, path, payload):
    body = json.dumps(payload).encode()
    url = f"{CALENDAR_API}{path}"
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _api_delete(token, path):
    url = f"{CALENDAR_API}{path}"
    req = urllib.request.Request(url, method="DELETE")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)

# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _get_client():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Error: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.",
              file=sys.stderr)
        sys.exit(1)
    return client_id, client_secret


def _load_token():
    try:
        with open(TOKEN_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_token(tok):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(tok, f, indent=2)


def _refresh(tok):
    client_id, client_secret = _get_client()
    resp = _request("POST", TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    })
    tok["access_token"] = resp["access_token"]
    if "refresh_token" in resp:
        tok["refresh_token"] = resp["refresh_token"]
    tok["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=resp.get("expires_in", 3600))
    ).isoformat()
    _save_token(tok)
    return tok


AUTH_STATE_PATH = TOKEN_PATH + ".auth-state"


def _start_pending_auth():
    """Start device flow, save state file, print instructions, then exit.

    Called when the refresh token is revoked.  The container agent sees the
    printed URL+code and relays them to the user, then waits for the user to
    say they're done before calling `gcal.py auth-complete`.
    """
    import time
    client_id, _secret = _get_client()
    resp = _request("POST", DEVICE_URL, data={"client_id": client_id, "scope": SCOPE})
    state = {
        "device_code": resp["device_code"],
        "interval": resp.get("interval", 5),
        "deadline": time.time() + resp.get("expires_in", 1800),
    }
    os.makedirs(os.path.dirname(AUTH_STATE_PATH), exist_ok=True)
    with open(AUTH_STATE_PATH, "w") as f:
        json.dump(state, f)
    verify_url = resp.get("verification_url", "https://google.com/device")
    user_code  = resp["user_code"]
    print("Google Calendar needs re-authorisation.")
    print(f"  1. Open: {verify_url}")
    print(f"  2. Enter code: {user_code}")
    print("  3. Tell me when you're done and I'll complete the calendar operation.")
    sys.exit(2)


def _get_access_token():
    tok = _load_token()
    if not tok:
        if os.path.exists(AUTH_STATE_PATH):
            print("Auth in progress — complete the Google authorisation then reply here.",
                  file=sys.stderr)
            sys.exit(2)
        _start_pending_auth()
    expires_at = tok.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if datetime.now(timezone.utc) >= exp - timedelta(seconds=60):
                try:
                    tok = _refresh(tok)
                except TokenRevokedException:
                    _start_pending_auth()
        except TokenRevokedException:
            _start_pending_auth()
        except Exception:
            try:
                tok = _refresh(tok)
            except TokenRevokedException:
                _start_pending_auth()
    return tok["access_token"]

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_auth_complete(_args):
    """Complete a pending device-flow auth (after user visits the URL and enters the code)."""
    import time
    try:
        with open(AUTH_STATE_PATH) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No pending auth. Run:  gcal.py auth")
        sys.exit(1)

    if time.time() > state["deadline"]:
        try:
            os.unlink(AUTH_STATE_PATH)
        except OSError:
            pass
        print("Auth code expired. Run:  gcal.py auth  to start over.")
        sys.exit(1)

    client_id, client_secret = _get_client()
    # Try a few times in case the user just completed auth
    for attempt in range(4):
        try:
            tok_resp = _request("POST", TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": state["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            })
        except SystemExit:
            # authorization_pending — wait and retry
            if attempt < 3:
                time.sleep(state.get("interval", 5))
                continue
            print("Not authorised yet. Complete the Google auth then try again.")
            sys.exit(1)

        if "access_token" in tok_resp:
            tok_resp["expires_at"] = (
                datetime.now(timezone.utc)
                + timedelta(seconds=tok_resp.get("expires_in", 3600))
            ).isoformat()
            _save_token(tok_resp)
            try:
                os.unlink(AUTH_STATE_PATH)
            except OSError:
                pass
            print("Authorised. Google Calendar is ready — retry your request.")
            return

    print("Not authorised yet. Complete the Google auth then try again.")
    sys.exit(1)


def cmd_auth(_args):
    """Initiate OAuth2 device flow and save token."""
    client_id, client_secret = _get_client()

    # Step 1: request device code
    resp = _request("POST", DEVICE_URL, data={
        "client_id": client_id,
        "scope": SCOPE,
    })

    device_code  = resp["device_code"]
    user_code    = resp["user_code"]
    verify_url   = resp.get("verification_url", "https://google.com/device")
    interval     = resp.get("interval", 5)
    expires_in   = resp.get("expires_in", 1800)

    print(f"\nOpen this URL in your browser:\n  {verify_url}")
    print(f"\nEnter this code: {user_code}")
    print(f"\nWaiting for authorisation (expires in {expires_in}s) ...")

    # Step 2: poll for token
    import time
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        try:
            tok_resp = _request("POST", TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            })
        except SystemExit:
            continue  # authorization_pending — keep polling

        if "access_token" in tok_resp:
            tok_resp["expires_at"] = (
                datetime.now(timezone.utc)
                + timedelta(seconds=tok_resp.get("expires_in", 3600))
            ).isoformat()
            _save_token(tok_resp)
            print(f"\nAuthenticated. Token saved to {TOKEN_PATH}")
            return

    print("Timed out waiting for authorisation.", file=sys.stderr)
    sys.exit(1)


def cmd_calendars(_args):
    """List all accessible calendars."""
    token = _get_access_token()
    data = _api_get(token, "/users/me/calendarList")
    items = data.get("items", [])
    if not items:
        print("No calendars found.")
        return
    for cal in items:
        primary = " [PRIMARY]" if cal.get("primary") else ""
        print(f"{cal['id']}{primary}")
        print(f"  Name: {cal.get('summary', '(no name)')}")
        print(f"  Access: {cal.get('accessRole', '?')}")
        print()


def _fmt_event(ev):
    start = ev.get("start", {})
    end   = ev.get("end", {})
    start_str = start.get("dateTime", start.get("date", "?"))
    end_str   = end.get("dateTime", end.get("date", "?"))
    try:
        dt = datetime.fromisoformat(start_str)
        start_str = dt.strftime("%a %d %b %Y  %H:%M")
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(end_str)
        end_str = dt.strftime("%H:%M")
    except Exception:
        pass
    loc   = f"  Location: {ev['location']}" if ev.get("location") else ""
    desc  = f"  Desc: {ev['description'][:80]}" if ev.get("description") else ""
    return (
        f"[{ev.get('id','?')}]\n"
        f"  {ev.get('summary', '(no title)')}\n"
        f"  {start_str} → {end_str}"
        + (f"\n{loc}" if loc else "")
        + (f"\n{desc}" if desc else "")
    )


def cmd_list(args):
    """List upcoming events.
    Usage: list [--calendar calendarId] [--days N] [--max N]
    """
    calendar_id = "primary"
    days = 7
    max_results = 20

    i = 0
    while i < len(args):
        if args[i] == "--calendar" and i + 1 < len(args):
            calendar_id = args[i + 1]; i += 2
        elif args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1]); i += 2
        elif args[i] == "--max" and i + 1 < len(args):
            max_results = int(args[i + 1]); i += 2
        else:
            i += 1

    token = _get_access_token()
    now   = datetime.now(timezone.utc)
    end   = now + timedelta(days=days)
    data  = _api_get(token, f"/calendars/{urllib.parse.quote(calendar_id)}/events", params={
        "timeMin": now.isoformat(),
        "timeMax": end.isoformat(),
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    })
    items = data.get("items", [])
    if not items:
        print(f"No events in the next {days} day(s).")
        return
    print(f"Upcoming events ({len(items)}):\n")
    for ev in items:
        print(_fmt_event(ev))
        print()


def cmd_today(args):
    """Show today's events. Usage: today [--calendar calendarId]"""
    calendar_id = "primary"
    i = 0
    while i < len(args):
        if args[i] == "--calendar" and i + 1 < len(args):
            calendar_id = args[i + 1]; i += 2
        else:
            i += 1

    token = _get_access_token()
    now   = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=1)
    data  = _api_get(token, f"/calendars/{urllib.parse.quote(calendar_id)}/events", params={
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
    })
    items = data.get("items", [])
    print(f"Today ({now.strftime('%a %d %b %Y')}):\n")
    if not items:
        print("  No events today.")
        return
    for ev in items:
        print(_fmt_event(ev))
        print()


def cmd_create(args):
    """Create an event.
    Usage: create <title> --start <ISO> --end <ISO>
                  [--calendar calendarId] [--location <text>]
                  [--description <text>] [--timezone <tz>]
    Example: create "Team standup" --start 2026-03-11T09:00:00 --end 2026-03-11T09:30:00
    """
    if not args:
        print("Usage: create <title> --start <ISO> --end <ISO> [options]")
        sys.exit(1)

    calendar_id = "primary"
    tz = "Australia/Sydney"
    title = location = description = start = end = None

    # Title is the first positional arg
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--start" and i + 1 < len(args):
            start = args[i + 1]; i += 2
        elif args[i] == "--end" and i + 1 < len(args):
            end = args[i + 1]; i += 2
        elif args[i] == "--calendar" and i + 1 < len(args):
            calendar_id = args[i + 1]; i += 2
        elif args[i] == "--location" and i + 1 < len(args):
            location = args[i + 1]; i += 2
        elif args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]; i += 2
        elif args[i] == "--timezone" and i + 1 < len(args):
            tz = args[i + 1]; i += 2
        else:
            positional.append(args[i]); i += 1

    title = " ".join(positional) if positional else None
    if not title or not start or not end:
        print("Error: title, --start, and --end are required.")
        sys.exit(1)

    event = {
        "summary": title,
        "start": {"dateTime": start, "timeZone": tz},
        "end":   {"dateTime": end,   "timeZone": tz},
    }
    if location:
        event["location"] = location
    if description:
        event["description"] = description

    token = _get_access_token()
    result = _api_post(token, f"/calendars/{urllib.parse.quote(calendar_id)}/events", event)
    print(f"Created: {result.get('summary')} [{result.get('id')}]")
    print(f"  Link: {result.get('htmlLink', 'n/a')}")


def cmd_update(args):
    """Update an event.
    Usage: update <eventId> [--calendar calendarId] [--title <text>]
                  [--start <ISO>] [--end <ISO>] [--location <text>]
                  [--description <text>] [--timezone <tz>]
    """
    if not args:
        print("Usage: update <eventId> [options]")
        sys.exit(1)

    event_id    = args[0]
    calendar_id = "primary"
    tz          = "Australia/Sydney"
    patch       = {}

    i = 1
    while i < len(args):
        if args[i] == "--calendar" and i + 1 < len(args):
            calendar_id = args[i + 1]; i += 2
        elif args[i] == "--title" and i + 1 < len(args):
            patch["summary"] = args[i + 1]; i += 2
        elif args[i] == "--start" and i + 1 < len(args):
            patch.setdefault("start", {})["dateTime"] = args[i + 1]
            patch["start"]["timeZone"] = tz; i += 2
        elif args[i] == "--end" and i + 1 < len(args):
            patch.setdefault("end", {})["dateTime"] = args[i + 1]
            patch["end"]["timeZone"] = tz; i += 2
        elif args[i] == "--location" and i + 1 < len(args):
            patch["location"] = args[i + 1]; i += 2
        elif args[i] == "--description" and i + 1 < len(args):
            patch["description"] = args[i + 1]; i += 2
        elif args[i] == "--timezone" and i + 1 < len(args):
            tz = args[i + 1]; i += 2
        else:
            i += 1

    if not patch:
        print("Nothing to update.")
        sys.exit(1)

    token  = _get_access_token()
    result = _api_patch(
        token,
        f"/calendars/{urllib.parse.quote(calendar_id)}/events/{urllib.parse.quote(event_id)}",
        patch
    )
    print(f"Updated: {result.get('summary')} [{result.get('id')}]")


def cmd_delete(args):
    """Delete an event.
    Usage: delete <eventId> [--calendar calendarId]
    """
    if not args:
        print("Usage: delete <eventId> [--calendar calendarId]")
        sys.exit(1)

    event_id    = args[0]
    calendar_id = "primary"
    i = 1
    while i < len(args):
        if args[i] == "--calendar" and i + 1 < len(args):
            calendar_id = args[i + 1]; i += 2
        else:
            i += 1

    token = _get_access_token()
    _api_delete(
        token,
        f"/calendars/{urllib.parse.quote(calendar_id)}/events/{urllib.parse.quote(event_id)}"
    )
    print(f"Deleted event: {event_id}")


def cmd_search(args):
    """Search events by keyword.
    Usage: search <query> [--calendar calendarId] [--max N]
    """
    if not args:
        print("Usage: search <query> [--calendar calendarId] [--max N]")
        sys.exit(1)

    calendar_id = "primary"
    max_results = 20
    query_parts = []

    i = 0
    while i < len(args):
        if args[i] == "--calendar" and i + 1 < len(args):
            calendar_id = args[i + 1]; i += 2
        elif args[i] == "--max" and i + 1 < len(args):
            max_results = int(args[i + 1]); i += 2
        else:
            query_parts.append(args[i]); i += 1

    query = " ".join(query_parts)
    token = _get_access_token()
    data  = _api_get(token, f"/calendars/{urllib.parse.quote(calendar_id)}/events", params={
        "q": query,
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": datetime.now(timezone.utc).isoformat(),
    })
    items = data.get("items", [])
    if not items:
        print(f"No events found for: {query}")
        return
    print(f"Found {len(items)} event(s) matching '{query}':\n")
    for ev in items:
        print(_fmt_event(ev))
        print()

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS = {
    "auth":          cmd_auth,
    "auth-complete": cmd_auth_complete,
    "calendars":     cmd_calendars,
    "list":      cmd_list,
    "today":     cmd_today,
    "create":    cmd_create,
    "update":    cmd_update,
    "delete":    cmd_delete,
    "search":    cmd_search,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Google Calendar CLI")
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        print()
        print("First-time setup:")
        print("  gcal.py auth")
        print()
        print("Examples:")
        print("  gcal.py today")
        print("  gcal.py list --days 14")
        print('  gcal.py create "Dentist" --start 2026-03-12T10:00:00 --end 2026-03-12T11:00:00')
        print('  gcal.py search "standup"')
        print('  gcal.py update <eventId> --title "New Title" --start 2026-03-12T11:00:00 --end 2026-03-12T12:00:00')
        print('  gcal.py delete <eventId>')
        print("  gcal.py calendars")
        sys.exit(1 if len(sys.argv) < 2 else 0)

    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
