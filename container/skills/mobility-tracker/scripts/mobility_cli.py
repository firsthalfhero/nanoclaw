#!/usr/bin/env python3
"""Mobility Tracker — Firestore CLI.

Manages exercises and workout logs for the 'Mobility with Simon' app.

Firestore structure:
  users/users/exercises/{exerciseId}
  users/users/logs/{logId}

Required env var:
  FIREBASE_SERVICE_ACCOUNT — path to service account JSON file,
                              OR the raw JSON string itself.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Firebase init
# ---------------------------------------------------------------------------

def get_db():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print("ERROR: firebase-admin not installed. Run: pip3 install firebase-admin")
        sys.exit(1)

    sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not sa:
        print("ERROR: FIREBASE_SERVICE_ACCOUNT env var not set.")
        print("Set it to the path of your service account JSON file, or the raw JSON string.")
        sys.exit(1)

    if not firebase_admin._apps:
        # Accept either a file path or raw JSON string
        if sa.strip().startswith("{"):
            cred = credentials.Certificate(json.loads(sa))
        else:
            cred = credentials.Certificate(sa)
        firebase_admin.initialize_app(cred)

    return firestore.client()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

EXERCISES_PATH = ("users", "users", "exercises")
LOGS_PATH = ("users", "users", "logs")


def exercises_ref(db):
    return db.collection(EXERCISES_PATH[0]).document(EXERCISES_PATH[1]).collection(EXERCISES_PATH[2])


def logs_ref(db):
    return db.collection(LOGS_PATH[0]).document(LOGS_PATH[1]).collection(LOGS_PATH[2])


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------

def cmd_list_exercises(args):
    db = get_db()
    docs = exercises_ref(db).order_by("order").stream()
    items = [(d.id, d.to_dict()) for d in docs]
    if not items:
        print("No exercises found.")
        return
    print(f"{'#':<4} {'ID':<22} {'Name':<40} {'Focus Area':<15} {'Sets':<6} {'Reps'}")
    print("-" * 110)
    for i, (doc_id, ex) in enumerate(items, 1):
        print(f"{i:<4} {doc_id:<22} {ex.get('Name',''):<40} {ex.get('Focus_Area',''):<15} {ex.get('Target_Sets',''):<6} {ex.get('Target_Reps','')}")


def cmd_get_exercise(args):
    db = get_db()
    doc = exercises_ref(db).document(args.id).get()
    if not doc.exists:
        print(f"Exercise {args.id} not found.")
        sys.exit(1)
    data = doc.to_dict()
    print(f"ID:                  {doc.id}")
    for k, v in sorted(data.items()):
        print(f"{k:<22} {v}")


def cmd_add_exercise(args):
    db = get_db()
    # Determine next order value
    docs = list(exercises_ref(db).order_by("order", direction="DESCENDING").limit(1).stream())
    next_order = (docs[0].to_dict().get("order", 0) + 1) if docs else 0

    data = {
        "Name": args.name,
        "Focus_Area": args.focus_area,
        "Target_Sets": int(args.target_sets),
        "Target_Reps": args.target_reps,
        "Weight_Used_Initial": args.weight or "",
        "Video_Link": args.video or "",
        "Physio_Notes": args.notes or "",
        "order": next_order,
    }
    _, ref = exercises_ref(db).add(data)
    print(f"Exercise added: {ref.id}")
    print(f"  Name: {data['Name']}")
    print(f"  Focus Area: {data['Focus_Area']}")


def cmd_update_exercise(args):
    db = get_db()
    doc_ref = exercises_ref(db).document(args.id)
    doc = doc_ref.get()
    if not doc.exists:
        print(f"Exercise {args.id} not found.")
        sys.exit(1)

    updates = {}
    field_map = {
        "name": "Name",
        "focus_area": "Focus_Area",
        "target_sets": "Target_Sets",
        "target_reps": "Target_Reps",
        "weight": "Weight_Used_Initial",
        "video": "Video_Link",
        "notes": "Physio_Notes",
    }
    for arg_key, field_name in field_map.items():
        val = getattr(args, arg_key, None)
        if val is not None:
            updates[field_name] = int(val) if arg_key == "target_sets" else val

    if not updates:
        print("No fields to update. Use --name, --focus-area, --target-sets, --target-reps, --weight, --video, --notes")
        sys.exit(1)

    doc_ref.update(updates)
    print(f"Exercise {args.id} updated: {list(updates.keys())}")


def cmd_delete_exercise(args):
    db = get_db()
    doc_ref = exercises_ref(db).document(args.id)
    doc = doc_ref.get()
    if not doc.exists:
        print(f"Exercise {args.id} not found.")
        sys.exit(1)

    name = doc.to_dict().get("Name", args.id)
    if not args.yes:
        confirm = input(f"Delete exercise '{name}' and ALL its logs? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    # Delete related logs
    related = logs_ref(db).where("Exercise_ID", "==", args.id).stream()
    batch = db.batch()
    count = 0
    for log_doc in related:
        batch.delete(log_doc.reference)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.delete(doc_ref)
    batch.commit()
    print(f"Deleted exercise '{name}' and {count} related log(s).")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def fmt_date(ts):
    if ts is None:
        return ""
    try:
        return ts.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def cmd_list_logs(args):
    db = get_db()
    query = logs_ref(db)

    if args.exercise_id:
        query = query.where("Exercise_ID", "==", args.exercise_id)

    if args.date:
        try:
            day = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            next_day = day.replace(hour=23, minute=59, second=59)
            query = query.where("Date", ">=", day).where("Date", "<=", next_day)
        except ValueError:
            print("ERROR: --date must be in YYYY-MM-DD format")
            sys.exit(1)

    query = query.order_by("Date", direction="DESCENDING").limit(args.limit)
    docs = list(query.stream())

    if not docs:
        print("No logs found.")
        return

    # Fetch exercise names for display
    ex_names = {}
    ex_ids = {d.to_dict().get("Exercise_ID") for d in docs if d.to_dict().get("Exercise_ID")}
    for ex_id in ex_ids:
        ex_doc = exercises_ref(db).document(ex_id).get()
        ex_names[ex_id] = ex_doc.to_dict().get("Name", ex_id) if ex_doc.exists else ex_id

    print(f"{'Date':<18} {'Exercise':<35} {'Set':<5} {'Reps':<8} {'Weight':<15} {'Feel':<6} {'Variation'}")
    print("-" * 110)
    for d in docs:
        log = d.to_dict()
        ex_name = ex_names.get(log.get("Exercise_ID", ""), "")
        print(
            f"{fmt_date(log.get('Date')):<18} "
            f"{ex_name[:33]:<35} "
            f"{log.get('SetNumber',''):<5} "
            f"{log.get('Actual_Reps',''):<8} "
            f"{log.get('Weight_Used',''):<15} "
            f"{log.get('Subjective_Feeling',''):<6} "
            f"{log.get('Variation','')}"
        )


def cmd_add_log(args):
    db = get_db()
    # Validate exercise exists
    ex_doc = exercises_ref(db).document(args.exercise_id).get()
    if not ex_doc.exists:
        print(f"Exercise {args.exercise_id} not found.")
        sys.exit(1)

    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    data = {
        "Exercise_ID": args.exercise_id,
        "Date": SERVER_TIMESTAMP,
        "SetNumber": int(args.set_number),
        "Actual_Reps": args.reps,
        "Weight_Used": args.weight or "",
        "Variation": args.variation or "",
        "Subjective_Feeling": int(args.feeling) if args.feeling else 0,
        "Comments": args.comments or "",
        "Pain_Level": 0,  # legacy field — kept for schema consistency
    }
    _, ref = logs_ref(db).add(data)
    ex_name = ex_doc.to_dict().get("Name", args.exercise_id)
    print(f"Log added: {ref.id}")
    print(f"  Exercise: {ex_name}")
    print(f"  Set {data['SetNumber']}: {data['Actual_Reps']} reps @ {data['Weight_Used']}")


def cmd_delete_log(args):
    db = get_db()
    doc_ref = logs_ref(db).document(args.id)
    doc = doc_ref.get()
    if not doc.exists:
        print(f"Log {args.id} not found.")
        sys.exit(1)
    doc_ref.delete()
    print(f"Log {args.id} deleted.")


def cmd_summary(args):
    """Show a quick summary: exercise count and log count."""
    db = get_db()
    ex_count = len(list(exercises_ref(db).stream()))
    log_count = len(list(logs_ref(db).stream()))
    print(f"Exercises: {ex_count}")
    print(f"Log entries: {log_count}")
    if log_count > 0:
        recent = list(logs_ref(db).order_by("Date", direction="DESCENDING").limit(1).stream())
        if recent:
            last = recent[0].to_dict()
            print(f"Last logged: {fmt_date(last.get('Date'))}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Mobility Tracker Firestore CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # exercises
    sub.add_parser("list-exercises", help="List all exercises")

    p = sub.add_parser("get-exercise", help="Show full details of one exercise")
    p.add_argument("id", help="Exercise document ID")

    p = sub.add_parser("add-exercise", help="Add a new exercise")
    p.add_argument("--name", required=True)
    p.add_argument("--focus-area", dest="focus_area", required=True)
    p.add_argument("--target-sets", dest="target_sets", required=True)
    p.add_argument("--target-reps", dest="target_reps", required=True)
    p.add_argument("--weight", help="Weight_Used_Initial")
    p.add_argument("--video", help="Video_Link URL")
    p.add_argument("--notes", help="Physio_Notes")

    p = sub.add_parser("update-exercise", help="Update fields on an exercise")
    p.add_argument("id", help="Exercise document ID")
    p.add_argument("--name")
    p.add_argument("--focus-area", dest="focus_area")
    p.add_argument("--target-sets", dest="target_sets")
    p.add_argument("--target-reps", dest="target_reps")
    p.add_argument("--weight")
    p.add_argument("--video")
    p.add_argument("--notes")

    p = sub.add_parser("delete-exercise", help="Delete an exercise and all its logs")
    p.add_argument("id", help="Exercise document ID")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    # logs
    p = sub.add_parser("list-logs", help="List workout logs")
    p.add_argument("--exercise-id", dest="exercise_id", help="Filter by exercise ID")
    p.add_argument("--date", help="Filter by date (YYYY-MM-DD)")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("add-log", help="Add a workout log entry")
    p.add_argument("--exercise-id", dest="exercise_id", required=True)
    p.add_argument("--set-number", dest="set_number", required=True)
    p.add_argument("--reps", required=True)
    p.add_argument("--weight", help="Weight used")
    p.add_argument("--variation")
    p.add_argument("--feeling", help="Subjective feeling 0-10")
    p.add_argument("--comments")

    p = sub.add_parser("delete-log", help="Delete a single log entry")
    p.add_argument("id", help="Log document ID")

    sub.add_parser("summary", help="Show exercise and log counts")

    args = parser.parse_args()

    commands = {
        "list-exercises": cmd_list_exercises,
        "get-exercise": cmd_get_exercise,
        "add-exercise": cmd_add_exercise,
        "update-exercise": cmd_update_exercise,
        "delete-exercise": cmd_delete_exercise,
        "list-logs": cmd_list_logs,
        "add-log": cmd_add_log,
        "delete-log": cmd_delete_log,
        "summary": cmd_summary,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
