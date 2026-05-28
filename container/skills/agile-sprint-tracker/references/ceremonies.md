# ceremonies.md

Four mandatory ceremonies per 2-week sprint with scripts, edge cases, and guardrails.

---

## Overview

| Ceremony | When | Duration | Focus | Prep Endpoint |
|----------|------|----------|-------|---------------|
| Backlog Refinement | Days 3–4, 10–11 | 15–20 min | Decompose, clarify, estimate | `GET /ceremony/refinement` |
| Sprint Planning | Day 1, post-retro | 20–30 min | Select goals, confirm scope | (no prep endpoint) |
| Mid-Sprint Review | Day 7 | 10–15 min | Check progress, unblock | `GET /ceremony/mid-sprint` |
| Retrospective | Day 14 | 15–20 min | Reflect, improve, plan next | `GET /ceremony/retro` |

---

## 1. Backlog Refinement

**Cadence:** Days 3–4 (first half) and days 10–11 (second half)
**Duration:** 15–20 minutes
**Objective:** Move items from `raw` → `refined`, ready for sprint planning

### Pre-Ceremony

**Call endpoint:**
```bash
curl http://agilelife.home/ceremony/refinement | jq
```

**Returns:**
```json
{
  "currentSprint": { "id": "...", "number": 1, "state": "active" },
  "unrefinedItems": [ /* raw items waiting for clarification */ ],
  "refinedButUnscheduled": [ /* refined items not yet in sprint */ ]
}
```

### Script

1. **Review unrefined items** (5 min)
   - Read each `raw` item's title and description
   - Ask:
     - "Is this clear enough to work on?"
     - "What does done look like?"
     - "How long would this take?"
   - If unclear: discuss until clear
   - If clear: move to `refined` status

   ```bash
   curl -X PATCH http://agilelife.home/backlog/{id} \
     -H "Content-Type: application/json" \
     -d '{"status": "refined"}'
   ```

2. **Handle epics** (5 min)
   - If any epic is marked `refined`, it **must be decomposed** before next planning
   - Decompose epic into 2–4 child stories

   ```bash
   curl -X POST http://agilelife.home/backlog/{epicId}/decompose \
     -H "Content-Type: application/json" \
     -d '{
       "stories": [
         {"title": "Child story 1", "priority": "high"},
         {"title": "Child story 2", "priority": "medium"}
       ]
     }'
   ```

3. **Build "ready" backlog** (5 min)
   - Confirm at least 5–8 refined stories are ready for next planning
   - If fewer: refine more items or decompose pending epics

### Edge Cases

**Edge Case 1: Unrefined items at planning time**
- Do not allow `raw` items in sprint goals
- Push refinement earlier or defer item to following sprint

**Edge Case 2: Epic too large to decompose quickly**
- Decompose only the first 2–3 stories this ceremony
- Flag remaining stories for next refinement

**Edge Case 3: Item deemed dropped during refinement**
- Use `DELETE /backlog/{id}` to soft-delete
- Provide `droppedReason` (e.g., "no longer relevant", "blocked indefinitely")

---

## 2. Sprint Planning

**Cadence:** Day 1 (immediately after retrospective of previous sprint, if any)
**Duration:** 20–30 minutes
**Objective:** Select 1–5 sprint goals, confirm scope, start sprint

### Pre-Ceremony (No endpoint prep)

**Have ready:**
- List of refined backlog items (from refinement ceremony)
- Previous sprint's retro notes (if any)
- Life area goals for this sprint (what's the focus?)

### Script

1. **Review sprint purpose** (2 min)
   - Discuss life areas for this sprint
   - Confirm ≥1 goal will be `next-chapter` (learning/growth)
   - Example: "This sprint focuses on learning and project delivery"

2. **Select sprint goals** (10 min)
   - Go through refined backlog
   - Ask per item: "Does this fit our sprint focus?"
   - Mark items as sprint goals (max 5)
   - Confirm ≥1 is `lifeArea: next-chapter`

   **Validation guardrails:**
   - Max 5 goals (enforce hard)
   - ≥1 next-chapter goal (enforce hard)
   - All must have `status: refined`
   - No `type: epic` allowed

3. **Start sprint** (5 min)
   ```bash
   curl -X POST http://agilelife.home/sprint/start \
     -H "Content-Type: application/json" \
     -d '{
       "goalItemIds": ["uuid-goal-1", "uuid-goal-2", "uuid-goal-3"]
     }'
   ```

4. **Confirm sprint state** (3 min)
   ```bash
   curl http://agilelife.home/sprint/current | jq '.state'
   # Should be: "active"
   ```

### Edge Cases

**Edge Case 1: Less than 3 refined items ready**
- Still start sprint (could have 1–2 goals if that's all that's ready)
- Use cron/evening check-in to refine more asynchronously
- Don't force scope just to hit a number

**Edge Case 2: George wants to add an unrefined item last-minute**
- Deny. "Let's get it refined next ceremony, add it mid-sprint if urgent."
- Protect planning integrity

**Edge Case 3: Too many good items, can't pick 5**
- Prioritize by life area (next-chapter first)
- Prioritize by urgency (health/family concerns)
- Rest moves to next sprint—don't overload

---

## 3. Mid-Sprint Review

**Cadence:** Day 7 (exactly halfway through sprint)
**Duration:** 10–15 minutes
**Objective:** Check progress, identify blockers, adjust course if needed

### Pre-Ceremony

**Call endpoint:**
```bash
curl http://agilelife.home/ceremony/mid-sprint | jq
```

**Returns:**
```json
{
  "currentSprint": { "id": "...", "number": 1, "state": "active" },
  "currentDay": 7,
  "goals": [
    {"id": "...", "title": "...", "completedAt": null}
  ],
  "mobilityStreak": 5,
  "completedGoals": 0,
  "outstandingGoals": 3
}
```

### Script

1. **Review goal progress** (5 min)
   - For each goal, ask:
     - "What's the status?"
     - "Is this on track?"
     - "Are there blockers?"
   - If blocked: discuss solutions
   - If on track: confirm next steps

2. **Check mobility** (2 min)
   - Review current streak
   - If streak < 3: ask "What's happening with mobility?"
   - If streak = 0: escalate (Level 3–4 depending on reason)

3. **Adjust if needed** (3 min)
   - If goal is unlikely to complete: defer it
   - If goal is easily doable: confirm completion path

   ```bash
   curl -X PATCH http://agilelife.home/backlog/{id} \
     -H "Content-Type: application/json" \
     -d '{
       "status": "deferred",
       "deferredReason": "Blocked by X, will revisit next sprint"
     }'
   ```

4. **No state change**
   - Sprint stays in `active` state
   - Just review; don't formally transition to `mid-review` unless retro prep starts

### Edge Cases

**Edge Case 1: All goals are done by day 7**
- Celebrate
- Ask: "Want to add something from backlog?"
- If yes: use PATCH to move refined item to `in-sprint` and update goal

**Edge Case 2: No progress on any goal**
- Escalate (Level 3–4): "This is a pattern. What's blocking us?"
- Discuss whether goals are realistic or if external pressure is crushing scope
- Don't soften; be direct

**Edge Case 3: Mobility streak is broken**
- If 1 miss: "Let's get back on track"
- If 2+ misses: escalate per `escalation.md`

---

## 4. Retrospective

**Cadence:** Day 14 (last day of sprint)
**Duration:** 15–20 minutes
**Objective:** Reflect on sprint, identify improvements, prepare for closure

### Pre-Ceremony

**Call endpoint:**
```bash
curl http://agilelife.home/ceremony/retro | jq
```

**Returns:**
```json
{
  "sprintNumber": 1,
  "completedGoals": 2,
  "deferredGoals": 1,
  "droppedGoals": 0,
  "mobilityStreak": 11,
  "mobilityMisses": 3,
  "previousRetro": { /* prior sprint's retro */ }
}
```

### Script

1. **Reflect on goals** (5 min)
   - What was completed?
   - What was deferred and why?
   - What was dropped and why?
   - Pattern analysis: Are we consistently deferring certain types of work?

2. **Reflect on mobility** (2 min)
   - Streak achieved vs. goal
   - Reasons for misses
   - Pattern: Is mobility being sacrificed for work?

3. **Answer retro questions** (5 min)
   - **What went well?** (2–3 items)
     - Example: "Good gym consistency", "Learned Docker networking"
   - **What could improve?** (2–3 items)
     - Example: "Schedule more buffer for work deadlines", "Better async communication"
   - **What blocked us?** (2–3 items)
     - Example: "Kid sick mid-week", "Database migration delayed"

4. **Submit retro** (3 min)
   ```bash
   curl -X POST http://agilelife.home/ceremony/retro \
     -H "Content-Type: application/json" \
     -d '{
       "whatWentWell": [
         "Good gym consistency",
         "Learned Docker networking"
       ],
       "improvements": [
         "Schedule work buffer better",
         "More async communication"
       ],
       "blockers": [
         "Kid sick mid-week"
       ],
       "nextSprintFocus": "Health + Learning balance"
     }'
   ```

5. **Close sprint** (trigger closing)
   ```bash
   curl -X POST http://agilelife.home/sprint/close \
     -H "Content-Type: application/json" \
     -d '{"sprintId": "uuid"}'
   ```

### Edge Cases

**Edge Case 1: Very little to show for the sprint**
- Don't sugar-coat it
- Ask: "What happened? External pressure? Goals too ambitious? Scope creep?"
- Discuss how to protect sprint boundary next time

**Edge Case 2: Multiple mobility misses**
- Escalate (Level 4–5): "Mobility is non-negotiable. What do we need to change?"
- Review impact on sprint completion
- Consider whether work commitments are unsustainable

**Edge Case 3: Same blockers as last sprint**
- Flag as a pattern: "This is the second sprint blocked by X. What's the fix?"
- Don't let recurring blockers slide

**Edge Case 4: George is too self-critical**
- Counter: "You completed X and maintained Y streak. That's not failure."
- Balance accountability with compassion

---

## Ceremony Guardrails

### Before Any Ceremony

1. **Fetch current sprint state:**
   ```bash
   curl http://agilelife.home/sprint/current
   ```
   If no active sprint, ceremonies cannot proceed (except planning).

2. **Check mobility:**
   - If streak is broken, address it immediately
   - Don't delay mobility check-in to next cron

### During Any Ceremony

1. **No scope creep in planning** — Max 5 goals, enforce hard
2. **No unrefined items in sprint** — All goals must be `status: refined`
3. **No epics in sprint** — Decompose first, sprint after
4. **No backwards transitions** — Status and state only move forward
5. **Mobility is never negotiable** — Ask every ceremony

### After Any Ceremony

1. **Confirm data persisted:**
   ```bash
   curl http://agilelife.home/sprint/current
   ```
   Verify changes applied correctly

2. **Log if updated manually:**
   - If mobility was logged: POST `/mobility/log`
   - If items were updated: confirm via GET `/backlog`

---

## Ceremony Checklist

### Backlog Refinement ✓
- [ ] Call `/ceremony/refinement` endpoint
- [ ] Review all `raw` items
- [ ] Move clear items to `refined`
- [ ] Decompose any epics marked refined
- [ ] Confirm 5–8 stories ready for planning
- [ ] No epics left in refined state

### Sprint Planning ✓
- [ ] Have refined backlog ready
- [ ] Discuss sprint focus (life areas)
- [ ] Select 1–5 goals (max 5, ≥1 next-chapter)
- [ ] POST `/sprint/start` with goal UUIDs
- [ ] Confirm sprint state is `active`
- [ ] Log mobility for day 1

### Mid-Sprint Review ✓
- [ ] Call `/ceremony/mid-sprint` endpoint
- [ ] Review each goal's status
- [ ] Check mobility streak
- [ ] Identify any blockers
- [ ] Defer incomplete goals if unlikely to finish
- [ ] Log mobility for day 7

### Retrospective ✓
- [ ] Call `/ceremony/retro` endpoint
- [ ] Reflect on completions, deferrals, drops
- [ ] Check mobility streak (final day)
- [ ] Answer: what went well, improvements, blockers
- [ ] POST `/ceremony/retro` with responses
- [ ] POST `/sprint/close` to archive sprint
- [ ] Confirm sprint state is `closed`

---

## Notes for Nanoclaw Skill

When invoking ceremonies from Nanoclaw:

1. Always fetch endpoint data first (prep)
2. Dialogue with George (guided ceremony workflow)
3. Update backlog and sprint based on responses
4. Persist changes via API
5. Confirm state changes with GET endpoints

**Be active, not passive.** Drive the ceremony; don't just present data. Push back on vague reflections, escalate blockers, protect scope.
