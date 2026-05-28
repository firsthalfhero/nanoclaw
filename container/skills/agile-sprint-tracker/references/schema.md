# schema.md

Complete data structures and database schema for agile-sprint-tracker.

---

## Database Tables

### sprints
Stores sprint metadata and state.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | uuid | pk | Unique identifier |
| `number` | int | unique, auto-increment | Sprint sequence (1, 2, 3...) |
| `state` | enum | enum(active, mid-review, retro, paused, closed) | Current sprint state |
| `startDate` | date | not null | Sprint start date |
| `endDate` | date | not null | Sprint end date (typically +14 days) |
| `totalDays` | int | default 14 | Sprint duration in days |
| `pausedOn` | date | nullable | Date sprint was paused |
| `resumeDate` | date | nullable | Date sprint was resumed |
| `createdAt` | timestamp | default now() | Created at |
| `updatedAt` | timestamp | default now() | Last updated |

**Indexes:**
- `idx_sprints_state` on `state`
- `idx_sprints_number` on `number`

**Constraints:**
- `endDate > startDate`
- If `pausedOn` is set, `resumeDate` must be set before closing

---

### backlog_items
All work items (epics, stories, tasks).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | uuid | pk | Unique identifier |
| `type` | enum | enum(epic, story, task) | Item classification |
| `title` | text | not null | Item title |
| `description` | text | nullable | Long-form description |
| `priority` | enum | enum(low, medium, high, asap) | Priority level |
| `lifeArea` | enum | enum(health, next-chapter, home-family) | Life area classification |
| `subArea` | text | nullable | Sub-area (e.g., "gym", "learning") |
| `status` | enum | enum(raw, refined, in-sprint, done, deferred, dropped) | Workflow status |
| `parentId` | uuid | fk backlog_items(id), nullable | Parent epic (for decomposed items) |
| `sprintCount` | int | default 0 | How many sprints this item has been in |
| `completedAt` | timestamp | nullable | When item was marked done |
| `deferredReason` | text | nullable | Why item was deferred |
| `droppedReason` | text | nullable | Why item was dropped |
| `createdAt` | timestamp | default now() | Created at |
| `updatedAt` | timestamp | default now() | Last updated |

**Indexes:**
- `idx_backlog_items_status` on `status`
- `idx_backlog_items_lifeArea` on `lifeArea`
- `idx_backlog_items_parentId` on `parentId`

**Constraints:**
- `status = dropped` is terminal (no transitions allowed)
- `type = epic` cannot have `status = in-sprint`
- `parentId` can only be set when `parentId.type = epic`

---

### sprint_goals
Links backlog items to sprints as sprint goals.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | uuid | pk | Unique identifier |
| `sprintId` | uuid | fk sprints(id) | Sprint reference |
| `itemId` | uuid | fk backlog_items(id) | Backlog item reference |
| `addedAt` | timestamp | default now() | When goal was added to sprint |
| `completedAt` | timestamp | nullable | When goal was marked done |

**Indexes:**
- `idx_sprint_goals_sprintId` on `sprintId`
- `idx_sprint_goals_itemId` on `itemId`
- `unique(sprintId, itemId)` — One goal per sprint per item

**Constraints:**
- Item must have `status = refined` when added
- Item cannot have `type = epic`
- Max 5 goals per sprint
- ≥1 goal per sprint must have `lifeArea = next-chapter`

---

### mobility_logs
Daily mobility tracking per sprint.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | uuid | pk | Unique identifier |
| `sprintId` | uuid | fk sprints(id) | Sprint reference |
| `logDate` | date | not null | Date of log |
| `done` | boolean | default false | Completed today's mobility |
| `createdAt` | timestamp | default now() | When logged |

**Indexes:**
- `idx_mobility_logs_sprintId` on `sprintId`
- `unique(sprintId, logDate)` — One log per sprint per day

**Constraints:**
- `logDate` cannot be in the future
- `logDate` must be within sprint dates

---

### sprint_retrospectives
Retro responses submitted at end of sprint.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | uuid | pk | Unique identifier |
| `sprintId` | uuid | fk sprints(id), unique | Sprint reference |
| `completedAt` | timestamp | default now() | When retro was submitted |
| `responses` | jsonb | not null | Retro data (see below) |

**Indexes:**
- `idx_sprint_retrospectives_sprintId` on `sprintId`

**Response Schema (JSONB):**
```json
{
  "whatWentWell": ["item1", "item2"],
  "improvements": ["item1", "item2"],
  "blockers": ["item1", "item2"],
  "nextSprintFocus": "optional focus area"
}
```

---

### meta
Configuration and metadata (single-row table).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | uuid | pk | Always 'config' |
| `lastUpdated` | timestamp | default now() | Last schema migration |
| `timezone` | text | default 'Australia/Sydney' | User timezone |

---

## API Schema Objects

### Sprint
Complete sprint object returned by endpoints.

```json
{
  "id": "uuid",
  "number": 1,
  "state": "active",
  "startDate": "2026-05-26",
  "endDate": "2026-06-09",
  "totalDays": 14,
  "currentDay": 1,
  "pausedOn": null,
  "resumeDate": null,
  "goals": [
    {
      "id": "uuid",
      "itemId": "uuid",
      "title": "Learn Docker networking",
      "lifeArea": "next-chapter",
      "subArea": "learning",
      "priority": "high",
      "completedAt": null,
      "addedAt": "2026-05-26T10:30:00Z"
    }
  ],
  "mobilityStreak": 5,
  "createdAt": "2026-05-26T10:00:00Z",
  "updatedAt": "2026-05-26T10:30:00Z"
}
```

### BacklogItem
Complete backlog item object.

```json
{
  "id": "uuid",
  "type": "story",
  "title": "Learn Docker networking",
  "description": "Understand bridge networks, host networks, overlay networks",
  "priority": "high",
  "lifeArea": "next-chapter",
  "subArea": "learning",
  "status": "refined",
  "parentId": null,
  "sprintCount": 1,
  "completedAt": null,
  "deferredReason": null,
  "droppedReason": null,
  "createdAt": "2026-05-20T08:00:00Z",
  "updatedAt": "2026-05-26T10:30:00Z"
}
```

### MobilityStatus
Mobility tracking status.

```json
{
  "streak": 5,
  "lastLogged": "2026-05-26",
  "history": [
    {
      "sprintNumber": 1,
      "startDate": "2026-05-26",
      "endDate": "2026-06-09",
      "completedDays": 11,
      "missedDays": 3,
      "percentage": 78.6
    }
  ]
}
```

### CeremonyRefinement
Data aggregation for backlog refinement ceremony.

```json
{
  "currentSprint": { "id": "...", "number": 1, "state": "active" },
  "unrefinedItems": [
    {
      "id": "uuid",
      "type": "epic",
      "title": "Redesign authentication system",
      "description": "...",
      "priority": "high",
      "lifeArea": "next-chapter",
      "sprintCount": 0
    }
  ],
  "refinedButUnscheduled": [
    {
      "id": "uuid",
      "type": "story",
      "title": "Implement OAuth2",
      "status": "refined",
      "priority": "high",
      "lifeArea": "next-chapter"
    }
  ]
}
```

### CeremonyMidSprint
Data aggregation for mid-sprint review.

```json
{
  "currentSprint": { "id": "...", "number": 1, "state": "mid-review" },
  "currentDay": 7,
  "goals": [
    {
      "id": "uuid",
      "title": "Learn Docker networking",
      "completedAt": null,
      "addedAt": "2026-05-26T10:30:00Z"
    }
  ],
  "mobilityStreak": 5,
  "completedGoals": 0,
  "outstandingGoals": 3
}
```

### CeremonyRetro
Data aggregation for retrospective ceremony.

```json
{
  "sprintNumber": 1,
  "startDate": "2026-05-26",
  "endDate": "2026-06-09",
  "completedGoals": 2,
  "deferredGoals": 1,
  "droppedGoals": 0,
  "mobilityStreak": 11,
  "mobilityMisses": 3,
  "previousRetro": {
    "whatWentWell": ["Good team communication"],
    "improvements": ["Shorter standup meetings"],
    "blockers": ["Database migration delayed"]
  }
}
```

### ClosedSprint (History)
Archived sprint from history endpoint.

```json
{
  "id": "uuid",
  "number": 1,
  "state": "closed",
  "startDate": "2026-05-26",
  "endDate": "2026-06-09",
  "totalDays": 14,
  "completedGoals": 2,
  "deferredGoals": 1,
  "droppedGoals": 0,
  "mobilityStreak": 11,
  "mobilityMisses": 3,
  "retro": {
    "whatWentWell": ["Good momentum on learning"],
    "improvements": ["Better async updates"],
    "blockers": ["Work deadline pressure"],
    "completedAt": "2026-06-09T18:00:00Z"
  },
  "closedAt": "2026-06-09T18:00:00Z"
}
```

---

## Status Transition Rules

### Valid Status Transitions

```
raw → refined
refined → in-sprint
in-sprint → done | deferred | dropped
deferred → refined
dropped → [terminal, no transitions]
```

### Sprint State Transitions

```
active → mid-review | paused
mid-review → retro | active | paused
retro → paused | closed (via POST /sprint/close)
paused → active | closed (via POST /sprint/close)
```

---

## Validation Constraints

### At POST /sprint/start
- 1 ≤ goal count ≤ 5
- All goals have `status = refined`
- ≥1 goal has `lifeArea = next-chapter`
- No goal has `type = epic`
- Sprint not already active

### At POST /mobility/log
- One log per sprint per day
- `logDate` within sprint date range
- `logDate` not in future

### At PATCH /backlog/{id} (status transition)
- Follow legal transition rules above
- If transitioning to `deferred`, provide `deferredReason`
- If transitioning to `dropped`, provide `droppedReason`

### At POST /ceremony/retro
- Sprint state must be `retro`
- Must provide `responses` object with fields:
  - `whatWentWell` (string array, required)
  - `improvements` (string array, required)
  - `blockers` (string array, required)
  - `nextSprintFocus` (string, optional)

---

## Calculations

### Current Sprint Day
```
currentDay = DATEDIFF(day, sprint.startDate, TODAY()) + 1
Clamped to [1, totalDays]
```

### Mobility Streak
```
streak = consecutive days with mobility_logs.done = true, 
         counting backwards from today
```

### Goal Completion Rate
```
percentComplete = (completedGoals / totalGoals) * 100
```

---

## Full Endpoint Reference

All 23 API endpoints with request/response schemas:

### Health
- **GET /health** — Health check
  - Response: `{status: "ok"}`

### Sprints (6)
- **GET /sprint/current** — Get active sprint (null if none)
- **GET /sprint/{id}** — Get sprint by UUID
- **POST /sprint/start** — Start new sprint
  - Body: `{goalItemIds: ["uuid", ...]}`
  - Validates: 1–5 goals, ≥1 next-chapter, all refined, no epics
- **PATCH /sprint/state** — Transition sprint state
  - Body: `{sprintId: "uuid", state: "mid-review" | "retro" | "active" | "paused"}`
  - Validates: legal state transitions only
- **PATCH /sprint/goal/{id}** — Mark sprint goal complete/incomplete
  - Body: `{completedAt: "ISO-8601-timestamp" | null}`
  - `completedAt: null` marks goal as incomplete
- **POST /sprint/close** — Close sprint and archive
  - Body: `{sprintId: "uuid"}`
  - Action: defers incomplete items, sets state to closed

### Backlog (7)
- **GET /backlog** — List all items (grouped by status)
- **POST /backlog** — Create item
  - Body: `{type, title, description?, priority, lifeArea, subArea?}`
  - Creates with status: raw
- **GET /backlog/{id}** — Get item details
- **PATCH /backlog/{id}** — Update item
  - Body: `{status?, title?, description?, priority?, lifeArea?, subArea?, deferredReason?, droppedReason?}`
  - Validates: legal status transitions
- **DELETE /backlog/{id}** — Soft-delete item
  - Action: sets status to dropped
- **POST /backlog/{id}/decompose** — Break epic into stories
  - Body: `{stories: [{title, description?, priority}]}`
  - Creates child items with parentId
- **GET /backlog/{id}/children** — Get children of epic
  - Returns: array of child items

### Mobility (2)
- **POST /mobility/log** — Log today's mobility
  - Body: `{done: true | false}`
  - One log per sprint per day
- **GET /mobility/status** — Get streak + sprint history
  - Returns: current streak, lastLogged date, history array

### Ceremonies (4)
- **GET /ceremony/refinement** — Data for backlog refinement ceremony
- **GET /ceremony/mid-sprint** — Data for mid-sprint review ceremony
- **GET /ceremony/retro** — Data for retrospective ceremony
- **POST /ceremony/retro** — Submit retro responses
  - Body: `{whatWentWell: [...], improvements: [...], blockers: [...], nextSprintFocus?: "..."}`

### History (2)
- **GET /history** — List all closed sprints
- **GET /history/{id}** — Get closed sprint details

### Cron (2)
- **GET /cron/morning** — Morning check-in (mobility status)
- **GET /cron/evening** — Evening check-in (ask for mobility, escalate if missed)

---

## Error Responses

All endpoints return standard HTTP status codes:

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | GET, PATCH, POST ceremonies |
| 201 | Created | POST /sprint/start, POST /backlog |
| 204 | No Content | Some DELETE operations |
| 400 | Bad Request | Invalid state transition, max goals exceeded |
| 404 | Not Found | Sprint/item doesn't exist |
| 409 | Conflict | Sprint already active, duplicate log date |
| 500 | Server Error | Database error, unexpected exception |

**Error Response Format:**
```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": {/* optional details */}
}
```
