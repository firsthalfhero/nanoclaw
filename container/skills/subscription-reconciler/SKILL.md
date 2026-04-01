---
name: subscription-reconciler
description: >
  Family subscription reconciliation. Use when the user asks about subscriptions,
  bank charges, spending, mysteries, unmatched transactions, Emily's charges,
  monthly costs, or wants to upload a bank statement. Also use for queries like
  "what's the $16.99 charge?", "how much are we spending?", "show mysteries",
  "list Emily's charges", "mark that as Emily's", or "add a subscription".
metadata:
  {
    "nanoclaw":
      {
        "emoji": "💳",
      },
  }
---

# 💳 Subscription Reconciler

Tracks and reconciles the family's subscription charges from Macquarie bank statements and Gmail receipts. The reconciler runs as a separate Docker Compose service on the host.

**Family members:** George (father, account manager), Emily (mother — account not managed), Henry (son), Sophie (daughter)

**API base URL:** `http://host.docker.internal:8400/api/v1`

**Always call the API for live data — never guess or fabricate transaction details.**

---

## Attribution Rules

| Status | Meaning |
|--------|---------|
| `confirmed` | Matched to a known subscription |
| `needs_review` | Merchant matched but amount outside expected range |
| `emily_likely` | Likely Emily's charge (not in George/Henry/Sophie accounts) |
| `unmatched` | Unknown — needs investigation |

Emily's charges are a distinct, clearly labelled category — not mysteries. Surface them separately.

---

## Query Reference

### Show summary / spending

```bash
curl -s http://host.docker.internal:8400/api/v1/reports/summary
```

Present total monthly spend and each member's total. Note Emily's charges with context that her account isn't managed.

### Show mysteries (unmatched + needs_review)

```bash
curl -s http://host.docker.internal:8400/api/v1/reports/mysteries
```

Format as a list: date, merchant, amount, AI reasoning (if any). Keep it scannable.

### Show Emily's charges

```bash
curl -s http://host.docker.internal:8400/api/v1/reports/emily
```

### Look up a specific transaction (e.g. "what is the $16.99 charge?")

```bash
curl -s "http://host.docker.internal:8400/api/v1/transactions?status=unmatched"
```

Filter by amount or merchant from the results.

### List all unmatched transactions

```bash
curl -s http://host.docker.internal:8400/api/v1/transactions/unmatched
```

### List subscriptions for a member (replace MEMBER_ID)

```bash
curl -s "http://host.docker.internal:8400/api/v1/subscriptions?member_id=MEMBER_ID&status=active"
```

### Get member IDs

```bash
curl -s http://host.docker.internal:8400/api/v1/members
```

---

## Actions

### Upload a bank statement CSV

**Important:** Telegram does not download file attachments into the container.
Do NOT tell the user to drop files in the workspace folder — that doesn't work.

There are two ways to upload a CSV:

*Option 1 — Drop folder (easiest):*
Tell the user to drop the CSV file into this folder on their Windows desktop:
```
C:\Users\George\Documents\projects\subscription-reconciler\uploads\
```
The reconciler watches this folder every 30 seconds and auto-imports any CSV files it finds. Processed files are moved to `uploads\processed\` automatically.

*Option 2 — Dashboard:*
Open `http://localhost:8401` in a browser and use the file uploader in the left sidebar.

After either method, check the result:
```bash
curl -s http://host.docker.internal:8400/api/v1/reports/summary
```

When the user says they've uploaded/dropped a file, wait a moment then fetch the summary and report:
```
✅ Bank statement imported.

📥 {rows_inserted} transactions imported ({rows_skipped_duplicate} duplicates skipped)
⚠️ {new_unmatched} unmatched charges need attention

Run "show mysteries" to review them.
```

### Trigger Gmail sync

```bash
curl -s -X POST http://host.docker.internal:8400/api/v1/upload/gmail-sync
```

### Confirm or attribute a transaction (replace TXN_ID and MEMBER_ID)

```bash
curl -s -X PATCH http://host.docker.internal:8400/api/v1/transactions/TXN_ID/confirm \
  -H "Content-Type: application/json" \
  -d '{"attributed_member_id": MEMBER_ID, "notes": "Confirmed by George"}'
```

To mark as Emily's: first get Emily's member ID from `/members`, then use it as `attributed_member_id`.

### Add a new known subscription

```bash
curl -s -X POST http://host.docker.internal:8400/api/v1/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Netflix",
    "service_provider": "Netflix",
    "merchant_patterns": ["NETFLIX.COM"],
    "amount_min": 22.00,
    "amount_max": 23.00,
    "billing_cycle": "monthly",
    "attributed_member_id": 1,
    "category": "streaming",
    "status": "active"
  }'
```

---

## Message Formatting (WhatsApp / Telegram)

- No markdown headings (##). Use *bold* (single asterisk) and • bullets.
- Keep responses short and scannable.
- For money: always show AUD with 2 decimal places.
- For Emily's charges: always note "Emily's account is not managed by George".
- Never output raw JSON to the user — always summarise it.

**Example — mysteries response:**
```
⚠️ *3 unmatched charges need your attention:*

• 15 Mar — ADOBE SYSTEMS $23.99
  AI thinks: Adobe Creative Cloud (George?) — low confidence
• 22 Mar — UNKNOWN MERCHANT $4.99
  No match found
• 27 Mar — APPLE.COM/BILL $16.99
  Merchant matches Apple but amount doesn't match any known plan

Reply with the transaction ID to confirm or attribute one.
```

**Example — Emily's charges:**
```
💙 *Emily's charges (identified from bank only):*

• 12 Mar — APPLE.COM/BILL $4.99 — likely iCloud 50GB
• 22 Mar — APPLE.COM/BILL $31.99 — likely Apple One

Monthly total: ~$36.98
Note: Emily's account is not managed — these are estimated from bank transactions only.
```

---

## Weekly Digest Cron

Set up the weekly digest on Monday mornings (Sydney time). Add this cron job once:

```json
{
  "action": "add",
  "job": {
    "name": "subscription-reconciler:weekly-digest",
    "schedule": { "kind": "cron", "cron": "0 7 * * 1", "tz": "Australia/Sydney" },
    "sessionTarget": "isolated",
    "payload": {
      "kind": "agentTurn",
      "message": "Run the subscription reconciler weekly digest. Call GET http://host.docker.internal:8400/api/v1/reports/digest and format the digest_message field for WhatsApp (no markdown headings, use *bold* and bullets). If there are unmatched charges, emphasise them."
    },
    "delivery": { "mode": "announce" }
  }
}
```

---

## First-Time Setup

When the user first activates this skill (says "set up subscription reconciler", "activate reconciler", "start tracking subscriptions"):

1. Check if the API is reachable: `curl -s http://host.docker.internal:8400/health`
2. If not reachable: tell the user to run `docker compose up -d` in the `subscription-reconciler/` directory
3. If reachable: fetch `/members` to confirm seed data is in place
4. Set up the weekly digest cron job (JSON above)
5. Reply:

```
✅ Subscription Reconciler is running!

💳 Tracking subscriptions for: George, Henry, Sophie
💙 Emily's charges tracked separately (bank only)

To get started:
• Upload a Macquarie CSV: just send the file with caption "upload"
• Trigger Gmail sync: "sync Gmail"
• Check spending: "how much are we spending?"
• Review mysteries: "show mysteries"

Weekly digest set for Monday 7am.
```

---

## Rules

- ALWAYS call the API. NEVER guess transaction amounts, merchants, or subscription names.
- Emily is NEVER a "mystery" — she is a separate, clearly labelled category.
- When surfacing mysteries, always include AI reasoning if available.
- When the user says "mark X as Emily's", look up Emily's member ID first, then PATCH.
- Keep all responses WhatsApp-safe (no ##, no **double**, single *asterisk* for bold).
