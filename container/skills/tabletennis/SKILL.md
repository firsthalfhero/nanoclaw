---
name: tabletennis
description: >
  Track table tennis club sessions, entry fees, and lesson credits for George and Henry at Pymble Table Tennis Club.
  Use when the user mentions table tennis, TT, ping pong, pinball club, going to the club, playing TT, lessons with James,
  "we went to table tennis", "George and Henry played", "Henry had a lesson", "I paid James", "paid the club",
  "how many lessons do we have left", "what do I owe the club", "table tennis summary", "entry fees", "lesson credits",
  or any mention of logging a session, lesson payments, or entry fee payments for this club.
metadata:
  {
    "nanoclaw": {
      "emoji": "🏓"
    }
  }
---

# Table Tennis Club Tracker

Track sessions, entry fees, and lesson credits for George and Henry at **Pymble Table Tennis Club**.

Use the `tabletennis.py` script for ALL operations. ALWAYS run the script — never fabricate session data, fees, or credit balances.

Script location: `/home/node/.claude/skills/tabletennis/scripts/tabletennis.py`
Fallback path: `/home/node/.openclaw/custom-skills/tabletennis/scripts/tabletennis.py`

Database: `/workspace/group/tabletennis.db` (pre-seeded with full history from Jan 2026)

---

## Club Details

- **Name:** Pymble Table Tennis Club (also known as Pinball Table Tennis Club)
- **Coach/Manager:** James Wong
- **Address:** 1186 Pacific Highway, Pymble
- **Website:** www.pymblettclub.com

### Opening Hours

| Day | Hours | Exceptions |
|---|---|---|
| Tuesday | 10am – 12pm | |
| Friday | 6pm – 9pm | |
| Saturday | 1pm – 5pm | 21 Feb, 21 Mar, 18 Apr, 16 May, 20 Jun, 18 Jul, 15 Aug, 19 Sep, 21 Nov → 4pm–7pm |
| Sunday | 1pm – 5pm | |

---

## Fee Structure

### Entry Fees (paid per visit, can be transferred)

Entry and lessons are **separate charges**. Attending the club gives access to social play against other members. Lessons are an additional optional service.

| Scenario | Fee per person |
|---|---|
| Entry only (no lesson that session) | $12.00 |
| Entry with lesson (discounted) | $5.00 |

### Lesson Fees (separate from entry, paid in cash)

- **$80 per lesson**, purchased upfront in blocks of 10 for **$800 cash**
- Paid directly to James Wong in cash
- Lessons are shared between George and Henry from a single credit pool
- Credits consumed FIFO (oldest block first)

---

## Members

- **George** (Andrew George Cains) — SNDTTA ID: 49197
- **Henry** (Henry Cains) — SNDTTA ID: 49198

Both are members of the Pymble Div 6 SNDTTA competition team.

---

## Current State (as of 31 Mar 2026)

- **Entry fees:** All paid up ($0 outstanding)
- **Lesson credits:** 1 remaining from Block 2 (purchased 28 Feb 2026)
- **Next $800 lesson payment** due soon — only 1 credit left

### Payment History

| Date | Type | Amount | Notes |
|---|---|---|---|
| 18 Jan 2026 | Lesson block | $800 cash | Block 1: 10 lessons |
| 14 Feb 2026 | Entry fees | $50 transfer | Covered Jan 17 – Feb 14 (5 sessions) |
| 28 Feb 2026 | Lesson block | $800 cash | Block 2: 10 lessons |
| 30 Mar 2026 | Entry fees | $114 transfer | Covered 28 Feb – 31 Mar (7 sessions incl. 29 Mar club-only) |

---

## Commands

### Log a Session

```bash
python3 /home/node/.claude/skills/tabletennis/scripts/tabletennis.py log-session \
  --date 2026-04-05 \
  --george --henry \
  --george-lesson --henry-lesson \
  --notes "optional notes"
```

Flags:
- `--date YYYY-MM-DD` — date of session (defaults to today)
- `--george` — George attended
- `--henry` — Henry attended
- `--george-lesson` — George had a lesson (requires `--george`)
- `--henry-lesson` — Henry had a lesson (requires `--henry`)
- `--notes "..."` — optional notes

### Log a Lesson Credit Purchase ($800 cash block)

```bash
python3 /home/node/.claude/skills/tabletennis/scripts/tabletennis.py log-lesson-payment \
  --date 2026-04-05 \
  --amount 800.00
```

### Log an Entry Fee Payment

```bash
python3 /home/node/.claude/skills/tabletennis/scripts/tabletennis.py log-entry-payment \
  --date 2026-04-05 \
  --amount 22.00 \
  --notes "paid for last two weeks"
```

### Show Outstanding Entry Balance

```bash
python3 /home/node/.claude/skills/tabletennis/scripts/tabletennis.py balance
```

### Show Lesson Credit Summary

```bash
python3 /home/node/.claude/skills/tabletennis/scripts/tabletennis.py lessons
```

### Full Summary

```bash
python3 /home/node/.claude/skills/tabletennis/scripts/tabletennis.py summary
```

---

## Intent → Command Mapping

| User says | Command to run |
|---|---|
| "we went to TT today" / "George and Henry played" | `log-session` |
| "Henry had a lesson today" | `log-session --henry --henry-lesson` |
| "just played, no lesson" | `log-session` (no lesson flags) |
| "I paid James $800 for lessons" | `log-lesson-payment` |
| "paid entry fees" / "I paid the club" | `log-entry-payment --amount <X>` |
| "how many lessons left?" | `lessons` |
| "what do I owe?" / "show outstanding" | `balance` |
| "table tennis summary" | `summary` |

---

## Rules

- ALWAYS run the script. NEVER guess or fabricate session data, credits, or fees.
- Entry fees and lesson fees are **separate** — logging a session records the entry fee; lesson credits are drawn separately from the $800 blocks.
- If the user doesn't specify a date, use today's date.
- If it's unclear who attended or whether a lesson was taken, ask before logging.
- After `log-session`, always run `balance` to show updated entry fee totals.
- After `log-lesson-payment`, always run `lessons` to show updated credits.
- After `log-entry-payment`, always run `balance` to confirm outstanding balance.
- Warn the user if lesson credits drop to 3 or fewer remaining.
- Confirm all mutations back to the user with a clear summary.
