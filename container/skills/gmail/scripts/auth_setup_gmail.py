#!/usr/bin/env python3
"""
Gmail - One-time host auth setup.
Run this on your Windows host (not in the container).

Usage:
  python auth_setup_gmail.py

Requires:
  GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET set in environment
  (same credentials used for Google Calendar)

Token saved to:
  groups\\main\\.gmail-token.json  (relative to project root)
"""

import http.server, json, os, sys, urllib.parse, urllib.request, webbrowser
from datetime import datetime, timezone, timedelta

TOKEN_PATH   = r"c:\Users\George\Documents\projects\nanoclaw\groups\main\.gmail-token.json"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE        = " ".join([
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
])
PORT = 8766

client_id     = os.environ.get("GOOGLE_GMAIL_CLIENT_ID", "")
client_secret = os.environ.get("GOOGLE_GMAIL_CLIENT_SECRET", "")

if not client_id or not client_secret:
    print("Error: set GOOGLE_GMAIL_CLIENT_ID and GOOGLE_GMAIL_CLIENT_SECRET in your environment.")
    print("\nIn PowerShell:")
    print('  $env:GOOGLE_GMAIL_CLIENT_ID="your-client-id"')
    print('  $env:GOOGLE_GMAIL_CLIENT_SECRET="your-client-secret"')
    sys.exit(1)

REDIRECT_URI = f"http://localhost:{PORT}"
auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
    "client_id": client_id, "redirect_uri": REDIRECT_URI,
    "response_type": "code", "scope": SCOPE,
    "access_type": "offline", "prompt": "consent",
})

print(f"\nOpening browser for Gmail auth...")
print(f"If browser doesn't open, visit:\n  {auth_url}")
print(f"\nIf you see 'redirect_uri_mismatch', add this to Google Cloud OAuth client:")
print(f"  {REDIRECT_URI}\n")

received = [None, None]  # [code, error]

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in p:   received[0] = p["code"][0]
        if "error" in p:  received[1] = p["error"][0]
        body = b"<html><body><h2>Done! You can close this tab.</h2></body></html>"
        self.send_response(200); self.send_header("Content-Type","text/html")
        self.send_header("Content-Length", len(body)); self.end_headers()
        self.wfile.write(body)

webbrowser.open(auth_url)
http.server.HTTPServer(("localhost", PORT), Handler).handle_request()

if received[1]: print(f"Auth error: {received[1]}"); sys.exit(1)
if not received[0]: print("No code received."); sys.exit(1)

print("Exchanging code for token...")
body = urllib.parse.urlencode({
    "code": received[0], "client_id": client_id, "client_secret": client_secret,
    "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
}).encode()
req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")
try:
    tok = json.loads(urllib.request.urlopen(req, timeout=15).read())
except urllib.error.HTTPError as e:
    print(f"Failed ({e.code}): {e.read().decode()}"); sys.exit(1)

tok["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=tok.get("expires_in",3600))).isoformat()
os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
with open(TOKEN_PATH, "w") as f: json.dump(tok, f, indent=2)
print(f"\nToken saved to:\n  {TOKEN_PATH}")
print("Gmail is ready!")
