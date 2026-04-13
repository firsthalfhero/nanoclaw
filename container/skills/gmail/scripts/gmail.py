#!/usr/bin/env python3
"""
Gmail skill script — label listing, inbox triage, and basic actions.
Uses OAuth2 device flow. Token stored at GMAIL_TOKEN_PATH.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import base64
import re
from datetime import datetime, timezone

GMAIL_TOKEN_PATH = os.environ.get(
    "GMAIL_TOKEN_PATH",
    "/workspace/group/.gmail-token.json"
)
AUTH_STATE_PATH = GMAIL_TOKEN_PATH + ".auth-state"


class TokenRevokedException(Exception):
    pass
TOKEN_URL   = "https://oauth2.googleapis.com/token"
DEVICE_URL  = "https://oauth2.googleapis.com/device/code"
SCOPE       = " ".join([
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
])
BASE_URL    = "https://gmail.googleapis.com/gmail/v1/users/me"


# ── HTTP helpers ────────────────────────────────────────────────────────────

def _api_get(token, path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def _api_post(token, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + path, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def _api_patch(token, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + path, data=data, method="PATCH")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# ── Auth helpers ─────────────────────────────────────────────────────────────

def _get_client():
    client_id     = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Error: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set.", file=sys.stderr)
        sys.exit(1)
    return client_id, client_secret

def _load_token():
    if os.path.exists(GMAIL_TOKEN_PATH):
        with open(GMAIL_TOKEN_PATH) as f:
            return json.load(f)
    return None

def _save_token(tok):
    with open(GMAIL_TOKEN_PATH, "w") as f:
        json.dump(tok, f, indent=2)

def _refresh_token(tok):
    client_id, client_secret = _get_client()
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        try:
            err = json.loads(err_body)
        except Exception:
            err = {}
        if err.get("error") == "invalid_grant":
            raise TokenRevokedException(err.get("error_description", "invalid_grant"))
        print(f"Token refresh failed: {err_body}", file=sys.stderr)
        sys.exit(1)
    tok["access_token"] = resp["access_token"]
    if "refresh_token" in resp:
        tok["refresh_token"] = resp["refresh_token"]
    tok["expires_at"] = time.time() + resp.get("expires_in", 3600) - 60
    _save_token(tok)
    return tok["access_token"]


def _start_pending_auth():
    """Start device flow, save state, print instructions, exit immediately."""
    client_id, _ = _get_client()
    payload = urllib.parse.urlencode({"client_id": client_id, "scope": SCOPE}).encode()
    req = urllib.request.Request(DEVICE_URL, data=payload, method="POST")
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
    state = {
        "device_code": resp["device_code"],
        "interval":    resp.get("interval", 5),
        "deadline":    time.time() + resp.get("expires_in", 1800),
    }
    os.makedirs(os.path.dirname(AUTH_STATE_PATH), exist_ok=True)
    with open(AUTH_STATE_PATH, "w") as f:
        json.dump(state, f)
    verify_url = resp.get("verification_url", "https://google.com/device")
    user_code  = resp["user_code"]
    print("Gmail needs re-authorisation.")
    print(f"  1. Open: {verify_url}")
    print(f"  2. Enter code: {user_code}")
    print("  3. Tell me when you're done and I'll complete the operation.")
    sys.exit(2)


def _get_access_token():
    tok = _load_token()
    if not tok:
        if os.path.exists(AUTH_STATE_PATH):
            print("Auth in progress — complete the Google authorisation then reply here.",
                  file=sys.stderr)
            sys.exit(2)
        _start_pending_auth()
    expires_at = tok.get("expires_at", 0)
    # Handle ISO string format (from web auth flow) or float (from device flow)
    if isinstance(expires_at, str):
        try:
            dt = datetime.fromisoformat(expires_at)
            expires_at = dt.timestamp()
        except Exception:
            expires_at = 0
    if time.time() >= expires_at:
        try:
            return _refresh_token(tok)
        except TokenRevokedException:
            _start_pending_auth()
    return tok["access_token"]


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_auth_complete(_args):
    """Complete a pending device-flow auth after user visits the URL."""
    try:
        with open(AUTH_STATE_PATH) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No pending auth. Run:  gmail.py auth")
        sys.exit(1)

    if time.time() > state["deadline"]:
        try:
            os.unlink(AUTH_STATE_PATH)
        except OSError:
            pass
        print("Auth code expired. Run:  gmail.py auth  to start over.")
        sys.exit(1)

    client_id, client_secret = _get_client()
    for attempt in range(4):
        poll_payload = urllib.parse.urlencode({
            "client_id":     client_id,
            "client_secret": client_secret,
            "device_code":   state["device_code"],
            "grant_type":    "urn:ietf:params:oauth:grant-type:device_code",
        }).encode()
        try:
            req = urllib.request.Request(TOKEN_URL, data=poll_payload, method="POST")
            with urllib.request.urlopen(req) as r:
                tok_resp = json.loads(r.read())
        except urllib.error.HTTPError as e:
            err = json.loads(e.read().decode())
            if err.get("error") == "authorization_pending" and attempt < 3:
                time.sleep(state.get("interval", 5))
                continue
            print("Not authorised yet. Complete the Google auth then try again.")
            sys.exit(1)

        if "access_token" in tok_resp:
            tok_resp["expires_at"] = time.time() + tok_resp.get("expires_in", 3600) - 60
            _save_token(tok_resp)
            try:
                os.unlink(AUTH_STATE_PATH)
            except OSError:
                pass
            print("Authorised. Gmail is ready — retry your request.")
            return

    print("Not authorised yet. Complete the Google auth then try again.")
    sys.exit(1)


def cmd_auth(_args):
    """Initiate OAuth2 device flow and save token."""
    client_id, client_secret = _get_client()
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(DEVICE_URL, data=payload, method="POST")
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())

    device_code  = resp["device_code"]
    user_code    = resp["user_code"]
    verify_url   = resp.get("verification_url", "https://google.com/device")
    interval     = resp.get("interval", 5)
    expires_in   = resp.get("expires_in", 1800)

    print(f"\n{'='*50}")
    print(f"  Go to:  {verify_url}")
    print(f"  Code:   {user_code}")
    print(f"{'='*50}\n")
    print(f"Waiting for authorisation (expires in {expires_in}s) ...")

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        poll_payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }).encode()
        try:
            req2 = urllib.request.Request(TOKEN_URL, data=poll_payload, method="POST")
            with urllib.request.urlopen(req2) as r2:
                tok_resp = json.loads(r2.read())
        except urllib.error.HTTPError as e:
            err = json.loads(e.read())
            if err.get("error") == "authorization_pending":
                continue
            print(f"Auth error: {err}", file=sys.stderr)
            sys.exit(1)

        if "access_token" in tok_resp:
            tok_resp["expires_at"] = time.time() + tok_resp.get("expires_in", 3600) - 60
            _save_token(tok_resp)
            print("✅ Authenticated! Token saved.")
            return

    print("Timed out waiting for authorisation.", file=sys.stderr)
    sys.exit(1)


def cmd_labels(_args):
    """List all Gmail labels."""
    token = _get_access_token()
    data  = _api_get(token, "/labels")
    labels = sorted(data.get("labels", []), key=lambda x: x.get("name", ""))
    print(json.dumps(labels, indent=2))


def cmd_inbox(args):
    """Fetch and triage inbox emails.
    Usage: inbox [--max N] [--label LABEL] [--unread-only]
    """
    token       = _get_access_token()
    max_results = 20
    label       = "INBOX"
    unread_only = False
    i = 0
    while i < len(args):
        if args[i] == "--max" and i + 1 < len(args):
            max_results = int(args[i+1]); i += 2
        elif args[i] == "--label" and i + 1 < len(args):
            label = args[i+1]; i += 2
        elif args[i] == "--unread-only":
            unread_only = True; i += 1
        else:
            i += 1

    q = "is:unread" if unread_only else ""
    params = {
        "labelIds": label,
        "maxResults": max_results,
    }
    if q:
        params["q"] = q

    data     = _api_get(token, "/messages", params)
    messages = data.get("messages", [])

    if not messages:
        print(json.dumps({"count": 0, "messages": []}))
        return

    results = []
    for m in messages:
        msg = _api_get(token, f"/messages/{m['id']}", {"format": "metadata",
              "metadataHeaders": "From,Subject,Date"})
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        snippet  = msg.get("snippet", "")
        label_ids = msg.get("labelIds", [])
        results.append({
            "id":      m["id"],
            "from":    headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date":    headers.get("Date", ""),
            "snippet": snippet[:200],
            "labels":  label_ids,
            "unread":  "UNREAD" in label_ids,
        })

    print(json.dumps({"count": len(results), "messages": results}, indent=2))


def cmd_mark_read(args):
    """Mark message(s) as read. Usage: mark-read <id> [<id> ...]"""
    token = _get_access_token()
    for msg_id in args:
        _api_post(token, f"/messages/{msg_id}/modify", {
            "removeLabelIds": ["UNREAD"]
        })
        print(f"Marked read: {msg_id}")


def cmd_archive(args):
    """Archive message(s). Usage: archive <id> [<id> ...]"""
    token = _get_access_token()
    for msg_id in args:
        _api_post(token, f"/messages/{msg_id}/modify", {
            "removeLabelIds": ["INBOX"]
        })
        print(f"Archived: {msg_id}")


def cmd_label_msg(args):
    """Add a label to a message. Usage: label-msg <msg_id> <label_id>"""
    if len(args) < 2:
        print("Usage: label-msg <msg_id> <label_id>"); return
    token = _get_access_token()
    _api_post(token, f"/messages/{args[0]}/modify", {
        "addLabelIds": [args[1]]
    })
    print(f"Labelled {args[0]} with {args[1]}")


def cmd_profile(_args):
    """Get Gmail profile (email, total messages, unread)."""
    token = _get_access_token()
    data  = _api_get(token, "/profile")
    print(json.dumps(data, indent=2))


# ── Dispatch ─────────────────────────────────────────────────────────────────

COMMANDS = {
    "auth":          cmd_auth,
    "auth-complete": cmd_auth_complete,
    "labels":     cmd_labels,
    "inbox":      cmd_inbox,
    "mark-read":  cmd_mark_read,
    "archive":    cmd_archive,
    "label-msg":  cmd_label_msg,
    "profile":    cmd_profile,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print("Usage: gmail.py <command> [options]")
        print("Commands:", ", ".join(COMMANDS))
        sys.exit(1)
    COMMANDS[args[0]](args[1:])
