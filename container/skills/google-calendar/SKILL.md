---
name: google-calendar
description: View and manage Google Calendar events — list, create, update, delete, and search.
homepage: https://calendar.google.com
metadata:
  {
    "openclaw":
      {
        "emoji": "📅",
        "requires":
          {
            "bins": ["python3"],
            "env": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
          },
        "primaryEnv": "GOOGLE_CLIENT_ID",
      },
  }
---

# 📅 Google Calendar

View and manage Google Calendar events. Uses the Google Calendar REST API with
OAuth2 device-flow authentication. Token is persisted between sessions.

## First-Time Setup

Run once to authenticate (opens a browser URL):

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py auth
```

This prints a short code and a URL. Open the URL in any browser, enter the code,
grant access, and the token is saved automatically to the workspace.

## Common Commands

### Today's events

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py today
```

### Upcoming events (default: 7 days)

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py list
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py list --days 14
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py list --days 30 --max 50
```

### Search events

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py search "dentist"
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py search "standup" --max 10
```

### Create an event

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py create "Team standup" \
  --start 2026-03-11T09:00:00 \
  --end   2026-03-11T09:30:00
```

With optional fields:

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py create "Dentist appointment" \
  --start 2026-03-12T10:00:00 \
  --end   2026-03-12T11:00:00 \
  --location "123 Main St" \
  --description "Bring X-rays"
```

Timezone defaults to `Australia/Sydney`. Override with `--timezone Europe/London`.

### Update an event

Use the event ID shown in list/search output:

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py update <eventId> --title "New title"
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py update <eventId> \
  --start 2026-03-12T11:00:00 \
  --end   2026-03-12T12:00:00
```

### Delete an event

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py delete <eventId>
```

### List available calendars

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py calendars
```

## Non-primary Calendars

All commands accept `--calendar <calendarId>` to target a specific calendar.
Get calendar IDs from `calendars` command. The default is `primary`.

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py list --calendar work@example.com
```

## Re-authentication (token expired or revoked)

**Always attempt the command first** — do not assume the token is still broken from a
previous session. The script handles re-auth automatically.

If `gcal.py` exits with code 2 and prints auth instructions, it means the refresh
token was revoked and a new device-flow auth has been started:

1. Relay the URL and code to the user exactly as printed.
2. Wait for the user to confirm they have completed the auth.
3. Run `auth-complete` to finish and save the new token:

```bash
python3 /home/node/.claude/skills/google-calendar/scripts/gcal.py auth-complete
```

4. Once that succeeds, retry the original calendar operation.

Do **not** tell the user to run scripts themselves or go to Google Cloud Console —
handle it entirely through the above flow.

## Notes

- Dates/times use ISO 8601 format: `YYYY-MM-DDTHH:MM:SS`
- OAuth token is stored at `/workspace/group/.gcal-token.json` and refreshes automatically
- The Google Cloud project must have the Calendar API enabled and the OAuth
  client configured for "TV and limited input devices" (device flow)
