# NanoClaw Stability — Diagnosis & Fixes

_Last updated: 2026-04-12_

## Background

NanoClaw is intermittently unstable. Crashes and "no response" events correlate with Claude hitting its daily usage cap. This document records the root causes found, the fixes applied, and the ongoing monitoring approach.

---

## Root Causes (ranked by severity)

### 1. Token-limit feedback loop — **FIXED**

**File:** `src/index.ts` — streaming callback  
**Symptom:** After Claude hits the usage cap, the container emits 4–8 identical "You've hit your limit" results before eventually throwing an error and exiting with code 1. Users who sent messages during this window get no response and those messages are silently dropped.

**What was happening:**

1. A container session is active and piping incoming messages via IPC.
2. Claude hits the cap → SDK returns `"You've hit your limit · resets 3pm"`.
3. The host detects this (`usageLimitHit = true`) but **does not signal the container to stop**.
4. The host's `startMessageLoop` keeps writing new IPC files for any incoming messages.
5. The container picks them up and sends them to Claude → more "hit your limit" responses, looping until the SDK throws.
6. The host's `usageLimitHit` fallback eventually fires, but the 4–8 IPC-piped messages during the failure window have already had their cursors advanced with no response sent.

**Fix:** Add `queue.closeStdin(chatJid)` immediately when a usage-limit match is detected in the streaming callback. This writes the `_close` sentinel to the container's IPC directory, stopping the agent-runner's poll loop within 500ms.

---

### 2. Overly broad `USAGE_LIMIT_PATTERNS` — **FIXED**

**File:** `src/index.ts`  
**Symptom:** Any Claude response mentioning "limit" (rate limits, skill limitations, "limited ability to…") triggered `usageLimitHit = true`, silently dropping the response and attempting an unnecessary failover.

**Fix:** Removed `/limit/i` and `/resets/i` from the pattern list. The specific patterns (`/you've hit your limit/i`, `/hit your limit/i`, `/usage.*resets/i`, etc.) already correctly catch the real Claude cap message. The broad patterns were latent false-positive traps.

---

### 3. No global error handlers — **FIXED**

**File:** `src/index.ts`  
**Symptom:** Node.js 15+ exits the process on unhandled promise rejections. Any async error escaping the explicit `catch` blocks (IPC race, Telegram network blip, etc.) silently kills NanoClaw with an empty stderr log — making post-mortem diagnosis impossible.

**Fix:** Added `process.on('uncaughtException')` and `process.on('unhandledRejection')` handlers before `main()`. These log the crash reason at `fatal` level before exiting, ensuring the cause appears in `logs/nanoclaw-out.log`.

---

### 4. Watchdog port-binding race — **FIXED**

**File:** `start.ps1`  
**Symptom:** The watchdog killed the process on port 3001 then waited only 1 second before starting a new instance. On Windows, TCP sockets stay in `TIME_WAIT` for 30–120s after a process is killed. If `server.listen(3001)` failed with `EADDRINUSE`, `main()` caught it and called `process.exit(1)` immediately — causing a rapid crash loop (10+ restarts in ~90 seconds).

**Fix:** Replaced the fixed 1-second sleep with a polling loop that checks port 3001 every second for up to 15 seconds, only proceeding once the port is confirmed free.

---

### 5. Service account key exposed in container error logs — **FIXED**

**File:** `src/container-runner.ts`  
**Symptom:** When a container exits with non-zero code, the full Docker run arguments (including `FIREBASE_SERVICE_ACCOUNT` JSON with a private key) are written to the group's `logs/container-*.log` file in plaintext.

**Fix:** Container args are redacted before writing to the log — any `-e KEY=VALUE` argument where the key ends with `_KEY`, `_SECRET`, `_TOKEN`, `_ACCOUNT`, `_CREDENTIAL`, or `_PASSWORD` has its value replaced with `[redacted]`.

---

### 6. API auth errors forwarded raw to users — **FIXED**

**File:** `src/index.ts`  
**Symptom:** When the Claude API returns a 401 (e.g. bad token) or 500, the raw SDK error JSON was forwarded directly to the user's chat: `"Failed to authenticate. API Error: 401 {\"type\":\"error\",...}"`.

**What was happening:** The Claude Agent SDK returns auth errors as result text with `status: 'success'` rather than throwing, so existing `try/catch` blocks didn't intercept them. The response passed through to the user unchanged.

**Fix:** Added `API_ERROR_PATTERNS` to detect 401/403/5xx and overloaded errors in the streaming callback. On match, `apiErrorHit` is set, the container's IPC stdin is closed, and a structured failover is attempted. Users see: `"The Claude API has failed with: {clean_message}\n\nFailed over to {model} and the response is below."` If all fallbacks fail, they get a clear message rather than raw JSON.

---

## Monitoring

### Log patterns to watch

```bash
# Tail the main log (Windows — run in PowerShell)
Get-Content logs\nanoclaw-out.log -Wait

# Key signals
"Claude usage limit hit"          -> cap hit, fallback should follow
"Max retries exceeded"            -> container failing 5+ times in a row
"Container timed out with no output" -> container hung
"Unhandled promise rejection"     -> process about to crash (after Fix 3)
"Uncaught exception"              -> process about to crash (after Fix 3)
"Fatal"                           -> process exiting
```

### Daily token usage

Token usage is stored in SQLite (`store/messages.db`, table `token_usage`). Query it to understand daily patterns:

```sql
SELECT date, 
       input_tokens + output_tokens as total_tokens,
       cache_read_tokens,
       request_count
FROM token_usage
ORDER BY date DESC
LIMIT 7;
```

Ask Pip: _"show me token usage for the last week"_ — the agent can run this query directly.

### Container logs

Each container run writes a log to `groups/{name}/logs/container-{timestamp}.log`. On error runs, this includes the full stdin, mount list, stderr, and stdout. These are the primary diagnostic tool for agent-level failures.

---

## Architecture notes

- The host (Node.js, port 3001) is persistent. The credential proxy runs here.
- Containers are ephemeral — one per conversation turn, `docker run --rm`.
- IPC between host and container is file-based: `data/ipc/{group}/input/`.
- When a container is in an active IPC session, the host can pipe follow-up messages without spawning a new container.
- The `_close` sentinel (`data/ipc/{group}/input/_close`) signals the container agent-runner to wind down.
- The watchdog (`start.ps1`) restarts the Node.js host on any exit. Containers are not affected by host restarts — they continue running and are cleaned up as orphans on the next startup.

---

## Remaining known issues

- **Messages during token-limit IPC window**: Messages piped into a container that subsequently hits the token limit have their cursors advanced. After Fix 1, the feedback loop is stopped quickly, but the 1–2 messages already in-flight at the moment of detection may still be lost. A more complete fix would require cursor rollback for IPC-piped messages, which is architecturally complex.
- **No proactive token-limit notification**: There is no mechanism to warn when approaching the daily cap. This would require polling the Anthropic API or tracking usage trends from the `token_usage` table.
