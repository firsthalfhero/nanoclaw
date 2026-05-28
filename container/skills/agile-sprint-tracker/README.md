# agile-sprint-tracker Nanoclaw Skill

Python bridge between Nanoclaw and the agile-sprint-tracker REST API on hp-server.

**Status:** ✅ Implemented with 24 actions, ready for Nanoclaw integration
**API:** `http://agilelife.home` (local network)
**Language:** Python 3.8+
**Dependencies:** `requests>=2.31.0`

---

## Calling Conventions

The skill supports two calling conventions:

### 1. CLI Arguments

```bash
python agile_sprint_tracker.py --action get_sprint
python agile_sprint_tracker.py --action start_sprint --goal_item_ids '["uuid1","uuid2"]'
python agile_sprint_tracker.py --action log_mobility --done true
```

### 2. JSON via stdin

```bash
echo '{"action": "get_sprint"}' | python agile_sprint_tracker.py
echo '{"action": "start_sprint", "params": {"goal_item_ids": ["uuid1", "uuid2"]}}' | python agile_sprint_tracker.py
```

### Response Format

All actions return JSON:

```json
{
  "ok": true,
  "status": 200,
  "data": { /* action-specific data */ },
  "error": null
}
```

**Error response:**

```json
{
  "ok": false,
  "status": 400,
  "data": null,
  "error": "Validation error message or API error"
}
```

---

## Configuration

Set via environment variables (defaults provided):

```bash
export AGILE_API_BASE="http://agilelife.home"
export AGILE_API_TIMEOUT="10"
```

---

## Available Actions (24 total)

### Sprint Actions (5)

| Action | Parameters | Returns |
|--------|------------|---------|
| `get_sprint` | none | Current active sprint or null |
| `start_sprint` | `goal_item_ids: [uuid]` | New sprint with goals |
| `update_sprint_state` | `sprint_id: uuid`, `state: string` | Updated sprint state |
| `close_sprint` | `sprint_id: uuid` | Closed/archived sprint |
| `update_sprint_goal` | `goal_id: uuid`, `completed_at: timestamp\|null` | Updated goal |

### Backlog Actions (5)

| Action | Parameters | Returns |
|--------|------------|---------|
| `get_backlog` | none | All items grouped by status |
| `add_backlog_item` | `type`, `title`, `life_area`, `priority`, `sub_area?`, `description?` | New item |
| `update_backlog_item` | `item_id`, `...fields` | Updated item |
| `delete_backlog_item` | `item_id`, `reason?` | Soft-deleted item |
| `decompose_epic` | `epic_id`, `child_stories: [...]` | Epic with children |

### Mobility Actions (2)

| Action | Parameters | Returns |
|--------|------------|---------|
| `log_mobility` | `done: boolean` | Logged entry |
| `get_mobility_status` | none | Streak + history |

### Ceremony Actions (4)

| Action | Parameters | Returns |
|--------|------------|---------|
| `get_refinement_data` | none | Unrefined items + ready backlog |
| `get_mid_sprint_data` | none | Current sprint goals + progress |
| `get_retro_data` | none | Sprint summary + previous retro |
| `save_retro_responses` | `responses: {whatWentWell: [...], improvements: [...], blockers: [...]}` | Saved retro |

### Check-in Actions (2)

| Action | Parameters | Returns |
|--------|------------|---------|
| `get_morning_checkin` | none | Sprint status + mobility reminder |
| `get_evening_checkin` | none | Mobility prompt + escalation data |

### History Actions (2)

| Action | Parameters | Returns |
|--------|------------|---------|
| `get_history` | none | All closed sprints |
| `get_sprint_history` | `sprint_id: uuid` | Closed sprint details |

### Composite Actions (3)

| Action | Purpose | Parameters | Returns |
|--------|---------|------------|---------|
| `get_full_state` | Fetch sprint + backlog + mobility together | none | Combined state |
| `triage_and_add_item` | Add item + return updated backlog | item fields | {item, backlog} |
| `complete_sprint` | Save retro + close sprint | `responses: {...}` | {retro, archivedSprint} |

---

## Examples

### Get Current Sprint

```bash
python agile_sprint_tracker.py --action get_sprint
```

**Response:**

```json
{
  "ok": true,
  "status": 200,
  "data": {
    "id": "uuid",
    "number": 1,
    "state": "active",
    "startDate": "2026-05-26",
    "endDate": "2026-06-09",
    "currentDay": 1,
    "goals": [
      {
        "id": "uuid",
        "itemId": "uuid",
        "title": "Learn Docker",
        "lifeArea": "next-chapter",
        "completedAt": null
      }
    ],
    "mobilityStreak": 5
  },
  "error": null
}
```

### Start New Sprint

```bash
python agile_sprint_tracker.py --action start_sprint --goal_item_ids '["uuid-1","uuid-2","uuid-3"]'
```

**Validation:**
- 1–5 goals only
- ≥1 goal must have `lifeArea: next-chapter`
- All goals must have `status: refined`
- No epics allowed

### Log Mobility

```bash
python agile_sprint_tracker.py --action log_mobility --done true
```

### Submit Retrospective and Close Sprint

```bash
python agile_sprint_tracker.py --action complete_sprint --responses '{
  "whatWentWell": ["Good momentum", "Learned Docker"],
  "improvements": ["Better async communication"],
  "blockers": ["Work deadline pressure"]
}'
```

### Add Backlog Item Mid-Sprint

```bash
python agile_sprint_tracker.py --action triage_and_add_item \
  --type story \
  --title "Fix authentication bug" \
  --life_area next-chapter \
  --sub_area skills \
  --priority high
```

---

## Error Handling

All errors are handled gracefully and returned as structured JSON:

```json
{
  "ok": false,
  "status": 400,
  "data": null,
  "error": "Validation error: epic cannot be in sprint"
}
```

**Common errors:**

| Error | Meaning |
|-------|---------|
| `Cannot reach agile-sprint-tracker API` | hp-server or API container is down |
| `Validation error: ...` | Request violates business rules (max 5 goals, etc.) |
| `Sprint not found` | Requested sprint doesn't exist |
| `Item already has status: in-sprint` | Invalid status transition |

---

## Nanoclaw Integration

### 1. Installation

Place this directory in Nanoclaw's skills folder:

```bash
ln -sf ~/agile-life/skill/agile-sprint-tracker ~/nanoclaw/container/skills/agile-sprint-tracker
```

### 2. Usage in Nanoclaw

**Invoke action from Nanoclaw LLM:**

```python
# In Nanoclaw skill definition
result = subprocess.run(
    ["python3", "skill/agile-sprint-tracker/agile_sprint_tracker.py",
     "--action", "get_sprint"],
    capture_output=True,
    text=True
)
response = json.loads(result.stdout)
```

### 3. Response Handling

Check `response["ok"]` before processing data:

```python
if response["ok"]:
    sprint = response["data"]
    # Process sprint data
else:
    error_msg = response["error"]
    # Handle error
```

---

## Development & Testing

### Test Locally (without running API)

```bash
python agile_sprint_tracker.py --action get_sprint
# → {ok: false, error: "Cannot reach agile-sprint-tracker API..."}
```

### Test Against Running API

First, ensure API is running:

```bash
curl http://agilelife.home/health
# → {"status":"ok"}
```

Then test:

```bash
python agile_sprint_tracker.py --action get_sprint
# → {ok: true, status: 200, data: {...}, error: null}
```

### Run Tests (if implemented)

```bash
python -m pytest tests/
```

---

## File Structure

```
skill/agile-sprint-tracker/
├── agile_sprint_tracker.py     ← Main skill file (all actions)
├── requirements.txt             ← Dependencies
├── README.md                    ← This file
├── SKILL.md                     ← Nanoclaw skill manifest
└── references/                  ← Documentation
    ├── ceremonies.md
    ├── escalation.md
    ├── life-areas.md
    └── schema.md
```

---

## Dependencies

- `requests>=2.31.0` — HTTP client for API calls
- Python 3.8+ (f-strings, type hints)

Install dependencies:

```bash
pip install -r requirements.txt
```

Or assume Nanoclaw provides `requests` in its base environment and skip installation.

---

## Known Limitations

1. **No caching** — Every call hits the API. By design.
2. **No offline mode** — If API is unreachable, skill fails gracefully with error message.
3. **No authentication** — Local network API has no auth (add if needed).
4. **No transaction handling** — Multi-step operations (e.g., `complete_sprint`) are composed but not atomic.

---

## Troubleshooting

### "Cannot reach agile-sprint-tracker API"

1. Check if hp-server is running: `ping hp-server`
2. Check if API container is running: `docker ps | grep api`
3. Check if port 3456 is open: `curl http://localhost:3456/health`
4. Verify environment variable: `echo $AGILE_API_BASE`

### "Validation error: epic cannot be in sprint"

Epics must be decomposed into stories before they can be sprint goals. Use `decompose_epic` action first.

### "Max goals exceeded (5)"

Reduce sprint scope. Current sprint has 5 or more goals; limit is 5.

### "No next-chapter goal"

Every sprint must include ≥1 goal with `life_area: next-chapter`. Add a learning or growth goal.

---

## Next Steps

1. **Confirm calling convention** with Nanoclaw team (CLI args, stdin JSON, or function calls)
2. **Install dependencies** in Nanoclaw environment
3. **Symlink skill** into Nanoclaw's skills directory
4. **Test** with sample Nanoclaw workflows (sprint planning, ceremonies)
5. **Implement Nanoclaw ceremony workflows** (using this skill as the data/action layer)

---

## Author

Generated by Claude for Nanoclaw integration with agile-sprint-tracker API.

**Related:** `SKILL.md` (manifest), API docs at `http://agilelife.home/docs`
