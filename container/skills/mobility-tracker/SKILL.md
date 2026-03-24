---
name: mobility-tracker
description: Manage the 'Mobility with Simon' physiotherapy app data — exercises and workout logs stored in Firestore. Triggers when the user asks to view, add, update or delete exercises or workout logs, asks what exercises are in the program, asks about workout history, or wants to log a session. Also triggers for questions like "what did Simon do last Tuesday", "update the hip exercise", "add a new exercise", "how many sets for X".
metadata:
  {
    "openclaw":
      {
        "emoji": "🏋️",
        "requires":
          {
            "bins": ["python3"],
            "env": ["FIREBASE_SERVICE_ACCOUNT"],
          },
        "primaryEnv": "FIREBASE_SERVICE_ACCOUNT",
      },
  }
---

# 🏋️ Mobility Tracker

Manage exercises and workout logs for the Mobility with Simon app.
Data lives in Firestore at `users/users/exercises` and `users/users/logs`.

Script: `/home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py`

ALWAYS run the script. NEVER fabricate exercise names, IDs, or log data.

---

## Exercises

### List all exercises (ordered by position)

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py list-exercises
```

### Get full details of one exercise

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py get-exercise <exerciseId>
```

### Add a new exercise

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py add-exercise \
  --name "Hip Flexor Stretch" \
  --focus-area "Hip" \
  --target-sets 3 \
  --target-reps "45 secs" \
  --weight "Bodyweight" \
  --notes "Keep spine neutral." \
  --video "https://..."
```

`--weight`, `--notes`, and `--video` are optional.

### Update an exercise

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py update-exercise <exerciseId> \
  --target-sets 4 \
  --notes "Updated physio notes."
```

Pass only the fields to change.

### Delete an exercise (also deletes all its logs)

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py delete-exercise <exerciseId> --yes
```

---

## Workout Logs

### List recent logs

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py list-logs
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py list-logs --limit 50
```

### Filter logs by exercise

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py list-logs --exercise-id <exerciseId>
```

### Filter logs by date

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py list-logs --date 2026-03-20
```

### Add a log entry

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py add-log \
  --exercise-id <exerciseId> \
  --set-number 1 \
  --reps "12" \
  --weight "Red band" \
  --variation "Half kneeling" \
  --feeling 7 \
  --comments "Felt strong today."
```

`--weight`, `--variation`, `--feeling`, and `--comments` are optional.

### Delete a log entry

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py delete-log <logId>
```

---

## Summary

```bash
python3 /home/node/.claude/skills/mobility-tracker/scripts/mobility_cli.py summary
```

---

## Rules

- ALWAYS run `list-exercises` first if the user refers to an exercise by name — you need the document ID.
- NEVER guess or fabricate Firestore document IDs.
- When the user says "delete X exercise", confirm the name match from `list-exercises` output before deleting.
- `Subjective_Feeling` is 0–10 (higher = better). If the user gives a feeling out of 10, pass it as `--feeling`.
- After any add/update/delete, confirm the outcome to the user.
- The app is used by one person (Simon) — there is only one set of exercises and logs.
