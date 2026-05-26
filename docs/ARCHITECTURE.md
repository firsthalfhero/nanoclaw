# NanoClaw Architecture

A developer's guide to how NanoClaw works — from a user message arriving on WhatsApp to a Claude agent running in an isolated container and a reply appearing in the chat.

For design philosophy and requirements, see [REQUIREMENTS.md](REQUIREMENTS.md). For the security model in depth, see [SECURITY.md](SECURITY.md). For the Claude Agent SDK integration, see [SDK_DEEP_DIVE.md](SDK_DEEP_DIVE.md).

---

## System Overview

NanoClaw is a single Node.js process (the **host**) that:

1. Receives messages from one or more messaging channels (WhatsApp, Telegram, Discord, Slack)
2. Stores every message in SQLite
3. Polls for new messages and spawns an ephemeral Docker container per invocation
4. Runs the Claude Agent SDK inside the container against the conversation history
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

### `src/config.ts` — Configuration

All non-secret configuration lives here, read from environment variables at startup.

| Constant | Default | Purpose |
|---|---|---|
| `ASSISTANT_NAME` | `Andy` | Trigger prefix (`@Andy`) |
| `POLL_INTERVAL` | 2 000 ms | Message poll rate |
| `SCHEDULER_POLL_INTERVAL` | 60 000 ms | Task check rate |
| `CONTAINER_IMAGE` | `nanoclaw-agent:latest` | Docker image tag |
| `CONTAINER_TIMEOUT` | 1 800 000 ms | Hard container kill deadline |
| `IDLE_TIMEOUT` | 1 800 000 ms | Kill after this long with no output |
| `MAX_CONCURRENT_CONTAINERS` | 5 | Global container concurrency cap |
| `TRIGGER_PATTERN` | `/^@Andy\b/i` | Non-main groups must match this |

---

## Container Components

### `container/agent-runner/src/index.ts` — Agent Runner

The executable that runs inside every container. It:

1. Reads a `ContainerInput` JSON blob from stdin (prompt, sessionId, groupFolder, chatJid, isMain)
2. Constructs a `MessageStream` — a push-based async iterable used as the prompt — so the SDK never closes stdin mid-conversation
3. Calls `query()` from the Claude Agent SDK in a loop
4. Polls `data/ipc/input/` for follow-up messages piped in by the host while the agent is running
5. Emits `ContainerOutput` JSON wrapped in sentinel markers on stdout:
   ```
   ---NANOCLAW_OUTPUT_START---
   {"text": "...", "sessionId": "..."}
   ---NANOCLAW_OUTPUT_END---
   ```
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

Session IDs are persisted to DB after each run; passing the same ID on the next invocation resumes the Claude Code session, preserving conversation history and tool call context.

### `container/agent-runner/src/ipc-mcp-stdio.ts` — MCP Server

A stdio-based MCP server exposed to the agent as `mcp__nanoclaw__*` tools. It writes JSON files to the IPC directories; the host IPC watcher processes them asynchronously.

| Tool | What it does |
|---|---|
| `send_message(text)` | Sends a message to the group immediately (progress update) |
| `schedule_task(prompt, schedule_type, schedule_value)` | Creates a recurring or one-time task |
| `list_tasks()` | Lists tasks (own group, or all groups if main) |
| `pause_task(id)` / `resume_task(id)` / `cancel_task(id)` | Manage task lifecycle |

### `container/skills/` — Agent Skills

Skills are Markdown files (with YAML frontmatter) synced from `container/skills/` into `/home/node/.claude/skills/` on every container start. They become available as Claude Code slash commands inside the container.

```yaml
---
name: motion
description: Manage tasks and projects via Motion API
trigger: "motion"
model: claude-opus-4-7
---
```

Built-in skills:

| Skill | Purpose | Needs |
|---|---|---|
| `adhd-coach` | Daily briefings, check-ins, end-of-day summary | Cron tasks |
| `google-calendar` | Read/write Google Calendar | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| `groceries` | Simple list manager | — |
| `brave-search` | Web search via Brave API | `BRAVE_API_KEY` |
| `weather` | Current conditions via wttr.in | — |
| `motion` | Task/project management via Motion API | `MOTION_API_KEY`, `MOTION_WORKSPACE_ID` |
| `paper-trader` | Read paper trading portfolio state | `additionalMounts` on group |
| `agent-browser` | Headless Chromium automation | — |

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
├── env.ts                  .env file reader
├── logger.ts               Pino logger setup
├── types.ts                Shared TypeScript interfaces
└── channels/
    ├── registry.ts         registerChannel() / getChannelFactory()
    ├── index.ts            Barrel imports (triggers self-registration)
    ├── discord.ts          Discord bot (slash commands, threads, DMs, audio)
    └── telegram.ts         Telegram bot

container/
├── Dockerfile              Image: node:22-slim + Chromium + Python + ffmpeg
├── build.sh                Build helper
└── agent-runner/
    ├── src/
    │   ├── index.ts        Agent runner; MessageStream; SDK query loop
    │   └── ipc-mcp-stdio.ts MCP server (send_message, schedule_task, …)
    └── package.json

container/skills/
├── adhd-coach/             Daily briefing and check-in coach
├── agent-browser/          Headless Chromium automation
├── brave-search/           Brave Search API wrapper
├── gmail/                  Gmail read/send
├── google-calendar/        Google Calendar OAuth
├── groceries/              Simple list manager
├── motion/                 Motion API (tasks, projects)
├── paper-trader/           Paper trading portfolio reader
├── weather/                wttr.in + open-meteo
└── …                       (additional custom skills)

groups/
├── CLAUDE.md               Global agent memory
└── {name}/                 Per-group workspace (one folder per registered group)

data/
├── sessions/{group}/.claude/    Claude Code session data
├── ipc/{group}/messages/        Agent→host message IPC
├── ipc/{group}/tasks/           Agent→host task IPC
└── ipc/{group}/input/           Host→agent follow-up IPC

.claude/skills/             Claude Code skills (run by developer, not agents)
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
