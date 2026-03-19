---
name: brave-search
description: >
  Web search using the Brave Search LLM Context API. Use when the user asks to search the web,
  look something up, find current information, or asks about recent events. Returns clean,
  structured results optimised for LLM consumption.
---

# Brave Search

Uses the Brave Search LLM Context API. Requires `BRAVE_API_KEY` in the environment.

## Usage

```bash
curl -s "https://api.search.brave.com/res/v1/web/search?q=YOUR+QUERY&count=5&result_filter=web" \
  -H "Accept: application/json" \
  -H "Accept-Encoding: gzip" \
  -H "X-Subscription-Token: $BRAVE_API_KEY"
```

Or via WebFetch with the Authorization header — but Bash + curl is preferred for reliability.

## Parameters

- `q` — search query (URL-encoded)
- `count` — number of results (1–20, default 10; use 5 for quick lookups)
- `result_filter` — `web`, `news`, `videos` (default: `web`)
- `freshness` — `pd` (past day), `pw` (past week), `pm` (past month)
- `search_lang` — e.g. `en`
- `country` — e.g. `AU`, `US`

## Response

Returns JSON. Extract results from `web.results[]`:

```
title       — page title
url         — canonical URL
description — snippet
age         — publication date (if available)
```

## Rules

- Always set `count=5` unless the user asks for more results.
- Present results as a clean bulleted list: title + URL + one-line summary.
- If `BRAVE_API_KEY` is not set, tell the user to add it to `.env`.
- For news/current events, add `&freshness=pw` to bias toward recent results.
- Never fabricate results — always run the curl command.
