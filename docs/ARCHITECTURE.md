# NanoClaw Architecture

A developer's guide to how NanoClaw works — from a user message arriving on WhatsApp to a Claude agent running in an isolated container and a reply appearing in the chat.

For design philosophy and requirements, see [REQUIREMENTS.md](REQUIREMENTS.md). For the security model in depth, see [SECURITY.md](SECURITY.md). For the Claude Agent SDK integration, see [SDK_DEEP_DIVE.md](SDK_DEEP_DIVE.md).

---

## System Overview

NanoClaw is a single Node.js process (the **host**) that:

1. Receives messages from one or more messaging channels (WhatsApp, Telegram, Discord, Slack)
2. Stores every message in SQLite
3. Polls for new messages and spawns an ephemeral Docker container per invocation
4. Runs the Claude Agent SDK (via Claude Code CLI) inside the container against the conversation history
5. Routes the agent's reply back to the channel

The host process owns all secrets and privileged operations. Containers run untrusted user input in isolation and communicate back only through a narrow IPC surface.

```
┌───────────────────────────────────────────────────────────────────┐
│                        HOST  (Node.js)                            │
│                                                                   │
│  ┌──────────────┐  onMessage  ┌──────────┐  poll  ┌──────────┐  │
│  │   Channels   │────────────▶│  SQLite  │◀───────│  Message │  │
│  │  (Discord,   │             │  (db.ts) │        │   Loop   │  │
│  │   Telegram…) │             └──────────┘        │(index.ts)│  │
│  └──────────────┘                                 └────┬─────┘  │
│                                                        │         │
│  ┌──────────────┐             ┌──────────┐        ┌────▼─────┐  │
│  │  Credential  │             │   IPC    │        │  Group   │  │
│  │   Proxy      │             │  Watcher │        │  Queue   │  │
│  │ (port 3001)  │             │ (ipc.ts) │        │          │  │
│  └──────┬───────┘             └────▲─────┘        └────┬─────┘  │
│         │                          │ files              │         │
└─────────┼──────────────────────────┼────────────────────┼────────┘
          │ API calls                │                    │ spawn
          │ (injected auth)          │                    ▼
┌─────────┼──────────────────────────┼────────────────────────────┐
│         │       CONTAINER  (Linux VM)                           │
│         │                          │                            │
│  ┌──────▼───────────────────────────────────────────────────┐   │
│  │  Agent Runner (agent-runner/src/index.ts)                 │   │
│  │                                                           │   │
│  │  • Reads prompt from stdin                                │   │
│  │  • Calls query() with Claude Agent SDK                    │   │
│  │  • Polls /workspace/ipc/input/ for follow-up messages     │   │
│  │  • Emits output wrapped in sentinel markers               │   │
│  │  • Exposes nanoclaw MCP server (schedule, send_message)   │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  Volume mounts:                                                   │
│    /workspace/group        ← groups/{name}/          (rw)         │
│    /workspace/global       ← groups/global/          (ro*)        │
│    /workspace/ipc          ← data/ipc/{group}/       (rw)         │
│    /home/node/.claude      ← data/sessions/{group}/  (rw)         │
│    /home/node/.claude/skills ← container/skills/    (ro)         │
└───────────────────────────────────────────────────────────────────┘

* main group gets rw access to /workspace/global
```

---

## Host Components

### `src/index.ts` — Orchestrator

The entry point and central coordinator. Responsibilities:

- Initialises the database, loads persisted state (registered groups, sessions, message cursors)
- Connects all registered channels
- Starts the scheduler, IPC watcher, and message loop
- Implements `processGroupMessages()` — the core pipeline from raw messages to container invocation
- Falls back to OpenAI/Gemini if the Claude API call fails

Key state held in memory:

| Variable | Purpose |
|---|---|
| `lastTimestamp` | Global message cursor; prevents reprocessing on restart |
| `lastAgentTimestamp` | Per-group cursor; resumes work after a crash mid-invocation |
| `sessions` | Group folder → Claude Code session ID (enables session resumption) |
| `registeredGroups` | JID → group config map, loaded from DB at startup |
| `queue` | `GroupQueue` instance — controls concurrent container count |

### `src/container-runner.ts` — Container Spawning

Translates an agent invocation request into a `docker run` command.

- `buildVolumeMounts(group, isMain)` — constructs the set of `-v` flags; validates additional mounts against the security allowlist
- `buildContainerArgs(mounts, containerName)` — assembles the full command, injects env vars, sets resource limits
- `runContainerAgent(group, input, onProcess, onOutput)` — spawns the container, streams stdout through sentinel-marker parsing, manages timeouts (CONTAINER_TIMEOUT, IDLE_TIMEOUT), and writes logs on exit

Containers are always started with `--rm` (ephemeral). The host kills any orphaned containers from a previous crashed session at startup.

### `src/task-scheduler.ts` — Scheduler

Checks SQLite for due tasks every `SCHEDULER_POLL_INTERVAL` (60 s). For each due task it spawns a container with `isScheduledTask: true` and the task's stored prompt. After the run it computes the next execution time and updates the DB.

Schedule types: `cron` (standard cron expression), `interval` (milliseconds), `once` (ISO timestamp, auto-cancelled after firing).

### `src/ipc.ts` — IPC Watcher

Provides a file-based channel for containers to request privileged operations on the host. Polls `data/ipc/{group}/messages/` and `data/ipc/{group}/tasks/` every second.

**Authorization model:**

| Requester | Allowed operations |
|---|---|
| Main group | Any group's tasks, global memory, group registration |
| Non-main group | Own tasks and messages only |

IPC task types: `schedule_task`, `pause_task`, `resume_task`, `cancel_task`, `update_task`, `register_group`, `refresh_groups`.

### `src/db.ts` — Database

SQLite via `better-sqlite3`. All tables are created on first run; missing columns are auto-migrated.

| Table | Stores |
|---|---|
| `messages` | Every inbound/outbound message with timestamp and `is_bot_message` flag |
| `chats` | Chat metadata (JID, name, channel, last activity) |
| `registered_groups` | Group config: folder, trigger, timeout, additional mounts |
| `scheduled_tasks` + `task_run_logs` | Task records and execution history |
| `sessions` | Group folder → Claude Code session ID |
| `router_state` | Persisted `lastTimestamp` and `lastAgentTimestamp` for crash recovery |
| `token_usage` | Daily API token accounting (input, output, cache hits/misses) |

### `src/router.ts` — Message Formatting

- `formatMessages(messages, timezone)` — converts DB rows into the XML conversation format the agent prompt uses
- `formatOutbound(rawText)` — strips `<internal>…</internal>` blocks from agent output before sending to users
- `routeOutbound(channels, jid, text)` — finds the owning channel for a JID and calls `sendMessage()`

### `src/credential-proxy.ts` — Credential Proxy

An HTTP proxy that runs on the host (default port 3001). Containers are configured to send all Anthropic API calls through it. The proxy intercepts each request and injects the real `Authorization` header before forwarding, so API keys never appear inside a container's environment or filesystem.

### `src/mount-security.ts` — Mount Validation

Before any additional volume mounts (configured per group) are passed to Docker, this module:

1. Resolves symlinks to prevent traversal attacks
2. Checks the resolved path against `~/.config/nanoclaw/mount-allowlist.json` (stored outside the project root)
3. Blocks patterns matching `.ssh`, `.aws`, `.gnupg`, `credentials`, `.env`, `id_rsa`, etc.

### `src/channels/` — Channel System

Channels follow a self-registration factory pattern:

```typescript
// At module load time:
registerChannel('telegram', (opts) => new TelegramChannel(opts));

// interface Channel
connect(): Promise<void>
sendMessage(jid: string, text: string): Promise<void>
isConnected(): boolean
ownsJid(jid: string): boolean
disconnect(): Promise<void>
```

`src/channels/index.ts` barrel-imports every channel module, triggering registration. `src/index.ts` iterates registered factories, instantiates each one, and calls `connect()`. If credentials are absent the factory returns `null` and the channel is skipped.

Built-in channels: **Discord** (`discord.ts`), **Telegram** (`telegram.ts`). Additional channels (WhatsApp, Slack, Gmail) are installed via Claude Code skills that inject new channel files and add the import to `index.ts`.

JID formats:

| Channel | Format |
|---|---|
| Discord channel | `dc:CHANNEL_ID` |
| Discord DM | `dc:dm:USER_ID` |
| Discord thread | `dc:thread:THREAD_ID` |
| Telegram | `tg:CHAT_ID` |
| WhatsApp | `PHONE@s.whatsapp.net` / `GROUP_ID@g.us` |

---

## Configuration Management

NanoClaw separates configuration into three tiers: global constants, secrets, and per-group overrides.

### Tier 1 — Global Constants (`src/config.ts`)

All non-secret, process-wide configuration is defined here and read from environment variables at startup. Secrets are never read here.

| Constant | Default | Source | Purpose |
|---|---|---|---|
| `ASSISTANT_NAME` | `Andy` | `.env` / env | Trigger prefix (`@Andy`) and bot identity |
| `TRIGGER_PATTERN` | `/^@Andy\b/i` | derived | Regex for non-main group activation |
| `POLL_INTERVAL` | 2 000 ms | hardcoded | Message poll rate |
| `SCHEDULER_POLL_INTERVAL` | 60 000 ms | hardcoded | Task check rate |
| `IPC_POLL_INTERVAL` | 1 000 ms | hardcoded | IPC watcher rate |
| `CONTAINER_IMAGE` | `nanoclaw-agent:latest` | env | Docker image tag |
| `CONTAINER_TIMEOUT` | 1 800 000 ms | env | Hard container kill deadline |
| `IDLE_TIMEOUT` | 1 800 000 ms | hardcoded | Kill after this long with no output |
| `MAX_CONCURRENT_CONTAINERS` | 5 | env | Global container concurrency cap |
| `CREDENTIAL_PROXY_PORT` | 3001 | hardcoded | Credential proxy listen port |
| `TIMEZONE` | system TZ | env `TZ` | Cron expressions and message timestamps |
| `STORE_DIR` | `{cwd}/store` | derived | SQLite database location |
| `GROUPS_DIR` | `{cwd}/groups` | derived | Per-group workspace folders |
| `DATA_DIR` | `{cwd}/data` | derived | Sessions, IPC, logs |
| `MOUNT_ALLOWLIST_PATH` | `~/.config/nanoclaw/mount-allowlist.json` | derived | External security allowlist |
| `SENDER_ALLOWLIST_PATH` | `~/.config/nanoclaw/sender-allowlist.json` | derived | Allowed sender JIDs |

### Tier 2 — Secrets (`.env` + `src/env.ts`)

`src/env.ts` provides `readEnvFile(keys)` which reads `.env` from the project root and returns a plain object. It **never writes into `process.env`**, preventing secrets from leaking to child processes.

Secrets are read explicitly by the components that need them:

| Component | What it reads |
|---|---|
| `src/credential-proxy.ts` | `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`; `OPENROUTER_API_KEY` |
| `src/container-runner.ts` | Skill API keys (see allowlist below) |
| `src/channels/*.ts` | Channel tokens (`TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, etc.) |
| `src/gemini-fallback.ts` | `GOOGLE_GEMINI_API_KEY` |
| `src/openai-fallback.ts` | `OPENAI_API_KEY` |

**Skill env var allowlist** — `buildContainerArgs()` in `container-runner.ts` explicitly gates which variables enter the container via `-e` flags:

```
MOTION_API_KEY            MOTION_WORKSPACE_ID
GOOGLE_CAL_CLIENT_ID      GOOGLE_CAL_CLIENT_SECRET
GOOGLE_GMAIL_CLIENT_ID    GOOGLE_GMAIL_CLIENT_SECRET
BRAVE_API_KEY             FIREBASE_SERVICE_ACCOUNT
OPENAI_API_KEY            GOOGLE_GEMINI_API_KEY
NUTRI_API_URL             OPENROUTER_API_KEY
OPENROUTER_VISION_MODEL   OPENROUTER_TEXT_MODEL
```

To add a new skill's env var, append it to this allowlist in `buildContainerArgs()`.

### Tier 3 — Per-Group Config (SQLite `registered_groups`)

Each registered group can override container behaviour via the `container_config` column (stored as JSON):

```typescript
interface ContainerConfig {
  timeout?: number;            // Override CONTAINER_TIMEOUT for this group (ms)
  additionalMounts?: AdditionalMount[];
}

interface AdditionalMount {
  hostPath: string;
  containerPath: string;
  allowReadWrite: boolean;
  description?: string;
}
```

Additional mounts must pass through `src/mount-security.ts` before being passed to Docker. The main group manages this config via IPC commands.

### Container Settings Injection

Before spawning each container, `container-runner.ts` writes two files into the session directory (`data/sessions/{group}/.claude/`):

**`settings.json`** — enables experimental features:
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "0"
  }
}
```

**Skills sync** — every file under `container/skills/` is copied into `data/sessions/{group}/.claude/skills/` so the Claude Code CLI inside the container picks them up automatically. Editing a skill file takes effect on the next container invocation with no rebuild needed.

---

## Container Build & Launch

### Image Build (`container/Dockerfile`)

Base image: `node:22-slim` (Debian slim + Node.js 22, non-root `node` user).

System packages installed:

| Category | Packages |
|---|---|
| Browser automation | `chromium`, libgbm1, libnss3, libatk-bridge2.0-0, libgtk-3-0, and associated X11/audio libs |
| Fonts | `fonts-liberation`, `fonts-noto-cjk`, `fonts-noto-color-emoji` |
| Dev tools | `curl`, `git`, `python3`, `python3-pip`, `ffmpeg`, `pandoc`, `wkhtmltopdf` |

Global npm packages installed into the image:

- `agent-browser` — Headless Chromium CLI tool (from Anthropic)
- `@anthropic-ai/claude-code` — The Claude Code CLI (this is what runs the agent)

Chromium environment variables set at build time so both `agent-browser` and Playwright find the system binary without a separate download:

```
AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
```

The `agent-runner` source is copied in and compiled during the build (`npm install && npm run build`). Workspace directories are pre-created at build time:

```
/workspace/group    /workspace/global    /workspace/extra
/workspace/ipc/messages  /workspace/ipc/tasks  /workspace/ipc/input
```

Rebuild the image with `./container/build.sh` (from a Linux/Git Bash shell). Takes ~2 min. Only needed when the Dockerfile or agent-runner TypeScript changes; skill file edits do not require a rebuild.

### Container Entrypoint

The entrypoint script compiles the agent-runner from source at startup (so the host can hot-patch it via the mounted `/app/src`), then pipes stdin JSON into the compiled binary:

```bash
#!/bin/bash
set -e
cd /app && npx tsc --outDir /tmp/dist 2>&1 >&2
ln -s /app/node_modules /tmp/dist/node_modules
chmod -R a-w /tmp/dist
cat > /tmp/input.json
node /tmp/dist/index.js < /tmp/input.json
```

### `docker run` Command Structure

`buildContainerArgs()` assembles the command. The structure is:

```
docker run -i --rm --name nanoclaw-{safeName}-{timestamp}
  -e TZ={TIMEZONE}
  -e ANTHROPIC_BASE_URL=http://host.docker.internal:3001
  -e ANTHROPIC_API_KEY=placeholder          # or CLAUDE_CODE_OAUTH_TOKEN=placeholder
  [-e OPENROUTER_MODEL=... -e ANTHROPIC_MODEL=...]   # OpenRouter mode only
  [-e MOTION_API_KEY=... -e BRAVE_API_KEY=... ...]   # skill vars from allowlist
  [--add-host=host.docker.internal:host-gateway]     # Linux only
  [--user {hostUid}:{hostGid} -e HOME=/home/node]    # if host uid ≠ 0 or 1000
  -v {groups/folder}:/workspace/group
  -v {groups/global}:/workspace/global:ro            # non-main; rw for main
  [-v {cwd}:/workspace/project:ro]                   # main group only
  [-v /dev/null:/workspace/project/.env:ro]          # hides .env from main
  -v {data/sessions/folder/.claude}:/home/node/.claude
  -v {data/sessions/folder/ipc}:/workspace/ipc
  -v {data/sessions/folder/agent-runner-src}:/app/src
  [-v {hostPath}:{containerPath}[:ro]]               # validated additionalMounts
  nanoclaw-agent:latest
```

**Host gateway routing:**

| Platform | Resolution |
|---|---|
| macOS / Docker Desktop | `127.0.0.1` — Docker Desktop routes `host.docker.internal` automatically |
| Linux | Binds to `docker0` bridge IP; adds `--add-host=host.docker.internal:host-gateway` |

**Input/output protocol:**

Input is a JSON blob piped to stdin:
```typescript
interface ContainerInput {
  prompt: string;
  sessionId?: string;      // omitted on first run; supplied for session resumption
  groupFolder: string;
  chatJid: string;
  isMain: boolean;
  isScheduledTask?: boolean;
  assistantName?: string;
}
```

Output is zero or more JSON blobs wrapped in sentinel markers on stdout:
```
---NANOCLAW_OUTPUT_START---
{"status": "success"|"error", "result": "...", "newSessionId": "...", "error": "..."}
---NANOCLAW_OUTPUT_END---
```

**Timeout handling:**

The effective timeout is `max(containerConfig.timeout, IDLE_TIMEOUT + 30s)`. When it fires:
1. `docker stop {name}` with a 15 s grace period
2. If that fails: `SIGKILL` via `container.kill('SIGKILL')`
3. If the container had produced output before timing out: resolves as `success`; otherwise `error`

**Logging:** On exit, stdout and stderr (each capped at 10 MB) are written to `groups/{folder}/logs/container-{timestamp}.log`. Full verbose logging is enabled when `LOG_LEVEL=debug`.

---

## Claude Code CLI Inside the Container

The agent is not a custom LLM integration — it runs the **Claude Code CLI** (`@anthropic-ai/claude-code`, installed globally in the image) via the **Claude Agent SDK** (`@anthropic-ai/claude-agent-sdk`).

The agent-runner calls `query()` from the SDK with `permissionMode: 'bypassPermissions'` — the container's filesystem isolation replaces the normal permission prompts. Inside the container the agent has full access to:

- **File tools:** `Read`, `Write`, `Edit`, `Glob`, `Grep` (scoped to mounted paths)
- **Shell:** `Bash` (runs inside the container; cannot reach the host)
- **Web:** `WebSearch`, `WebFetch`
- **Orchestration:** `Task`, `TeamCreate`, `SendMessage` (agent-teams support)
- **MCP tools:** `mcp__nanoclaw__*` (send messages, schedule tasks)
- **Skills:** Claude Code slash commands from `/home/node/.claude/skills/`

Session IDs from Claude Code are persisted to SQLite after each run. Supplying the same session ID on the next invocation resumes the conversation with full context — the agent remembers tool calls, prior turns, and any files it modified.

The Claude Code CLI is also what drives the **skill system**: each `container/skills/*/SKILL.md` is a Claude Code skill prompt. When the agent calls `/motion` or `/google-calendar`, Claude Code reads the skill's YAML frontmatter, spawns a subagent with the skill model, and executes the skill's instructions.

---

## Container Components

### `container/agent-runner/src/index.ts` — Agent Runner

The executable that runs inside every container. It:

1. Reads a `ContainerInput` JSON blob from stdin
2. Constructs a `MessageStream` — a push-based async iterable used as the prompt — so the SDK never closes stdin mid-conversation
3. Calls `query()` from the Claude Agent SDK in a loop
4. Polls `/workspace/ipc/input/` for follow-up messages piped in by the host while the agent is running
5. Emits `ContainerOutput` JSON wrapped in sentinel markers on stdout
6. Continues the loop until a close sentinel arrives or the container times out

**SDK call configuration:**

```typescript
query({
  prompt: messageStream,             // async iterable, not a string
  cwd: '/workspace/group',
  resume: sessionId,                 // omitted in OpenRouter mode
  systemPrompt: globalClaudeMd,      // /workspace/global/CLAUDE.md (non-main groups)
  allowedTools: ['Bash', 'Read', 'Write', 'Edit', 'Glob', 'Grep',
                 'WebSearch', 'WebFetch', 'Task', 'mcp__nanoclaw__*'],
  permissionMode: 'bypassPermissions',
  settingSources: ['project', 'user'],
  mcpServers: { nanoclaw: { command: 'node', args: ['ipc-mcp-stdio.js'] } }
})
```

### `container/agent-runner/src/ipc-mcp-stdio.ts` — MCP Server

A stdio-based MCP server exposed to the agent as `mcp__nanoclaw__*` tools. It writes JSON files to the IPC directories; the host IPC watcher processes them asynchronously.

| Tool | What it does |
|---|---|
| `send_message(text)` | Sends a message to the group immediately (progress update) |
| `schedule_task(prompt, schedule_type, schedule_value)` | Creates a recurring or one-time task |
| `list_tasks()` | Lists tasks (own group, or all groups if main) |
| `pause_task(id)` / `resume_task(id)` / `cancel_task(id)` | Manage task lifecycle |

### `container/skills/` — Agent Skills

Skills are Markdown files (with YAML frontmatter) synced from `container/skills/` into `/home/node/.claude/skills/` on every container start. They become available as Claude Code slash commands inside the container. A skill may include Python scripts alongside its `SKILL.md`; scripts import from `sys.path` or use stdlib only (no pip unless added to the Dockerfile).

```yaml
---
name: motion
description: Manage tasks and projects via Motion API
trigger: "motion"
model: claude-opus-4-7
---
```

All 18 installed skills:

| Skill | Purpose | Env vars / deps |
|---|---|---|
| `adhd-coach` | ADHD coaching: Pomodoro sessions, morning briefings, check-ins, brain dumps. Schedules cron jobs for daily structure. | — |
| `agent-browser` | Headless Chromium automation via semantic element refs (`@e1`). Navigate, click, fill, screenshot, PDF, cookie/localStorage management. | Chromium (bundled) |
| `brave-search` | Web search via Brave Search LLM Context API. Supports freshness and type filters. | `BRAVE_API_KEY` |
| `capabilities` | Read-only report of installed skills, available tools, MCP tools, and group mounts. Main-channel only. | — |
| `gmail` | Read inbox, filter by label, mark read, archive, apply labels. OAuth2 device flow; token at `/workspace/group/.gmail-token.json`. | `GOOGLE_GMAIL_CLIENT_ID`, `GOOGLE_GMAIL_CLIENT_SECRET` |
| `google-calendar` | List, create, update, delete calendar events. Supports non-primary calendars. OAuth2 device flow; token at `/workspace/group/.gcal-token.json`. | `GOOGLE_CAL_CLIENT_ID`, `GOOGLE_CAL_CLIENT_SECRET` |
| `groceries` | Add/remove/list grocery items by category (meat, fruit-veg, pantry, chemist…). State in `/workspace/group/groceries.json`. | — |
| `mobility-tracker` | Manage physiotherapy exercises and workout logs in Firestore. | `FIREBASE_SERVICE_ACCOUNT` |
| `motion` | Motion task manager: list, create, update, delete tasks with auto-scheduling. Post-create `update --start-date` is required for Motion to schedule the task. | `MOTION_API_KEY`, `MOTION_WORKSPACE_ID` |
| `nutri-skill` | Nutrition tracking: log meals (free-text or saved foods), OCR nutrition labels from photos, log water, view daily/weekly summaries. Connects to a FastAPI backend. | `NUTRI_API_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_VISION_MODEL`, `OPENROUTER_TEXT_MODEL` |
| `openproject` | Multi-project task management via OpenProject MCP server. Date-range queries, task create/update/link, project summaries. | `OPENPROJECT_MCP_URL` (optional; defaults to `http://localhost:8085`) |
| `paper-trader` | Read-only view of mean-reversion paper trading portfolio. Reads from a host-side JSON file via `additionalMounts`. | `additionalMounts` on group config |
| `pdf-generator` | Convert Markdown or HTML to PDF (Pandoc), or render a URL to PDF (wkhtmltopdf). | Pandoc, wkhtmltopdf (bundled) |
| `status` | Quick health check: workspace mounts, tool availability, container utility versions, task snapshot. Main-channel only. | — |
| `subscription-reconciler` | Family subscription reconciliation from bank statements and Gmail receipts. Shows spending by family member, mysteries, and unmatched transactions. Talks to a host-side Docker service at `host.docker.internal:8400`. | Subscription Reconciler service running on host |
| `tabletennis` | Track Pymble Table Tennis Club sessions, entry fees, lesson credits, and competition fees for George and Henry. SQLite at `/workspace/group/tabletennis.db`. | — |
| `usage` | Show Claude token usage statistics (last 30 days) from the NanoClaw SQLite database. Main-channel only. | Requires `/workspace/project` mount (main group) |
| `weather` | Current weather and forecasts via wttr.in (no key). Falls back to open-meteo JSON API for coordinates-based queries. | — |

**Skills that are main-channel only** (`capabilities`, `status`, `usage`) check for the presence of `/workspace/project` — which is only mounted for the main group.

---

## Message Flow

### Inbound (User → Agent)

```
1.  User sends a message in WhatsApp / Telegram / Discord

2.  Channel adapter receives it, calls onMessage() callback
    → db.storeMessage({ chatJid, sender, content, timestamp })

3.  Message loop (index.ts) polls db.getNewMessages() every 2 s
    → returns rows with timestamp > lastTimestamp

4.  For each chatJid with new messages:
    a. Is chatJid in registeredGroups?  No → skip
    b. Is this the main group OR does any message match TRIGGER_PATTERN?
       No → skip (messages stored but not processed)

5.  GroupQueue accepts the work item; waits if MAX_CONCURRENT_CONTAINERS reached

6.  processGroupMessages() fetches the full message history since
    lastAgentTimestamp[group] via db.getMessagesSince()

7.  runAgent() serialises input, calls runContainerAgent():
    - builds volume mounts (workspace, global, ipc, sessions, skills)
    - spawns:  docker run --rm nanoclaw-agent:latest
    - writes input JSON to container stdin
    - streams stdout; parses sentinel-delimited ContainerOutput blobs
    - calls onOutput(text) for each parsed output

8.  onOutput() → routeOutbound() → channel.sendMessage(chatJid, text)

9.  After container exits:
    - save sessionId to DB
    - update lastAgentTimestamp[group]
    - save router state to DB
```

### Outbound During a Run (Agent → User, Mid-Session)

```
1.  Agent calls mcp__nanoclaw__send_message(text)

2.  ipc-mcp-stdio.ts writes:
      data/ipc/{group}/messages/{uuid}.json

3.  Host IPC watcher (ipc.ts) polls every 1 s, finds file

4.  Validates authorization (group matches source folder)

5.  Calls routeOutbound() → channel.sendMessage()

6.  Message appears in chat immediately, without waiting for container exit
```

### Follow-up Message During a Run (User → Active Container)

```
1.  User sends another message while container is running

2.  Stored in DB as normal

3.  Message loop detects it; GroupQueue sees group is busy

4.  Host writes the message to:
      data/ipc/{group}/input/{uuid}.json

5.  Agent runner polls /workspace/ipc/input/ every 2 s

6.  Found file is merged into the next MessageStream push

7.  Agent receives it as a new user turn within the same session
```

---

## Security Model

Security is layered. Each layer is independent so that a failure in one does not compromise the others.

### Layer 1 — Container Isolation

The primary security boundary. Every agent run is an ephemeral Linux VM:

- Only explicitly mounted directories are visible inside the container
- Processes inside cannot affect the host filesystem or process table
- Runs as unprivileged user `node` (uid 1000)
- Destroyed immediately on exit (`--rm`)

### Layer 2 — Mount Validation

Before any user-configured `additionalMounts` are passed to Docker:

- Paths are resolved (symlinks expanded)
- Validated against `~/.config/nanoclaw/mount-allowlist.json` (outside project root, never mountable itself)
- Blocked if they match known sensitive patterns (`.ssh`, `.env`, `credentials`, etc.)
- Non-main groups can be forced to mount read-only

### Layer 3 — Credential Proxy

API keys (ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN) never enter the container:

- Containers proxy all Anthropic API calls through `http://host:3001`
- Proxy injects real `Authorization` headers before forwarding
- Containers receive placeholder values that are useless outside the proxy

### Layer 4 — IPC Authorization

Containers can only reach the host through the IPC file channel:

- Each container writes to its own `data/ipc/{group}/` directory
- The IPC watcher validates that the `folder` in each request matches the directory it was found in
- Only the **main group** (self-chat) can: schedule tasks for other groups, register new groups, or write global memory

### Trust Hierarchy

| Principal | Trust | Capabilities |
|---|---|---|
| Main group (self-chat) | Trusted admin | Full: global memory, cross-group tasks, group registration, custom mounts |
| Non-main groups | Untrusted (user input) | Own group only: messages, tasks, local files |
| Container agents | Sandboxed | Only mounted paths; API access via proxy; IPC to host |

---

## Memory System

The agent's persistent memory is managed through a folder hierarchy on the host, mounted into the container.

```
groups/
├── CLAUDE.md               ← global memory  (read by all agents)
├── global/                 ← additional global files (main group rw, others ro)
│   └── *.md
└── {channel}_{group-name}/ ← per-group workspace
    ├── CLAUDE.md           ← group memory  (read+write by this group's agent)
    ├── media/              ← received attachments
    ├── logs/               ← container logs
    └── *.md                ← agent-created notes and documents
```

How it loads:

1. Container `cwd` is `/workspace/group`
2. Claude Agent SDK with `settingSources: ['project', 'user']` auto-loads `CLAUDE.md` files walking up from `cwd`
3. `/workspace/global/CLAUDE.md` (if non-main) is passed as `systemPrompt` to the SDK directly
4. The agent can write to `./CLAUDE.md` to update its own memory; main group can write to `../CLAUDE.md` (global)

---

## Startup Sequence

```
main() in src/index.ts
  │
  ├─ 1. Open SQLite; run migrations
  ├─ 2. Load registeredGroups, sessions, router state from DB
  ├─ 3. Discover and connect all registered channels
  ├─ 4. Kill any orphaned containers from previous crash
  ├─ 5. Start credential proxy
  ├─ 6. Start IPC watcher (1 s poll)
  ├─ 7. Start task scheduler (60 s poll)
  └─ 8. Start message loop (2 s poll)
```

NanoClaw runs as a **systemd service** on Linux. Use `start.sh` (a thin wrapper around `systemctl`) for lifecycle management:

```bash
./start.sh start    # build then start
./start.sh stop
./start.sh restart
systemctl status nanoclaw
journalctl -u nanoclaw -f
```

The service is configured with `Restart=always` and `RestartSec=5` — it restarts automatically on crash. Orphaned containers from a previous crash are killed at startup.

---

## Key File Reference

```
src/
├── index.ts                Main orchestrator; message loop; runAgent()
├── container-runner.ts     Docker spawn; volume mounts; sentinel parsing
├── task-scheduler.ts       Cron/interval/once task execution
├── ipc.ts                  File-based IPC watcher; authorization
├── db.ts                   SQLite wrapper; all table definitions
├── group-queue.ts          Per-group concurrency queue
├── router.ts               formatMessages(); routeOutbound()
├── credential-proxy.ts     Auth header injection proxy
├── mount-security.ts       Mount allowlist validation
├── config.ts               All non-secret configuration constants
├── env.ts                  .env reader (never writes process.env)
├── logger.ts               Pino logger setup
├── types.ts                Shared TypeScript interfaces
└── channels/
    ├── registry.ts         registerChannel() / getChannelFactory()
    ├── index.ts            Barrel imports (triggers self-registration)
    ├── discord.ts          Discord bot (slash commands, threads, DMs, audio)
    └── telegram.ts         Telegram bot

container/
├── Dockerfile              node:22-slim + Chromium + Python + Claude Code CLI
├── build.sh                Build helper (~2 min)
└── agent-runner/
    ├── src/
    │   ├── index.ts        Agent runner; MessageStream; SDK query loop
    │   └── ipc-mcp-stdio.ts MCP server (send_message, schedule_task, …)
    └── package.json        deps: claude-agent-sdk, mcp/sdk, cron-parser, zod

container/skills/           Synced into /home/node/.claude/skills/ at runtime
├── adhd-coach/             ADHD coaching with Pomodoro and cron scheduling
├── agent-browser/          Headless Chromium via semantic refs
├── brave-search/           Brave Search API (needs BRAVE_API_KEY)
├── capabilities/           Installed skills and tool inventory
├── gmail/                  Gmail read/manage (needs GOOGLE_GMAIL_* creds)
├── google-calendar/        Google Calendar (needs GOOGLE_CAL_* creds)
├── groceries/              Grocery list manager
├── mobility-tracker/       Firestore physio tracker (needs FIREBASE_SERVICE_ACCOUNT)
├── motion/                 Motion task manager (needs MOTION_API_KEY)
├── nutri-skill/            Nutrition tracking with photo OCR (needs NUTRI_API_URL)
├── openproject/            OpenProject task management
├── paper-trader/           Paper trading portfolio reader (needs additionalMounts)
├── pdf-generator/          Markdown/HTML/URL → PDF via Pandoc or wkhtmltopdf
├── status/                 Quick health check (main-channel only)
├── subscription-reconciler/ Family subscription reconciliation
├── tabletennis/            Table tennis session and fee tracker
├── usage/                  Claude token usage stats (main-channel only)
└── weather/                Weather via wttr.in / open-meteo

groups/
├── CLAUDE.md               Global agent memory
└── {name}/                 Per-group workspace (one folder per registered group)

data/
├── sessions/{group}/.claude/    Claude Code session data + settings + skills
├── ipc/{group}/messages/        Agent→host message IPC
├── ipc/{group}/tasks/           Agent→host task IPC
└── ipc/{group}/input/           Host→agent follow-up IPC

.claude/skills/             Claude Code skills (run by developer in Claude Code, not by agents)
store/
└── messages.db             SQLite: messages, chats, groups, tasks, sessions, token_usage
```

---

## Related Documents

| Document | Contents |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Design philosophy and original requirements |
| [SPEC.md](SPEC.md) | Message format and internal protocol specification |
| [SECURITY.md](SECURITY.md) | Security model in depth; threat model; audit notes |
| [SDK_DEEP_DIVE.md](SDK_DEEP_DIVE.md) | How the Claude Agent SDK is integrated; version history |
| [STABILITY.md](STABILITY.md) | Known issues and workarounds |
| [DEBUG_CHECKLIST.md](DEBUG_CHECKLIST.md) | Troubleshooting flowchart |
| [docker-sandboxes.md](docker-sandboxes.md) | Container setup and hypervisor model |
