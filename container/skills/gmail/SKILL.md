---
name: gmail
description: Read and manage Gmail — inbox triage, label management, mark read, archive.
homepage: https://mail.google.com
metadata:
  {
    "openclaw":
      {
        "emoji": "📧",
        "requires":
          {
            "bins": ["python3"],
            "env": ["GOOGLE_GMAIL_CLIENT_ID", "GOOGLE_GMAIL_CLIENT_SECRET"],
          },
        "primaryEnv": "GOOGLE_GMAIL_CLIENT_ID",
      },
  }
---

# 📧 Gmail

Read and manage Gmail using the Gmail REST API with OAuth2 device-flow
authentication. Token is persisted between sessions.

## First-Time Setup

Run once to authenticate:

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py auth
```

This prints a short code and a URL. Open the URL in any browser, enter the
code, grant access, and the token is saved automatically.

## Common Commands

### View inbox

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py inbox
python3 /home/node/.claude/skills/gmail/scripts/gmail.py inbox --max 20
python3 /home/node/.claude/skills/gmail/scripts/gmail.py inbox --label SENT
```

### List labels

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py labels
```

### Mark messages as read

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py mark-read <messageId>
```

### Archive a message

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py archive <messageId>
```

### Apply a label

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py label-msg <messageId> <labelId>
```

### Account profile

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py profile
```

## Re-authentication (token explicitly revoked)

**Always attempt the command first** — the token refreshes automatically and
re-auth is only needed if the token was explicitly revoked in Google Console.

If the token is revoked, Google blocks Gmail from device flow, so re-auth
requires a browser on the host machine. Tell the user to run this on their
Windows host (not inside the container):

```bash
python container/skills/gmail/scripts/auth_setup_gmail.py
```

This opens a browser, completes the OAuth flow, and saves a new token to
`groups/main/.gmail-token.json`. Once done, the next Gmail command will work.

## Notes

- OAuth token is stored at `/workspace/group/.gmail-token.json`
- Env vars required: `GOOGLE_GMAIL_CLIENT_ID` and `GOOGLE_GMAIL_CLIENT_SECRET`
  (injected automatically by NanoClaw — do not look for `GOOGLE_CLIENT_ID`)
- Google blocks Gmail scopes from device flow — initial auth requires a browser and must
  be run on the host via `auth_setup_gmail.py`. Token refresh works automatically in the
  container without a browser, so re-auth should be rare (only if token is explicitly revoked)
