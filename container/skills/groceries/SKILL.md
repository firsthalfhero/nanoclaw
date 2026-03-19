---
name: groceries
description: Track and manage a grocery shopping list. Use when the user wants to add, remove, check off, or view grocery items they need to order or buy. Also triggers when the user says they bought or got items (e.g. "I bought the bread", "I got everything except milk", "done shopping"), for meal planning, pantry tracking, or "what do I need from the store" queries. Any mention of buying, purchasing, or having gotten grocery items should trigger this skill to update the list.
metadata: { "openclaw": { "emoji": "🛒" } }
---

# Groceries

Use the `groceries.py` script for ALL grocery operations. ALWAYS run the script — never make up data.

Script location: `/home/node/.claude/skills/groceries/scripts/groceries.py`
Fallback path: `/home/node/.claude/skills/groceries/scripts/groceries.py`

Categories: `meat`, `fruit-veg`, `store`, `pantry`, `chemist`, `other`.

## Commands

Show the list (grouped by category):

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py list
```

Show the list (alphabetical):

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py list --alpha
```

Add items (each item: name category quantity note, separated by `--`):

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py add Bread bakery "" ""
python3 /home/node/.claude/skills/groceries/scripts/groceries.py add Milk fruit-veg 1L "" -- Eggs other 12 free-range
```

Remove items by name:

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py remove Bread
python3 /home/node/.claude/skills/groceries/scripts/groceries.py remove Bread Milk
```

Mark items as bought (removes them):

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py bought Bread Milk
```

Bought everything:

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py bought --all
```

Bought everything except specific items:

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py bought --all-except Milk Eggs
```

Update an item:

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py update Milk --quantity 2L --note "semi-skimmed"
```

Clear all items:

```bash
python3 /home/node/.claude/skills/groceries/scripts/groceries.py clear
```

## Rules

- ALWAYS run the script. NEVER guess or fabricate grocery data.
- Infer category from the item name (e.g. chicken -> meat, apples -> fruit-veg, toothpaste -> chemist, detergent -> store).
- When adding multiple items, combine them in one command using `--` separators.
- When the user says "I bought X" or "I got X", run the `bought` command to remove those items.
- When the user says "I got everything except X", run `bought --all-except X`.
- After any modification, run `list` to show the updated list.
