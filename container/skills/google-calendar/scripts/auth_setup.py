#!/usr/bin/env python3
"""
Google Calendar - One-time host auth setup.
Run this on your Windows host (not in the container).

Usage:
  python auth_setup.py [--port 8765]

Requires:
  OPENCLAW_GOOGLE_CLIENT_ID and OPENCLAW_GOOGLE_CLIENT_SECRET set in environment,
  OR pass --client-id and --client-secret flags.

The token is saved to:
  D:/AI_Projects/.openclaw/workspace/.gcal-token.json
(which the container reads as /home/node/.openclaw/workspace/.gcal-token.json)
"""

import http.server
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN_PATH   = r"D:\AI_Projects\.openclaw\workspace\.gcal-token.json"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE        = "https://www.googleapis.com/auth/calendar"
DEFAULT_PORT = 8765

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

args = sys.argv[1:]
port = DEFAULT_PORT
client_id = os.environ.get("OPENCLAW_GOOGLE_CLIENT_ID", "")
client_secret = os.environ.get("OPENCLAW_GOOGLE_CLIENT_SECRET", "")

i = 0
while i < len(args):
    if args[i] == "--port" and i + 1 < len(args):
        port = int(args[i + 1]); i += 2
    elif args[i] == "--client-id" and i + 1 < len(args):
        client_id = args[i + 1]; i += 2
    elif args[i] == "--client-secret" and i + 1 < len(args):
        client_secret = args[i + 1]; i += 2
    else:
        i += 1

if not client_id or not client_secret:
    print("Error: set OPENCLAW_GOOGLE_CLIENT_ID and OPENCLAW_GOOGLE_CLIENT_SECRET in your environment")
    print("  or pass --client-id and --client-secret")
    sys.exit(1)

REDIRECT_URI = f"http://localhost:{port}"

# ---------------------------------------------------------------------------
# OAuth2 authorization code flow
# ---------------------------------------------------------------------------

auth_params = urllib.parse.urlencode({
    "client_id": client_id,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPE,
    "access_type": "offline",
    "prompt": "consent",
})
auth_url = f"{AUTH_URL}?{auth_params}"

print(f"\nOpening browser for Google Calendar authorisation...")
print(f"\nIf the browser does not open, visit:\n  {auth_url}\n")
print(f"NOTE: If you see 'redirect_uri_mismatch', add this URI to your")
print(f"Google Cloud OAuth client's authorized redirect URIs:")
print(f"  {REDIRECT_URI}\n")

# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------

received_code = [None]
received_error = [None]


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence access logs

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            received_error[0] = params["error"][0]
            self._respond("Authorization denied. You can close this tab.")
        elif "code" in params:
            received_code[0] = params["code"][0]
            self._respond("Authorised! You can close this tab and return to the terminal.")
        else:
            self._respond("Unexpected response. Please try again.")

    def _respond(self, message):
        body = f"<html><body><h2>{message}</h2></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


server = http.server.HTTPServer(("localhost", port), CallbackHandler)
webbrowser.open(auth_url)

print(f"Waiting for Google to redirect to http://localhost:{port} ...")
server.handle_request()  # handle exactly one request then stop

if received_error[0]:
    print(f"Error from Google: {received_error[0]}")
    sys.exit(1)

if not received_code[0]:
    print("No authorisation code received.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Exchange code for tokens
# ---------------------------------------------------------------------------

print("Exchanging authorisation code for tokens...")

body = urllib.parse.urlencode({
    "code": received_code[0],
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}).encode()

req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        tok = json.loads(resp.read().decode())
except urllib.error.HTTPError as e:
    err = e.read().decode()
    print(f"Token exchange failed ({e.code}): {err}")
    sys.exit(1)

if "access_token" not in tok:
    print(f"Unexpected response: {tok}")
    sys.exit(1)

tok["expires_at"] = (
    datetime.now(timezone.utc) + timedelta(seconds=tok.get("expires_in", 3600))
).isoformat()

# ---------------------------------------------------------------------------
# Save token
# ---------------------------------------------------------------------------

os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
with open(TOKEN_PATH, "w") as f:
    json.dump(tok, f, indent=2)

print(f"\nToken saved to:\n  {TOKEN_PATH}")
print("\nThe container will pick it up automatically.")
print("You can now use Google Calendar via OpenClaw.")
