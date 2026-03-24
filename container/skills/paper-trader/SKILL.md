---
name: paper-trader
description: >
  Paper trading portfolio monitor. Use when the user asks about their trading
  balance, open positions, P&L, fees, or the state of their mean reversion
  paper trading strategy. Also use for questions like "how's my trading going",
  "am I in any trades", "what's my account balance", or "is trading halted".
  Always read live data from disk — never guess or make up values.
metadata:
  {
    "nanoclaw":
      {
        "emoji": "📈",
        "requires": { "bins": ["python3"] },
      },
  }
---

# 📈 Paper Trader

Reads live state from the mean reversion paper trading engine running on the
host machine. Data is mounted read-only at `/workspace/extra/paper-trader/`
and written every ~60 seconds by the engine.

Script location: `/home/node/.claude/skills/paper-trader/scripts/portfolio_cli.py`

**Always run the script — never fabricate trading data.**

## Portfolio status (balance + open positions)

```bash
python3 /home/node/.claude/skills/paper-trader/scripts/portfolio_cli.py status
```

## Balance only

```bash
python3 /home/node/.claude/skills/paper-trader/scripts/portfolio_cli.py balance
```

## Open positions only

```bash
python3 /home/node/.claude/skills/paper-trader/scripts/portfolio_cli.py positions
```

## Output format

All commands output JSON. Present the data to the user in a clean, readable
format. For balance, show AUD values with 2 decimal places and +/- signs on
P&L figures. For positions, show strategy name (underscores as slashes),
direction, entry date, size, and bars open. If `trading_halted` is true,
highlight this prominently.

## Error handling

If the script exits with a non-zero code or prints to stderr, tell the user
the engine may not be running or no data has been written yet.
