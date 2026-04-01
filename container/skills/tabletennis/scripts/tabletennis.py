#!/usr/bin/env python3
"""Table tennis club tracker for George and Henry at Pinball TT Club.

Database: /workspace/group/tabletennis.db
"""

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "/workspace/group/tabletennis.db"

ENTRY_FEE_WITH_LESSON = 5.00
ENTRY_FEE_NO_LESSON = 12.00
LOW_CREDIT_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _migrate(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT NOT NULL,
            day_of_week TEXT,
            george_attended INTEGER DEFAULT 0,
            henry_attended INTEGER DEFAULT 0,
            george_had_lesson INTEGER DEFAULT 0,
            henry_had_lesson INTEGER DEFAULT 0,
            george_entry_fee REAL DEFAULT 0,
            henry_entry_fee REAL DEFAULT 0,
            total_entry_fee REAL DEFAULT 0,
            entry_fee_paid INTEGER DEFAULT 0,
            entry_fee_paid_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lesson_credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_date TEXT NOT NULL,
            amount_paid REAL DEFAULT 800.00,
            lessons_purchased INTEGER DEFAULT 10,
            lessons_used INTEGER DEFAULT 0,
            paid_to TEXT DEFAULT 'James Wong',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lesson_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT NOT NULL,
            member TEXT NOT NULL,
            credit_block_id INTEGER,
            FOREIGN KEY (credit_block_id) REFERENCES lesson_credits(id)
        );

        CREATE TABLE IF NOT EXISTS entry_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            paid_to TEXT DEFAULT 'James Wong',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def today():
    return date.today().isoformat()


def day_name(iso_date):
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%A")


def total_lessons_remaining(conn):
    rows = conn.execute(
        "SELECT lessons_purchased - lessons_used AS rem FROM lesson_credits"
    ).fetchall()
    return sum(r["rem"] for r in rows if r["rem"] > 0)


def active_credit_block(conn):
    """Return the oldest block that still has lessons remaining."""
    return conn.execute(
        """SELECT * FROM lesson_credits
           WHERE lessons_used < lessons_purchased
           ORDER BY purchase_date ASC, id ASC
           LIMIT 1"""
    ).fetchone()


def draw_lesson(conn, session_date, member):
    """Draw one lesson from the active credit block. Returns False if no credits."""
    block = active_credit_block(conn)
    if not block:
        return False
    conn.execute(
        "UPDATE lesson_credits SET lessons_used = lessons_used + 1 WHERE id = ?",
        (block["id"],),
    )
    conn.execute(
        "INSERT INTO lesson_usage (session_date, member, credit_block_id) VALUES (?, ?, ?)",
        (session_date, member, block["id"]),
    )
    return True


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log_session(args):
    p = argparse.ArgumentParser(prog="log-session")
    p.add_argument("--date", default=today())
    p.add_argument("--george", action="store_true")
    p.add_argument("--henry", action="store_true")
    p.add_argument("--george-lesson", action="store_true", dest="george_lesson")
    p.add_argument("--henry-lesson", action="store_true", dest="henry_lesson")
    p.add_argument("--notes", default="")
    opts = p.parse_args(args)

    if not opts.george and not opts.henry:
        print("Error: specify at least --george or --henry (or both).")
        sys.exit(1)

    george_fee = 0.0
    henry_fee = 0.0
    if opts.george:
        george_fee = ENTRY_FEE_WITH_LESSON if opts.george_lesson else ENTRY_FEE_NO_LESSON
    if opts.henry:
        henry_fee = ENTRY_FEE_WITH_LESSON if opts.henry_lesson else ENTRY_FEE_NO_LESSON

    total_fee = george_fee + henry_fee

    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO sessions
               (session_date, day_of_week, george_attended, henry_attended,
                george_had_lesson, henry_had_lesson,
                george_entry_fee, henry_entry_fee, total_entry_fee,
                entry_fee_paid, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                opts.date,
                day_name(opts.date),
                1 if opts.george else 0,
                1 if opts.henry else 0,
                1 if opts.george_lesson else 0,
                1 if opts.henry_lesson else 0,
                george_fee,
                henry_fee,
                total_fee,
                opts.notes,
            ),
        )
        session_id = cur.lastrowid

        no_credits = []
        if opts.george_lesson:
            ok = draw_lesson(conn, opts.date, "George")
            if not ok:
                no_credits.append("George")
        if opts.henry_lesson:
            ok = draw_lesson(conn, opts.date, "Henry")
            if not ok:
                no_credits.append("Henry")

        conn.commit()

        # Summary output
        dname = day_name(opts.date)
        print(f"Session logged: {dname} {opts.date}  (id={session_id})")
        print()
        if opts.george:
            lesson_str = "entry + lesson" if opts.george_lesson else "entry, no lesson"
            print(f"  George: {lesson_str} — ${george_fee:.2f}")
        if opts.henry:
            lesson_str = "entry + lesson" if opts.henry_lesson else "entry, no lesson"
            print(f"  Henry:  {lesson_str} — ${henry_fee:.2f}")
        print(f"\n  Total entry fee this session: ${total_fee:.2f} (unpaid)")

        if no_credits:
            print(f"\n  ⚠️  No lesson credits available for: {', '.join(no_credits)}")
            print("     Consider paying James $800 for the next block.")

        rem = total_lessons_remaining(conn)
        print(f"\n  Lesson credits remaining: {rem}")
        if 0 < rem <= LOW_CREDIT_THRESHOLD:
            print(f"  ⚠️  Running low — consider buying the next block soon.")

    finally:
        conn.close()


def cmd_log_lesson_payment(args):
    p = argparse.ArgumentParser(prog="log-lesson-payment")
    p.add_argument("--date", default=today())
    p.add_argument("--amount", type=float, default=800.00)
    p.add_argument("--lessons", type=int, default=10)
    p.add_argument("--paid-to", default="James Wong", dest="paid_to")
    p.add_argument("--notes", default="")
    opts = p.parse_args(args)

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO lesson_credits
               (purchase_date, amount_paid, lessons_purchased, lessons_used, paid_to, notes)
               VALUES (?, ?, ?, 0, ?, ?)""",
            (opts.date, opts.amount, opts.lessons, opts.paid_to, opts.notes),
        )
        conn.commit()

        rem = total_lessons_remaining(conn)
        print(f"Payment of ${opts.amount:.2f} recorded — {opts.lessons} new lesson credits added.")
        print(f"Total lesson credits now available: {rem}")

    finally:
        conn.close()


def cmd_log_entry_payment(args):
    p = argparse.ArgumentParser(prog="log-entry-payment")
    p.add_argument("--date", default=today())
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--paid-to", default="James Wong", dest="paid_to")
    p.add_argument("--notes", default="")
    opts = p.parse_args(args)

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO entry_payments (payment_date, amount, paid_to, notes)
               VALUES (?, ?, ?, ?)""",
            (opts.date, opts.amount, opts.paid_to, opts.notes),
        )

        # Mark unpaid sessions as paid (oldest first) up to the amount paid
        unpaid = conn.execute(
            """SELECT id, total_entry_fee FROM sessions
               WHERE entry_fee_paid = 0 AND total_entry_fee > 0
               ORDER BY session_date ASC, id ASC"""
        ).fetchall()

        remaining = opts.amount
        marked = []
        for row in unpaid:
            if remaining <= 0:
                break
            if row["total_entry_fee"] <= remaining + 0.001:
                conn.execute(
                    "UPDATE sessions SET entry_fee_paid = 1, entry_fee_paid_date = ? WHERE id = ?",
                    (opts.date, row["id"]),
                )
                remaining -= row["total_entry_fee"]
                marked.append(row["id"])

        conn.commit()

        print(f"Entry payment of ${opts.amount:.2f} recorded.")
        if marked:
            print(f"Marked {len(marked)} session(s) as paid (ids: {', '.join(str(i) for i in marked)}).")
        else:
            print("No unpaid sessions were fully covered by this amount.")

        still_outstanding = conn.execute(
            "SELECT COALESCE(SUM(total_entry_fee),0) AS tot FROM sessions WHERE entry_fee_paid = 0"
        ).fetchone()["tot"]
        print(f"Outstanding entry fees remaining: ${still_outstanding:.2f}")

    finally:
        conn.close()


def cmd_balance(args):
    conn = get_db()
    try:
        unpaid = conn.execute(
            """SELECT session_date, day_of_week,
                      george_attended, henry_attended,
                      george_had_lesson, henry_had_lesson,
                      total_entry_fee
               FROM sessions
               WHERE entry_fee_paid = 0 AND total_entry_fee > 0
               ORDER BY session_date ASC"""
        ).fetchall()

        print("Outstanding Entry Fees")
        print("─" * 40)

        if not unpaid:
            print("Nothing outstanding — all paid up!")
        else:
            total = 0.0
            for row in unpaid:
                members = []
                if row["george_attended"]:
                    tag = "lesson" if row["george_had_lesson"] else "no lesson"
                    members.append(f"George ({tag})")
                if row["henry_attended"]:
                    tag = "lesson" if row["henry_had_lesson"] else "no lesson"
                    members.append(f"Henry ({tag})")
                member_str = " + ".join(members)
                dname = row["day_of_week"] or day_name(row["session_date"])
                print(f"  {dname} {row['session_date']}  {member_str}: ${row['total_entry_fee']:.2f}")
                total += row["total_entry_fee"]
            print(f"\n  Total outstanding: ${total:.2f}")

        rem = total_lessons_remaining(conn)
        print(f"\nLesson credits remaining: {rem}")
        if 0 < rem <= LOW_CREDIT_THRESHOLD:
            print(f"⚠️  Running low — consider buying the next block soon.")

    finally:
        conn.close()


def cmd_lessons(args):
    conn = get_db()
    try:
        blocks = conn.execute(
            """SELECT id, purchase_date, amount_paid, lessons_purchased, lessons_used, paid_to
               FROM lesson_credits
               ORDER BY purchase_date ASC, id ASC"""
        ).fetchall()

        print("Lesson Credit Summary")
        print("─" * 40)

        if not blocks:
            print("No lesson credit blocks recorded yet.")
            print("Log a payment with: log-lesson-payment --amount 800")
            return

        total_rem = 0
        for block in blocks:
            used = block["lessons_used"]
            purch = block["lessons_purchased"]
            rem = purch - used
            total_rem += max(rem, 0)
            status = "active" if rem > 0 else "exhausted"
            print(f"\n  Block #{block['id']} — purchased {block['purchase_date']} (${block['amount_paid']:.0f}, paid to {block['paid_to']})")
            print(f"    Lessons purchased: {purch}  |  Used: {used}  |  Remaining: {rem}  [{status}]")

            if rem > 0:
                usage = conn.execute(
                    """SELECT member, COUNT(*) AS cnt
                       FROM lesson_usage WHERE credit_block_id = ?
                       GROUP BY member ORDER BY member""",
                    (block["id"],),
                ).fetchall()
                if usage:
                    breakdown = ", ".join(f"{u['member']}: {u['cnt']}" for u in usage)
                    print(f"    Usage breakdown: {breakdown}")

        print(f"\n  Total lessons remaining across all blocks: {total_rem}")
        if 0 < total_rem <= LOW_CREDIT_THRESHOLD:
            print(f"  ⚠️  Running low — consider paying James for the next block soon.")
        elif total_rem == 0:
            print(f"  ⚠️  No credits left! Pay James $800 to get 10 more lessons.")

    finally:
        conn.close()


def cmd_summary(args):
    conn = get_db()
    try:
        print("Table Tennis Club — Full Summary")
        print("═" * 40)

        # Sessions
        sessions = conn.execute(
            """SELECT session_date, day_of_week,
                      george_attended, henry_attended,
                      george_had_lesson, henry_had_lesson,
                      total_entry_fee, entry_fee_paid
               FROM sessions
               ORDER BY session_date DESC"""
        ).fetchall()

        print(f"\nSessions ({len(sessions)} total)")
        print("─" * 40)
        if not sessions:
            print("  No sessions recorded yet.")
        else:
            for row in sessions:
                members = []
                if row["george_attended"]:
                    tag = "+lesson" if row["george_had_lesson"] else "no lesson"
                    members.append(f"George({tag})")
                if row["henry_attended"]:
                    tag = "+lesson" if row["henry_had_lesson"] else "no lesson"
                    members.append(f"Henry({tag})")
                paid_str = "✓ paid" if row["entry_fee_paid"] else "unpaid"
                dname = row["day_of_week"] or day_name(row["session_date"])
                print(f"  {dname} {row['session_date']}  {' + '.join(members)}  ${row['total_entry_fee']:.2f} [{paid_str}]")

        # Entry fee totals
        totals = conn.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN entry_fee_paid=0 THEN total_entry_fee ELSE 0 END),0) AS outstanding,
                 COALESCE(SUM(CASE WHEN entry_fee_paid=1 THEN total_entry_fee ELSE 0 END),0) AS paid_total
               FROM sessions"""
        ).fetchone()
        print(f"\n  Outstanding entry fees: ${totals['outstanding']:.2f}")
        print(f"  Total entry fees paid:  ${totals['paid_total']:.2f}")

        # Lesson credits
        print(f"\nLesson Credits")
        print("─" * 40)
        blocks = conn.execute(
            """SELECT id, purchase_date, amount_paid, lessons_purchased, lessons_used
               FROM lesson_credits ORDER BY purchase_date ASC, id ASC"""
        ).fetchall()
        if not blocks:
            print("  No lesson credit blocks recorded.")
        else:
            total_rem = 0
            for block in blocks:
                rem = block["lessons_purchased"] - block["lessons_used"]
                total_rem += max(rem, 0)
                status = "active" if rem > 0 else "exhausted"
                print(f"  Block #{block['id']} {block['purchase_date']} — {block['lessons_used']}/{block['lessons_purchased']} used, {rem} remaining [{status}]")
            print(f"\n  Total remaining: {total_rem}")
            if 0 < total_rem <= LOW_CREDIT_THRESHOLD:
                print(f"  ⚠️  Running low — buy next block soon.")
            elif total_rem == 0:
                print(f"  ⚠️  No credits left!")

        # Entry payments
        payments = conn.execute(
            "SELECT payment_date, amount, notes FROM entry_payments ORDER BY payment_date DESC"
        ).fetchall()
        print(f"\nEntry Fee Payments ({len(payments)} recorded)")
        print("─" * 40)
        if not payments:
            print("  No entry payments recorded yet.")
        else:
            for p in payments:
                note_str = f" — {p['notes']}" if p["notes"] else ""
                print(f"  {p['payment_date']}  ${p['amount']:.2f}{note_str}")

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS = {
    "log-session": cmd_log_session,
    "log-lesson-payment": cmd_log_lesson_payment,
    "log-entry-payment": cmd_log_entry_payment,
    "balance": cmd_balance,
    "lessons": cmd_lessons,
    "summary": cmd_summary,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Table Tennis Club Tracker")
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        print()
        print("Examples:")
        print("  tabletennis.py log-session --george --henry --george-lesson --henry-lesson")
        print("  tabletennis.py log-session --date 2025-04-05 --george --henry")
        print("  tabletennis.py log-lesson-payment --amount 800")
        print("  tabletennis.py log-entry-payment --amount 22.00")
        print("  tabletennis.py balance")
        print("  tabletennis.py lessons")
        print("  tabletennis.py summary")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
