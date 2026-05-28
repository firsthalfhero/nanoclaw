# Testing Workflow for Nanoclaw Integration

## Prerequisite: Create Initial Data

Since no sprints exist yet, we need to seed the database first.

### Step 1: Create Backlog Items

```bash
# Add a learning goal
python agile_sprint_tracker.py --action add_backlog_item \
  --type story \
  --title "Learn Docker networking" \
  --life_area next-chapter \
  --sub_area learning \
  --priority high \
  --description "Understand bridge networks, host networks, overlay networks"

# Add a health goal
python agile_sprint_tracker.py --action add_backlog_item \
  --type story \
  --title "3x weekly gym sessions" \
  --life_area health \
  --sub_area gym \
  --priority high \
  --description "Complete 3 strength training sessions"

# Add a family goal
python agile_sprint_tracker.py --action add_backlog_item \
  --type task \
  --title "Plan date night with Emily" \
  --life_area home-family \
  --sub_area emily \
  --priority high \
  --description "Book restaurant, arrange childcare, spend quality time"
```

**Save the UUIDs returned** for the next step.

### Step 2: Mark Items as Refined

Items are created in `raw` status. Update them to `refined`:

```bash
python agile_sprint_tracker.py --action update_backlog_item \
  --item_id <uuid-from-step-1> \
  --status refined
```

Repeat for all 3 items.

### Step 3: Start First Sprint

```bash
python agile_sprint_tracker.py --action start_sprint \
  --goal_item_ids '["uuid1", "uuid2", "uuid3"]'
```

This creates Sprint #1 in `active` state.

### Step 4: Get Current Sprint

```bash
python agile_sprint_tracker.py --action get_sprint
```

Response should show:
- Sprint #1, active state
- 3 goals with titles
- Current day (should be 1)
- Mobility streak (should be null initially)

**Success criteria:** Sprint is created, goals are assigned, state is active.

---

## Testing Nanoclaw Integration

Once sprint is created, test these Nanoclaw workflows:

### Workflow 1: Morning Check-In

**Nanoclaw prompt:**
```
Good morning! Check in with the sprint status and remind me about mobility.
```

**Expected flow:**
1. Nanoclaw calls: `python agile_sprint_tracker.py --action get_morning_checkin`
2. API returns: Sprint status, mobility reminder, current day
3. Nanoclaw responds to George: "Morning! You're on day X of Sprint 1. Did you do your mobility today?"

### Workflow 2: Log Mobility

**Nanoclaw prompt:**
```
I did my mobility today.
```

**Expected flow:**
1. Nanoclaw calls: `python agile_sprint_tracker.py --action log_mobility --done true`
2. API logs the entry
3. Nanoclaw responds: "Great! Your mobility streak is now X days."

### Workflow 3: Mid-Sprint Review (Day 7)

**Nanoclaw prompt:**
```
Let's do a mid-sprint review.
```

**Expected flow:**
1. Nanoclaw calls: `python agile_sprint_tracker.py --action get_mid_sprint_data`
2. API returns: Goals, completion status, mobility streak
3. Nanoclaw leads review dialogue with George

### Workflow 4: Evening Check-In (Day 14)

**Nanoclaw prompt:**
```
Evening check-in. Time for the retrospective.
```

**Expected flow:**
1. Nanoclaw calls: `python agile_sprint_tracker.py --action get_retro_data`
2. API returns: Sprint summary, goals, mobility, previous retro
3. Nanoclaw guides George through retro questions
4. Nanoclaw calls: `python agile_sprint_tracker.py --action complete_sprint --responses {...}`
5. Sprint is archived, new sprint can be started

---

## Expected Output Examples

### get_sprint (Sprint #1 exists)

```json
{
  "ok": true,
  "status": 200,
  "data": {
    "id": "uuid-sprint-1",
    "number": 1,
    "state": "active",
    "startDate": "2026-05-26",
    "endDate": "2026-06-09",
    "totalDays": 14,
    "currentDay": 1,
    "goals": [
      {
        "id": "uuid-goal-1",
        "itemId": "uuid-item-docker",
        "title": "Learn Docker networking",
        "lifeArea": "next-chapter",
        "subArea": "learning",
        "completedAt": null,
        "addedAt": "2026-05-26T10:30:00Z"
      },
      ...
    ],
    "mobilityStreak": 1
  },
  "error": null
}
```

### log_mobility (done: true)

```json
{
  "ok": true,
  "status": 201,
  "data": {
    "id": "uuid-log",
    "sprintId": "uuid-sprint-1",
    "logDate": "2026-05-26",
    "done": true,
    "createdAt": "2026-05-26T18:30:00Z"
  },
  "error": null
}
```

### get_morning_checkin

```json
{
  "ok": true,
  "status": 200,
  "data": {
    "currentSprint": {
      "id": "uuid-sprint-1",
      "number": 1,
      "state": "active",
      "currentDay": 1
    },
    "mobilityLogged": false,
    "mobilityStreak": 0,
    "goalsCount": 3,
    "completedGoals": 0,
    "message": "Good morning! You're on day 1 of Sprint 1. Have you done your mobility?"
  },
  "error": null
}
```

---

## Debugging

### If get_sprint returns null

Sprint hasn't been created yet. Run the full workflow from Step 1.

### If add_backlog_item fails with "life_area not valid"

Check spelling: `health`, `next-chapter`, `home-family` (with hyphens).

### If start_sprint fails with "max goals exceeded"

You're trying to add 6+ goals. Limit to 5.

### If start_sprint fails with "no next-chapter goal"

Add at least 1 goal with `life_area: next-chapter` before starting sprint.

### If Python script returns "Cannot reach API"

1. Check hp-server is running: `docker ps`
2. Check API container: `docker logs agile-life-api-1`
3. Test API directly: `curl http://agilelife.home/health`

---

## Full Test Sequence (Copy-Paste)

Save as `test_sprint.sh`:

```bash
#!/bin/bash
set -e

SKILL="python ~/agile-life/skill/agile-sprint-tracker/agile_sprint_tracker.py"

echo "=== Creating backlog items ==="
DOCKER_UUID=$($SKILL --action add_backlog_item \
  --type story \
  --title "Learn Docker networking" \
  --life_area next-chapter \
  --sub_area learning \
  --priority high | jq -r '.data.id')
echo "Created Docker item: $DOCKER_UUID"

GYM_UUID=$($SKILL --action add_backlog_item \
  --type story \
  --title "3x weekly gym" \
  --life_area health \
  --sub_area gym \
  --priority high | jq -r '.data.id')
echo "Created Gym item: $GYM_UUID"

DATE_UUID=$($SKILL --action add_backlog_item \
  --type task \
  --title "Date night with Emily" \
  --life_area home-family \
  --sub_area emily \
  --priority high | jq -r '.data.id')
echo "Created Date item: $DATE_UUID"

echo ""
echo "=== Marking items as refined ==="
$SKILL --action update_backlog_item --item_id $DOCKER_UUID --status refined > /dev/null
$SKILL --action update_backlog_item --item_id $GYM_UUID --status refined > /dev/null
$SKILL --action update_backlog_item --item_id $DATE_UUID --status refined > /dev/null
echo "All items refined"

echo ""
echo "=== Starting Sprint 1 ==="
$SKILL --action start_sprint --goal_item_ids "[\"$DOCKER_UUID\",\"$GYM_UUID\",\"$DATE_UUID\"]" | jq '.data | {number, state, currentDay, goals: [.goals[].title]}'

echo ""
echo "=== Getting current sprint ==="
$SKILL --action get_sprint | jq '.data | {number, state, currentDay, mobilityStreak, goalsCount: (.goals | length)}'

echo ""
echo "=== Logging mobility ==="
$SKILL --action log_mobility --done true | jq '.data | {logDate, done, createdAt}'

echo ""
echo "=== Getting mobility status ==="
$SKILL --action get_mobility_status | jq '.data | {streak, lastLogged, sprintCount: (.history | length)}'

echo ""
echo "✅ Test workflow complete!"
```

Run:
```bash
chmod +x test_sprint.sh
./test_sprint.sh
```

---

## Nanoclaw Integration Checklist

- [ ] Dependencies added to package.json / Dockerfile
- [ ] Skill symlinked to Nanoclaw skills directory
- [ ] `AGILE_API_BASE` env var set in Nanoclaw container
- [ ] Test sprint created via workflow above
- [ ] `python agile_sprint_tracker.py --action get_sprint` returns Sprint #1
- [ ] Morning check-in workflow tested
- [ ] Evening check-in workflow tested
- [ ] Mid-sprint review workflow tested
- [ ] Full sprint lifecycle tested (start → mid-review → retro → close)
- [ ] Mobility tracking tested
- [ ] Escalation logic tested (3-day miss)
