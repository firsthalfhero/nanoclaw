---
name: usage
description: Show Claude token usage statistics — daily totals for input, output, and cache tokens. Use when the user asks about token usage, API costs, how many tokens have been used, or runs /usage.
---

# /usage — Token Usage Report

Query token usage from the NanoClaw database.

**Main-channel check:**

```bash
test -d /workspace/project && echo "MAIN" || echo "NOT_MAIN"
```

If `NOT_MAIN`: respond "This command is available in your main chat only."

## Query usage

```bash
node --input-type=module << 'JSEOF'
import Database from 'better-sqlite3';
const db = new Database('/workspace/project/store/messages.db');
const rows = db.prepare(`
  SELECT * FROM token_usage
  WHERE date >= date('now', '-30 days')
  ORDER BY date DESC
`).all();
console.log(JSON.stringify(rows));
db.close();
JSEOF
```

## Format the report

Present the data as a clean summary:

```
📊 Token Usage (last 30 days)

Date         Input      Output     Cache Read   Requests
2026-03-19   12,450     3,210      8,100        42
2026-03-18   9,800      2,640      5,200        35
...

Total:       22,250     5,850      13,300       77
```

- Show the most recent 7 days in full, then a monthly total line
- If cache_creation_tokens > 0, add a "Cache Written" column
- If the table is empty, say "No usage recorded yet — token tracking starts from the next conversation"
