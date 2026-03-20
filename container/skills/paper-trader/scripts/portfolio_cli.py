#!/usr/bin/env python3
"""
portfolio_cli.py — Read paper trading state from disk.

Reads: /workspace/extra/paper-trader/paper_state.json
(Mounted read-only from the host by NanoClaw's additionalMounts config.)

No API calls. No network. Direct file read.
"""

import json
import sys
import argparse
from pathlib import Path

STATE_FILE = Path("/workspace/extra/paper-trader/paper_state.json")


def load_state() -> dict:
    if not STATE_FILE.exists():
        print(json.dumps({
            "error": "State file not found. Engine may not have started yet.",
            "path": str(STATE_FILE)
        }))
        sys.exit(1)

    text = STATE_FILE.read_text(encoding="utf-8").strip()
    if not text:
        print(json.dumps({"error": "State file is empty. Engine may still be initialising."}))
        sys.exit(1)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"State file is malformed (mid-write?): {e}. Retry in a moment."}))
        sys.exit(1)


def cmd_balance(state: dict) -> None:
    print(json.dumps({
        "account_balance_aud": state.get("account_balance_aud"),
        "total_pnl_aud":       state.get("total_pnl_aud"),
        "daily_pnl_aud":       state.get("daily_pnl_aud"),
        "total_fees_aud":      state.get("total_fees_aud"),
        "trade_count":         state.get("trade_count"),
        "trading_halted":      state.get("trading_halted", False),
    }, indent=2))


def cmd_positions(state: dict) -> None:
    positions = state.get("positions", {})
    open_positions = {
        sid.replace("_", "/"): pos
        for sid, pos in positions.items()
        if pos is not None and pos.get("open", True)
    }
    print(json.dumps({
        "open_count": len(open_positions),
        "positions":  open_positions,
    }, indent=2))


def cmd_status(state: dict) -> None:
    positions = state.get("positions", {})
    open_positions = {
        sid.replace("_", "/"): pos
        for sid, pos in positions.items()
        if pos is not None and pos.get("open", True)
    }
    print(json.dumps({
        "account_balance_aud":   state.get("account_balance_aud"),
        "total_pnl_aud":         state.get("total_pnl_aud"),
        "daily_pnl_aud":         state.get("daily_pnl_aud"),
        "total_fees_aud":        state.get("total_fees_aud"),
        "trade_count":           state.get("trade_count"),
        "trading_halted":        state.get("trading_halted", False),
        "open_positions_count":  len(open_positions),
        "open_positions":        open_positions,
    }, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper trader portfolio reader")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status",    help="Balance + open positions")
    subparsers.add_parser("balance",   help="Account balance and P&L only")
    subparsers.add_parser("positions", help="Open positions only")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help(sys.stderr)
        return 1

    state = load_state()

    if args.command == "status":
        cmd_status(state)
    elif args.command == "balance":
        cmd_balance(state)
    elif args.command == "positions":
        cmd_positions(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
