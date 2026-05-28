---
name: agile-sprint-tracker
description: >
  Personal Agile sprint management. Use when George mentions: sprint, backlog,
  retrospective, refinement, "how am I tracking", "add to backlog", "start sprint",
  "daily check-in", "mid-sprint review", "what are my goals", mobility check,
  sprint planning, "what did I commit to", or asks about current goals or priorities.
  Do NOT load for calendar management, nutrition logging, or unrelated tasks.
metadata:
  {
    "nanoclaw":
      {
        "emoji": "🏃",
        "requires": { "bins": ["python3"], "env": [] },
      },
  }
---

# 🏃 Agile Sprint Tracker

Script location: `/home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py`

**ALWAYS run the script — never fabricate sprint or backlog data.**

**ALWAYS call `state` first before any ceremony or check-in** — conversation history is unreliable.

---

## CRITICAL Rules

1. **Be active, never passive.** Push, prompt, confront. Never wait to be pushed.
2. **Mobility is asked EVERY evening. No exceptions. No softening.**
3. **Max 5 sprint goals.** Push back hard on anything over.
4. **Epics cannot enter a sprint.** Decompose into stories first.
5. **Every sprint must include ≥1 Next Chapter goal.** Block planning if absent.
6. **Never trust conversation history for data.** Always read from the script.
7. **Vague goals are rejected.** Demand measurable outcomes before accepting.
8. **George has ADHD.** Escalate fast. See `references/escalation.md`.

---

## Get Full State (use this first)

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py state
```

Returns: `{ sprint, backlog, mobility }` — everything needed for ceremonies and check-ins.

---

## Daily Check-ins

### Morning Check-in

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py cron-morning
```

Returns: `{ day, daysLeft, sprintState, goals, mobilityDoneToday }`

From this data, construct the morning message:
1. "Day [X] of 14. [Y] days left."
2. Mobility prompt — has it been done yet today?
3. One line per sprint goal with honest status
4. 1–3 specific things to focus on today
5. Any hard deadlines this week?
6. **Ceremony reminder** if applicable (see table below) — append to message, do not auto-start

**Ceremony reminders by sprint day:**

| Day | Reminder |
|-----|----------|
| 3 or 4 | "Backlog refinement is due — say 'let's refine' when ready." |
| 7 | "Mid-sprint review is due — say 'mid-sprint review' when ready." |
| 10 or 11 | "Backlog refinement is due — say 'let's refine' when ready." |
| 14 | "Retrospective is due — say 'let's do the retro' when ready." |

**Tone:** Direct, energising. No soft opener.

### Evening Check-in

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py cron-evening
```

Returns: `{ day, sprintState, mobilityDoneToday, goalsProgress }`

Construct the evening message:
1. **"Did you do your mobility today? Yes or no."** — Always first, always.
2. Did today's planned tasks get done?
3. Any blockers?
4. One thing to set up tomorrow

Log mobility after George responds:
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py mobility-log --done true
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py mobility-log --done false
```

**Tone:** Accountability. See `references/escalation.md`.

---

## Sprint Commands

### Get current sprint
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py sprint-current
```

### Start a sprint
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py sprint-start \
  --goals UUID1 UUID2 UUID3
```

Goals must be `status: refined`, max 5, ≥1 `lifeArea: next-chapter`.

### Update sprint state
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py sprint-state \
  --state mid-review
```

Valid states: `mid-review`, `retro`, `paused`, `active`. Never use `closed` here.

### Close sprint (end of retrospective only)
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py sprint-close
```

Always call `ceremony-save-retro` first to persist responses, then close.

### Mark a goal complete
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py sprint-goal GOAL_UUID \
  --completed-at 2026-05-25T14:00:00Z
```

---

## Backlog Commands

### List all backlog items
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py backlog-list
```

Items grouped by status: `raw`, `refined`, `in-sprint`, `done`, `deferred`, `dropped`.

### Add a backlog item
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py backlog-add \
  --type story \
  --title "Complete AWS Solutions Architect Module 1" \
  --life-area next-chapter \
  --sub-area learning \
  --priority high
```

Types: `epic`, `story`, `task`. Epics cannot enter sprints until decomposed.

### Update a backlog item
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py backlog-update UUID \
  --status refined \
  --priority medium
```

Legal status transitions: `raw→refined`, `refined→in-sprint`, `in-sprint→done|deferred|dropped`, `deferred→refined`.

### Drop a backlog item
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py backlog-delete UUID \
  --reason "No longer relevant"
```

Soft delete only. Final state — cannot be changed after.

### Decompose an epic into stories
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py backlog-decompose EPIC_UUID \
  --stories '[{"title":"Complete Module 1-2","subArea":"learning","priority":"high"},{"title":"Complete Module 3-4","subArea":"learning","priority":"medium"}]'
```

Child stories inherit `lifeArea` from the parent epic. Created as `status: raw`.

---

## Mobility Commands

### Log mobility
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py mobility-log --done true
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py mobility-log --done false
```

### Get mobility status
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py mobility-status
```

Returns: `{ streak, daysCompleted, totalDays }`

---

## Ceremony Commands

Ceremonies are **always triggered by George** — never auto-started. Morning check-in adds a reminder nudge on ceremony days only. George says "let's refine" / "mid-sprint review" / "let's do the retro" when ready.

### Backlog Refinement (days 3–4, 10–11)

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py ceremony-refinement
```

Returns: raw items + refined items grouped by life area. Full ceremony script → `references/ceremonies.md`.

### Mid-Sprint Review (day 7)

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py ceremony-mid-sprint
```

Returns: current goals + mobility status + new items since planning.

### Retrospective (day 14)

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py ceremony-retro
```

Returns: completed goals, incomplete goals, mobility summary, flagged carryovers.

After collecting George's responses, save them before closing:
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py ceremony-save-retro \
  --responses '{"gut_reaction":"Went well overall","completed":"Goals 1 and 3","mobility_days":"11"}'
```

Then close the sprint:
```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py sprint-close
```

Full ceremony scripts and edge cases → `references/ceremonies.md`.

---

## History Commands

```bash
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py history-list
python3 /home/node/.claude/skills/agile-sprint-tracker/agile_sprint_cli.py history-get SPRINT_UUID
```

---

## Life Areas

Full definitions → `references/life-areas.md`

- **Health:** `medical` · `gym` · `mobility`
- **Next Chapter:** `learning` · `skills` · `thinking`
- **Home & Family:** `kids` · `life-admin` · `emily` · `chores` · `projects`

`health/mobility` is never a sprint goal — tracked daily as a non-negotiable only.

---

## Item Types

| Type | Can enter sprint? | Notes |
|------|-------------------|-------|
| `epic` | No | Must be decomposed into stories first |
| `story` | Yes (when `refined`) | Sprint-sized chunk of work |
| `task` | Yes (when `refined`) | Atomic single action |

---

## Cron Setup

Morning and evening check-ins are triggered via system crontab using the `claw` CLI, which spawns an agent container and sends a prompt directly to Nanoclaw.

Add to crontab (`crontab -e` on hp-server):

```bash
# Agile Sprint — Morning check-in (7:00 AM)
0 7 * * * claw -g george "Run the agile sprint morning check-in" 2>&1 | logger -t agile-sprint

# Agile Sprint — Evening check-in (7:00 PM)
0 19 * * * claw -g george "Run the agile sprint evening check-in" 2>&1 | logger -t agile-sprint
```

Replace `-g george` with your actual Nanoclaw group name. Omit the `-g` flag entirely to use the default group.

The `claw` CLI spawns the agent container, sends the prompt, and the agent loads this skill, calls `cron-morning` or `cron-evening`, formats the message, and sends it back to you via your messaging platform.
