# life-areas.md

Life area taxonomy for categorizing backlog items and sprint goals.

---

## Overview

All backlog items must be tagged with a **life area** and optional **sub-area**. This ensures balance across life domains and prevents any area from being neglected.

**Three primary life areas:**
1. **Health** — Physical well-being, medical care, mobility
2. **Next-Chapter** — Learning, growth, skill development
3. **Home-Family** — Family, living space, relationships, admin

**Constraint:** Every sprint must include ≥1 `next-chapter` goal (enforced at `POST /sprint/start`).

---

## Life Area: Health

Focus on physical well-being, medical care, fitness, and daily mobility.

### Sub-Areas

| Sub-Area | Examples | Notes |
|----------|----------|-------|
| `medical` | Doctor visit, prescription refill, annual checkup, bloodwork, mental health session | Preventive and reactive care |
| `gym` | Strength training, cardio, yoga, fitness class, personal training | Structured exercise |
| `mobility` | Daily movement tracking, walking, stretching, physiotherapy, pain management | Non-negotiable daily baseline |

### Item Examples

**Medical:**
```json
{
  "type": "task",
  "title": "Annual physical exam",
  "lifeArea": "health",
  "subArea": "medical",
  "priority": "high",
  "description": "Schedule and complete annual health checkup with primary care doctor"
}
```

**Gym:**
```json
{
  "type": "story",
  "title": "Establish 3x weekly gym routine",
  "lifeArea": "health",
  "subArea": "gym",
  "priority": "high",
  "description": "Commit to 3 strength training sessions per week for 4 weeks"
}
```

**Mobility:**
```json
{
  "type": "task",
  "title": "Daily mobility 10 min",
  "lifeArea": "health",
  "subArea": "mobility",
  "priority": "asap",
  "description": "Non-negotiable: move for 10 min every day"
}
```

### Patterns to Watch

- **Medical neglect:** Putting off doctor visits, ignoring symptoms
- **Gym abandonment:** Committing to gym, then dropping it within 2 weeks
- **Mobility slip:** Daily tracking breaks during high-stress work periods

---

## Life Area: Next-Chapter

Focus on learning, growth, skill development, and thinking about future direction.

### Sub-Areas

| Sub-Area | Examples | Notes |
|----------|----------|-------|
| `learning` | Reading, online course, tutorial, documentation study, skill building | Structured knowledge acquisition |
| `skills` | Coding practice, writing, design, technical skill depth, soft skills | Hands-on application of knowledge |
| `thinking` | Strategic planning, career reflection, goal setting, life vision, decision making | Meta-cognitive and planning work |

### Item Examples

**Learning:**
```json
{
  "type": "story",
  "title": "Learn Docker networking",
  "lifeArea": "next-chapter",
  "subArea": "learning",
  "priority": "high",
  "description": "Complete Docker networking course: bridge networks, host networks, overlay networks"
}
```

**Skills:**
```json
{
  "type": "story",
  "title": "Build API authentication system",
  "lifeArea": "next-chapter",
  "subArea": "skills",
  "priority": "high",
  "description": "Implement OAuth2 from scratch in a side project"
}
```

**Thinking:**
```json
{
  "type": "story",
  "title": "Define 5-year career direction",
  "lifeArea": "next-chapter",
  "subArea": "thinking",
  "priority": "high",
  "description": "Write vision for next 5 years: roles, skills, impact areas"
}
```

### Patterns to Watch

- **Learning debt:** Learning goals always deferred to next sprint
- **Skill stagnation:** No growth goals for multiple sprints
- **Thinking avoidance:** Never making time for strategic reflection

### Sprint Requirement

**Every sprint must include ≥1 next-chapter goal.** This prevents George from getting stuck in pure execution mode without growth.

**Examples of valid next-chapter goals:**
- ✅ Learning a new framework
- ✅ Deepening existing skills (practice)
- ✅ Reflecting on career direction
- ✅ Reading a book related to work
- ✅ Teaching someone else (learning by explaining)
- ✅ Documenting knowledge for future reference

**Examples of invalid:**
- ❌ "Keep my existing skills sharp" (too vague, not a goal)
- ❌ "Do my job well" (that's execution, not learning)
- ❌ "Think about growth" (not specific enough)

---

## Life Area: Home-Family

Focus on family relationships, home maintenance, life administration, and personal projects.

### Sub-Areas

| Sub-Area | Examples | Notes |
|----------|----------|-------|
| `kids` | School activities, sports, homework, parenting time, quality time | Responsibilities and bonding with children |
| `emily` | Date nights, quality time, relationship building, communication, listening | Partnership and connection with spouse |
| `life-admin` | Bills, taxes, insurance, legal docs, scheduling, planning, HR tasks | Administrative overhead of life |
| `chores` | Cleaning, laundry, cooking, dishes, yard work, home maintenance | Daily and weekly household tasks |
| `projects` | Home renovations, repairs, creative projects, car maintenance, side projects | One-off or medium-term household projects |

### Item Examples

**Kids:**
```json
{
  "type": "task",
  "title": "Attend kid's soccer game + post-game dinner",
  "lifeArea": "home-family",
  "subArea": "kids",
  "priority": "high",
  "description": "Make it to Saturday game and have family dinner after"
}
```

**Emily:**
```json
{
  "type": "task",
  "title": "Plan and execute date night",
  "lifeArea": "home-family",
  "subArea": "emily",
  "priority": "high",
  "description": "Book restaurant, arrange childcare, spend quality time together"
}
```

**Life-Admin:**
```json
{
  "type": "task",
  "title": "Renew car insurance and update policy",
  "lifeArea": "home-family",
  "subArea": "life-admin",
  "priority": "medium",
  "description": "Review coverage, get quotes, renew before expiration date"
}
```

**Chores:**
```json
{
  "type": "task",
  "title": "Deep clean kitchen and bathroom",
  "lifeArea": "home-family",
  "subArea": "chores",
  "priority": "medium",
  "description": "Kitchen: cabinets, floors. Bathroom: tile, fixtures, shower"
}
```

**Projects:**
```json
{
  "type": "story",
  "title": "Repaint master bedroom",
  "lifeArea": "home-family",
  "subArea": "projects",
  "priority": "low",
  "description": "Select paint color, prep walls, paint both coats, trim work"
}
```

### Patterns to Watch

- **Family neglect:** Work creep pushes out family time
- **Relationship decay:** Emily/kids goals consistently deferred
- **Administrative chaos:** Never doing life-admin, bills piling up
- **Home deterioration:** Chores always deferred, living space suffers

---

## Sprint Balance Framework

Ideal sprint goal distribution (not rigid, but aim for this):

| Life Area | Target Goals | Notes |
|-----------|-------------|-------|
| Health | 1–2 | At least 1 (usually gym or mobility related) |
| Next-Chapter | 1–2 | Always ≥1 (required by rule) |
| Home-Family | 1–2 | Balance family, kids, admin, projects |

**Example balanced sprint:**
- Goal 1: Health — "3x gym sessions" (gym)
- Goal 2: Next-Chapter — "Learn GraphQL basics" (learning)
- Goal 3: Home-Family — "Plan and execute date night" (emily)
- Goal 4: Next-Chapter — "Build API authentication" (skills)
- Goal 5: Home-Family — "Deep clean house" (chores)

**Not balanced (too much work, neglecting family):**
- Goal 1: Work project
- Goal 2: Work project
- Goal 3: Learning
- Goal 4: Learning
- Goal 5: Gym

---

## When Assigning Items to Sprints

Ask these questions:

1. **Is this item in the right life area?**
   - If it's learning → should be `next-chapter`
   - If it's fitness → should be `health`
   - If it's family time → should be `home-family`

2. **Does this sprint have balance?**
   - Count by life area
   - If all work and learning, add family/health goals
   - If all family, add learning goal

3. **Is the next-chapter goal present?**
   - Sprint cannot start without ≥1 next-chapter goal
   - Fail planning if missing

4. **Are goals vague?**
   - "Health" is not specific (needs sub-area)
   - "Learn stuff" is not specific (needs topic)
   - "Family time" is not specific (needs who and what)

---

## Escalation by Life Area

If a life area is consistently neglected (no goals for 3+ sprints), escalate:

**Health neglect:**
- Level 2: "Your health isn't in this sprint. Let's add a goal."
- Level 3: "You've skipped health goals for three sprints. What's going on?"
- Level 4: "Health is non-negotiable. We're adding a mobility goal this sprint."

**Next-Chapter neglect:**
- Level 1–2: Remind that rule requires ≥1 goal per sprint
- Level 3: "You keep deferring learning. Why?"
- Level 4: "Growth is part of the system. We're picking a learning goal right now."

**Home-Family neglect:**
- Level 2: "Family time isn't in this sprint. That's important."
- Level 3: "You've neglected family goals for two sprints. What's the pattern?"
- Level 4: "Work is not more important than family. We're blocking time."

---

## Nanoclaw Skill Integration

When implementing life-area tagging in Nanoclaw:

1. **Enforce tags** — Every item must have `lifeArea` and ideally `subArea`
2. **Validate sprints** — Refuse to start sprint without ≥1 next-chapter goal
3. **Show balance** — Display sprint composition by life area
4. **Highlight neglect** — Flag if any life area hasn't been touched in 2+ sprints
5. **Suggest variety** — When planning, remind George to include neglected areas

**Example Nanoclaw prompt:**
```
You have 3 goals so far, all in work/learning. Let's balance this:
- Health: nothing yet. Add a gym or medical goal?
- Home-Family: nothing yet. Add time with Emily or kids?

Remember: ≥1 next-chapter is required. You have 2 learning goals, which is good. 
But health/family are also important. Let's round out the sprint.
```
