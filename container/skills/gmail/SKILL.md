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

## Re-authentication (token expired or revoked)

**Always attempt the command first** — do not check env vars or assume the
token is broken from a previous session. The script handles re-auth
automatically and will tell you if action is needed.

If `gmail.py` exits with code 2 and prints auth instructions, a new
device-flow auth has been started:

1. Relay the URL and code to the user exactly as printed.
2. Wait for the user to confirm they have completed the auth.
3. Run `auth-complete` to finish and save the new token:

```bash
python3 /home/node/.claude/skills/gmail/scripts/gmail.py auth-complete
```

4. Once that succeeds, retry the original operation.

Do **not** tell the user to run scripts themselves or to check docker-compose
or any config files — handle it entirely through the above flow.

## Notes

- OAuth token is stored at `/workspace/group/.gmail-token.json`
- Env vars required: `GOOGLE_GMAIL_CLIENT_ID` and `GOOGLE_GMAIL_CLIENT_SECRET`
  (injected automatically by NanoClaw — do not look for `GOOGLE_CLIENT_ID`)
- The OAuth client type must be "Desktop app" (not TV/device flow)
