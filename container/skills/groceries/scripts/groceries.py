#!/usr/bin/env python3
"""Grocery list manager. Data stored at /opt/state/groceries.json."""

import json
import os
import sys
import tempfile
from datetime import date

DATA_FILE = os.environ.get("GROCERIES_STATE_FILE", "/workspace/group/groceries-state.json")
CATEGORY_ORDER = ["meat", "fruit-veg", "store", "pantry", "chemist", "other"]
CATEGORY_LABELS = {
    "meat": "Meat",
    "fruit-veg": "Fruit & Veg",
    "store": "Store",
    "pantry": "Pantry",
    "chemist": "Chemist",
    "other": "Other",
}


def load():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"items": []}


def save(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=os.path.dirname(DATA_FILE))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def cmd_list(args):
    """List items. Usage: list [--alpha]"""
    data = load()
    items = data.get("items", [])
    if not items:
        print("Your grocery list is empty.")
        return

    alpha = "--alpha" in args

    if alpha:
        items_sorted = sorted(items, key=lambda x: x["name"].lower())
        print(f"Grocery List ({len(items_sorted)} items)\n")
        for item in items_sorted:
            line = f"- {item['name']}"
            if item.get("quantity"):
                line += f" ({item['quantity']})"
            if item.get("note"):
                line += f" - {item['note']}"
            print(line)
    else:
        by_cat = {}
        for item in items:
            cat = item.get("category", "other")
            by_cat.setdefault(cat, []).append(item)

        print(f"Grocery List ({len(items)} items)\n")
        for cat in CATEGORY_ORDER:
            if cat not in by_cat:
                continue
            cat_items = sorted(by_cat[cat], key=lambda x: x["name"].lower())
            print(f"**{CATEGORY_LABELS.get(cat, cat)}**")
            for item in cat_items:
                line = f"- {item['name']}"
                if item.get("quantity"):
                    line += f" ({item['quantity']})"
                if item.get("note"):
                    line += f" - {item['note']}"
                print(line)
            print()


def cmd_add(args):
    """Add items. Usage: add <name> [category] [quantity] [note] [-- <name2> [category2] ...]
    Each item is: name [category] [quantity] [note], separated by --
    """
    if not args:
        print("Error: provide at least one item name.")
        print("Usage: groceries.py add <name> [category] [quantity] [note] [-- <name2> ...]")
        sys.exit(1)

    data = load()
    chunks = []
    current = []
    for a in args:
        if a == "--":
            if current:
                chunks.append(current)
            current = []
        else:
            current.append(a)
    if current:
        chunks.append(current)

    added = []
    for chunk in chunks:
        name = chunk[0]
        category = chunk[1] if len(chunk) > 1 else "other"
        quantity = chunk[2] if len(chunk) > 2 else ""
        note = chunk[3] if len(chunk) > 3 else ""
        item = {
            "name": name,
            "category": category,
            "quantity": quantity,
            "note": note,
            "added": date.today().isoformat(),
        }
        data["items"].append(item)
        added.append(item)

    save(data)
    for item in added:
        line = f"Added: {item['name']} ({CATEGORY_LABELS.get(item['category'], item['category'])})"
        if item["quantity"]:
            line += f" - {item['quantity']}"
        print(line)
    print(f"\nTotal items: {len(data['items'])}")


def cmd_remove(args):
    """Remove items by name. Usage: remove <name> [<name2> ...]"""
    if not args:
        print("Error: provide item name(s) to remove.")
        sys.exit(1)

    data = load()
    targets = [a.lower() for a in args]
    removed = []
    kept = []
    for item in data["items"]:
        if item["name"].lower() in targets:
            removed.append(item["name"])
        else:
            kept.append(item)

    data["items"] = kept
    save(data)

    if removed:
        print(f"Removed: {', '.join(removed)}")
    else:
        print(f"No items matched: {', '.join(args)}")
    print(f"Remaining items: {len(data['items'])}")


def cmd_bought(args):
    """Remove bought items. Usage: bought --all | bought --all-except <name> [<name2>...] | bought <name> [<name2>...]"""
    if not args:
        print("Error: specify what was bought.")
        print("Usage: bought --all | bought --all-except <name> ... | bought <name> ...")
        sys.exit(1)

    data = load()

    if args[0] == "--all":
        count = len(data["items"])
        data["items"] = []
        save(data)
        print(f"Cleared all {count} items. Your grocery list is now empty.")
        return

    if args[0] == "--all-except":
        keep_names = [a.lower() for a in args[1:]]
        removed = []
        kept = []
        for item in data["items"]:
            if item["name"].lower() in keep_names:
                kept.append(item)
            else:
                removed.append(item["name"])
        data["items"] = kept
        save(data)
        print(f"Removed: {', '.join(removed) if removed else '(none)'}")
        print(f"Kept: {', '.join(i['name'] for i in kept) if kept else '(none)'}")
        print(f"Remaining items: {len(data['items'])}")
        return

    # Bought specific items - remove them
    targets = [a.lower() for a in args]
    removed = []
    kept = []
    for item in data["items"]:
        if item["name"].lower() in targets:
            removed.append(item["name"])
        else:
            kept.append(item)
    data["items"] = kept
    save(data)
    print(f"Removed: {', '.join(removed) if removed else '(none)'}")
    print(f"Remaining items: {len(data['items'])}")


def cmd_clear(_args):
    """Clear all items. Usage: clear"""
    data = load()
    count = len(data["items"])
    data["items"] = []
    save(data)
    print(f"Cleared {count} items. Your grocery list is now empty.")


def cmd_update(args):
    """Update an item. Usage: update <name> [--quantity <q>] [--note <n>] [--category <c>]"""
    if not args:
        print("Error: provide item name to update.")
        sys.exit(1)

    name = args[0].lower()
    data = load()

    found = None
    for item in data["items"]:
        if item["name"].lower() == name:
            found = item
            break

    if not found:
        print(f"Item not found: {args[0]}")
        sys.exit(1)

    i = 1
    while i < len(args):
        if args[i] == "--quantity" and i + 1 < len(args):
            found["quantity"] = args[i + 1]
            i += 2
        elif args[i] == "--note" and i + 1 < len(args):
            found["note"] = args[i + 1]
            i += 2
        elif args[i] == "--category" and i + 1 < len(args):
            found["category"] = args[i + 1]
            i += 2
        else:
            i += 1

    save(data)
    print(f"Updated: {found['name']}")


COMMANDS = {
    "list": cmd_list,
    "add": cmd_add,
    "remove": cmd_remove,
    "bought": cmd_bought,
    "clear": cmd_clear,
    "update": cmd_update,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Grocery List Manager")
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        print("\nExamples:")
        print("  groceries.py list")
        print("  groceries.py list --alpha")
        print('  groceries.py add Bread bakery "" ""')
        print("  groceries.py add Milk fruit-veg 1L -- Eggs other 12 free-range")
        print("  groceries.py remove Bread")
        print("  groceries.py bought Bread Milk")
        print("  groceries.py bought --all")
        print("  groceries.py bought --all-except Milk Eggs")
        print("  groceries.py clear")
        print('  groceries.py update Milk --quantity 2L --note "semi-skimmed"')
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
