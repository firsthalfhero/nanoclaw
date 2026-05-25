# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# NanoClaw

Personal Claude assistant. See [README.md](README.md) for philosophy and setup. See [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) for architecture decisions.

## Quick Context

Single Node.js process with skill-based channel system. Channels (WhatsApp, Telegram, Slack, Discord, Gmail) are skills that self-register at startup. Messages route to Claude Agent SDK running in containers (Linux VMs). Each group has isolated filesystem and memory.

**Architecture**: `src/` contains the orchestrator and channel adapters (Node.js). `container/` contains the agent runner and custom skills that run inside isolated Docker/Apple Container sandboxes. They communicate via IPC.

## Key Files

| File | Purpose |
|------|---------|
| `src/index.ts` | Orchestrator: state, message loop, agent invocation |
| `src/channels/registry.ts` | Channel registry (self-registration at startup) |
| `src/ipc.ts` | IPC watcher and task processing |
| `src/router.ts` | Message formatting and outbound routing |
| `src/config.ts` | Trigger pattern, paths, intervals |
| `src/container-runner.ts` | Spawns agent containers with mounts |
| `src/task-scheduler.ts` | Runs scheduled tasks |
| `src/db.ts` | SQLite operations |
| `groups/{name}/CLAUDE.md` | Per-group memory (isolated) |
| `container/skills/agent-browser.md` | Browser automation tool (available to all agents via Bash) |

## Skills

| Skill | When to Use |
|-------|-------------|
| `/setup` | First-time installation, authentication, service configuration |
| `/customize` | Adding channels, integrations, changing behavior |
| `/debug` | Container issues, logs, troubleshooting |
| `/update-nanoclaw` | Bring upstream NanoClaw updates into a customized install |
| `/qodo-pr-resolver` | Fetch and fix Qodo PR review issues interactively or in batch |
| `/get-qodo-rules` | Load org- and repo-level coding rules from Qodo before code tasks |
| `/graphify` | Build knowledge graphs from project files for token-efficient context. Run in the target project directory. (`.claude/skills/graphify/SKILL.md`) |
| `/obsidian-cli` | Structured Obsidian vault operations: search, task management, wikilink-aware note moves. Requires Obsidian v1.12+ running for IPC commands. (`.claude/skills/obsidian-cli/SKILL.md`) |

## Custom Skills (ported from OpenClaw)

Skills live in `container/skills/` and are synced into `/home/node/.claude/skills/` inside every container at startup. Adding or editing a skill file takes effect on the next container run — no rebuild needed.

| Skill | Script | Notes |
|-------|--------|-------|
| `adhd-coach` | `scripts/adhd_coach.py` | State at `/workspace/group/adhd-coach-state.json`. Cron jobs for morning briefing (8am AEST weekdays), check-ins (45 min), end-of-day (3pm AEST weekdays). Calls groceries script at end-of-day. |
| `google-calendar` | `scripts/gcal.py` | OAuth2 device flow. Token at `/workspace/group/.gcal-token.json`. Re-auth: run `python3 .../gcal.py auth` inside container. Needs `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`. |
| `groceries` | `scripts/groceries.py` | Simple list manager. No env vars needed. |
| `brave-search` | none (curl) | Needs `BRAVE_API_KEY`. Uses Brave LLM Context API. |
| `weather` | none (web_fetch) | No API key. Uses wttr.in + open-meteo. |
| `motion` | `motion_cli.py` | Self-contained stdlib script. Needs `MOTION_API_KEY` + `MOTION_WORKSPACE_ID`. |
| `paper-trader` | `scripts/portfolio_cli.py` | Reads paper trading state from host disk. Requires `additionalMounts` on the group (see Paper Trader section). |

### Env Vars Injected into Containers

`src/container-runner.ts` explicitly injects these from `.env` (explicit allowlist, not full env):
`MOTION_API_KEY`, `MOTION_WORKSPACE_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BRAVE_API_KEY`

To add a new skill env var, add it to the `skillEnv` allowlist in `buildContainerArgs()`.

### Motion Skill

`motion_cli.py` has been rewritten as a self-contained stdlib script using the Motion REST API directly (no external imports). Needs `MOTION_API_KEY` + `MOTION_WORKSPACE_ID` in `.env`.

### Paper Trader Skill

Reads live state from the mean reversion paper trading engine. Data is mounted read-only into the container via `additionalMounts` on the main group. The host path `C:\Users\George\Documents\projects\mean-reversion-strategy-sandbox\data` is mounted to `/workspace/extra/paper-trader/` in the container. Script reads `/workspace/extra/paper-trader/paper_state.json`.

## Git Rules

These rules are mandatory. Violations make it impossible to audit which AI introduced a change.

### Co-author tag — required on every commit, no exceptions

Every commit must include a co-author trailer in the commit message body identifying which tool/model generated it. Examples:

```text
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Co-authored-by: aider (openrouter/anthropic/claude-sonnet-4-5) <aider@aider.chat>
Co-authored-by: aider (openrouter/moonshotai/kimi-k2.6) <aider@aider.chat>
```

No exceptions: bug fixes, typo patches, version bumps — all of them. A commit without this tag will be treated as unattributed.

### Branch and merge rules

- Claude Code may commit directly to `main` for small, self-contained changes.
- For larger features or anything that touches security/auth/container behavior, create a branch prefixed `CLAUDE-` and open a PR.
- Never force-push (`--force` / `--force-with-lease`) to `main`.
- Never bypass hooks (`--no-verify`).
- Never amend a commit that has already been pushed.
- Do not create empty commits.

### Identifying AI authorship in git log

- Claude commits: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- Aider commits: `Co-authored-by: aider (claude-sonnet-4-5) <aider@aider.chat>`
- Codex commits: `Co-authored-by: Codex <codex@openai.com>`
- Human-only commits: no co-author trailer

To find all Claude-authored commits: `git log --all --grep="Co-Authored-By: Claude"`  
To find all Aider-authored commits: `git log --all --grep="Co-authored-by: aider"`  
To find all Codex-authored commits: `git log --all --grep="Co-authored-by: Codex"`

### Aider configuration

Aider is configured via `.aider.conf.yml` (gitignored). It reads `CLAUDE.md`, `README.md`, and `docs/REQUIREMENTS.md` as always-on context, auto-commits with `Co-authored-by` attribution, and runs `npm run build` as its test command.

## Development

Run commands directly—don't tell the user to run them.

### Building and Type Safety

```bash
npm run build        # Compile TypeScript to dist/
npm run typecheck    # Type check without emitting (catch issues before build)
npm run format:check # Check code formatting
npm run format:fix   # Auto-fix code formatting
npm run dev          # Run with hot reload (dev only — not suitable for persistent use on Windows)
```

### Testing

```bash
npm run test         # Run all tests once (Vitest)
npm run test:watch   # Run tests in watch mode (re-run on file change)
```

Tests live in `src/**/*.test.ts`. When adding a feature, create a `.test.ts` file in the same directory.

### Container

```bash
./container/build.sh # Rebuild agent container (run from Git Bash or Linux shell)
docker build -t nanoclaw-agent:latest container/  # Alternative: direct Docker command
```

The container image contains the agent runtime (Claude Agent SDK) and all custom skills. Rebuilding takes ~2min. Changes to skill files in `container/skills/` take effect on the next agent invocation without rebuild.

## Running NanoClaw

PM2 does not work reliably with this project (pino-pretty worker thread conflicts, CWD issues). Use the start script with automatic watchdog instead.

### Linux/macOS

```bash
# Start (builds first, kills any existing instance, starts watchdog, writes logs)
./start.sh

# Stop
./start.sh --stop

# Check logs
tail -f logs/nanoclaw-out.log
tail -f logs/nanoclaw-watchdog.log
```

### Windows (Legacy)

```powershell
# Start (builds first, kills any existing instance, starts watchdog, writes logs)
.\start.ps1

# Stop
.\start.ps1 -Stop

# Check logs
Get-Content logs\nanoclaw-out.log -Wait
```

Logs are written to `logs/nanoclaw-out.log` (stdout) and `logs/nanoclaw-err.log` (stderr).

The agent container is **ephemeral** — it spins up per conversation and disappears when done (`docker run --rm`). It will not appear as a persistent container in Docker Desktop. Only the Node.js host process (port 3001) is persistent.

## Adding Custom Skills

Custom skills live in `container/skills/` and are automatically synced into `/home/node/.claude/skills/` inside every container at startup.

### File Format

Create a `.md` file (e.g., `container/skills/my-skill/SKILL.md`) with YAML frontmatter:

```yaml
---
name: my-skill
description: Does something useful
trigger: "my command"
model: claude-opus-4-7
---
```

The skill markdown body becomes the prompt Claude sees. Reference any scripts in the same folder.

### Python Scripts

Scripts in the same folder (e.g., `scripts/my_script.py`) are available to the skill. Import them:

```python
import sys; sys.path.append('/home/node/.claude/skills/my-skill')
from scripts.my_script import my_function
```

Scripts must be self-contained or use only Python stdlib (no pip packages unless added to `container/Dockerfile`).

### Environment Variables

Add new env vars to the allowlist in `src/container-runner.ts` (`buildContainerArgs()`) before they're injected into containers.

### Testing Locally

After adding or editing a skill, changes take effect on the next container invocation. Rebuild the container only if you've modified the Dockerfile or added pip dependencies.

## Documentation

See `docs/` for deeper dives:
- **REQUIREMENTS.md** — Architecture decisions and philosophy
- **SPEC.md** — Message format and internal protocols
- **SECURITY.md** — Security model and isolation guarantees
- **SDK_DEEP_DIVE.md** — How the Claude Agent SDK is integrated
- **STABILITY.md** — Known issues and workarounds
- **DEBUG_CHECKLIST.md** — Troubleshooting flowchart
- **docker-sandboxes.md** — Container setup and the hypervisor model

## Troubleshooting

**Multiple orphaned containers:** If NanoClaw crashes and restarts repeatedly, previous containers may keep running (holding resources). Check with `docker ps --filter "name=nanoclaw"` and kill with `docker kill <name>`. NanoClaw kills orphans automatically on startup.

**Port 3001 EADDRINUSE:** A previous NanoClaw instance is still running.

- Linux/macOS: `lsof -i :3001` to find the PID, then `kill -9 <PID>`. Running `./start.sh --stop` handles this automatically.
- Windows: `Get-NetTCPConnection -LocalPort 3001` to find the PID, then `Stop-Process -Id <PID> -Force`. Running `.\start.ps1 -Stop` handles this automatically.

**IPv4/IPv6 on Windows:** NanoClaw patches `dns.setDefaultResultOrder('ipv4first')` at startup to prevent undici happy-eyeballs failures (IPv6 ENETUNREACH on this network).

**WhatsApp not connecting after upgrade:** WhatsApp is now a separate channel fork, not bundled in core. Run `/add-whatsapp` (or `git remote add whatsapp https://github.com/qwibitai/nanoclaw-whatsapp.git && git fetch whatsapp main && (git merge whatsapp/main || { git checkout --theirs package-lock.json && git add package-lock.json && git merge --continue; }) && npm run build`) to install it. Existing auth credentials and groups are preserved.

## Remote Access (RDP via ngrok)

RDP is configured on port **65136** (non-standard). ngrok tunnels it externally via a Docker container at `c:\Users\George\Documents\projects\ngrok\local-tunnel\`.

- ngrok config: `C:\Users\George\Documents\projects\ngrok\local-tunnel\ngrok.yml`
- ngrok container: `local-tunnel-ngrok-1` (authtoken in `NGROK_AUTHTOKEN` env var, account: george.cains@gmail.com)
- ngrok inspector: http://localhost:4040
- The public TCP address changes on every container restart (free plan). Check current address at http://localhost:4040/api/tunnels

To get the current RDP address:
```bash
curl -s http://localhost:4040/api/tunnels | python -c "import sys,json; t=[x for x in json.load(sys.stdin)['tunnels'] if x['name']=='rdp']; print(t[0]['public_url'] if t else 'tunnel not running')"
```

## Container Build Cache

The container buildkit caches the build context aggressively. `--no-cache` alone does NOT invalidate COPY steps — the builder's volume retains stale files. To force a truly clean rebuild, prune the builder then re-run `./container/build.sh`.

## Initial Setup

Run `/setup` (in Claude Code) to configure NanoClaw for the first time. This handles:
- Installing Node.js dependencies
- Authenticating with messaging platforms (WhatsApp, Telegram, etc.)
- Building the container image
- Setting up `.env` with secrets and API keys
- Ensuring port 3001 is accessible (automatically handled by start scripts)

For subsequent changes (adding channels, modifying trigger words), use `/customize`.

## Discord Channel

Discord support is fully integrated. The bot self-registers at startup and manages slash commands, message delivery, and audio transcription.

### Setup

1. **Create a Discord Application:**
   - Visit [Discord Developer Portal](https://discord.com/developers/applications)
   - Click "New Application"
   - Go to "Bot" tab → "Add Bot"
   - Copy the token

2. **Set Environment Variable:**
   ```bash
   DISCORD_BOT_TOKEN=your_bot_token_here
   ```

3. **Configure Bot Permissions:**
   - OAuth2 → URL Generator
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Read Message History`, `Embed Links`, `Attach Files`, `Use Slash Commands`
   - Use generated URL to add bot to your server

4. **Register a Channel with the Group:**
   - Send `/chatid` command in any Discord channel or DM
   - Bot responds with Chat ID (format: `dc:CHANNEL_ID` or `dc:dm:USER_ID` or `dc:thread:THREAD_ID`)
   - Add this ID to the group's `channels` in `.env`

### Features

- **Slash Commands:**
  - `/chatid` — Get the Chat ID for group registration
  - `/ping` — Check if the bot is online

- **Message Handling:**
  - Text messages, threads, and DMs supported
  - Trigger pattern and group `requiresTrigger` settings respected
  - Bot mentions counted as valid triggers

- **Audio Transcription:**
  - Audio attachments (MP3, WAV, OGG) automatically transcribed via Google Gemini
  - Requires `GOOGLE_GEMINI_API_KEY` in `.env`
  - Transcribed text forwarded to agent as `[Voice transcription: ...]`

- **Message Limits:**
  - Discord enforces 2000-character limit; long messages auto-split
  - Attachments downloaded and saved to group `media/` folder

### Implementation Details

- **File:** `src/channels/discord.ts` (507 lines)
- **Tests:** `src/channels/discord.test.ts` (731 lines, 33 tests passing)
- **JID Format:** 
  - Channels: `dc:CHANNEL_ID`
  - Threads: `dc:thread:THREAD_ID`
  - DMs: `dc:dm:USER_ID`

- **Registration:** Auto-registers in `src/channels/index.ts` on startup
- **Message Flow:** Incoming Discord messages → JID conversion → trigger check → agent invocation → response routed back to channel

### Troubleshooting

**Bot doesn't respond to messages:**
- Ensure the bot has "Read Message History" and "Send Messages" permissions in the channel
- Check that the channel is registered (`/chatid` returns a valid ID)
- Verify `DISCORD_BOT_TOKEN` is set and valid
- If `requiresTrigger: true` on the group, message must contain trigger word or mention the bot

**Audio transcription not working:**
- Ensure `GOOGLE_GEMINI_API_KEY` is set in `.env`
- Check that the file is a valid audio format (MP3, WAV, OGG)
- Review agent logs for transcription errors

**Slash commands not visible:**
- Permissions may not include "Use Slash Commands" — update bot invite URL
- Try kicking and re-adding the bot to the server
- Wait a few minutes for Discord to sync permissions

## Knowledge Graph

This project has a graphify knowledge graph at `graphify-out/`. The god nodes (most-connected abstractions) are: `load()`, `GroupQueue`, `main()`, `save()`, and `_get_access_token()`.

**For architecture questions:** Read `graphify-out/GRAPH_REPORT.md` first for god nodes and community structure.

**After modifying code:** Run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to rebuild the graph incrementally (tokens/time are free after the initial build).
