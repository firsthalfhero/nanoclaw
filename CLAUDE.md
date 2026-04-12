# NanoClaw

Personal Claude assistant. See [README.md](README.md) for philosophy and setup. See [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) for architecture decisions.

## Quick Context

Single Node.js process with skill-based channel system. Channels (WhatsApp, Telegram, Slack, Discord, Gmail) are skills that self-register at startup. Messages route to Claude Agent SDK running in containers (Linux VMs). Each group has isolated filesystem and memory.

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

## Development

Run commands directly—don't tell the user to run them.

```bash
npm run dev          # Run with hot reload (dev only — not suitable for persistent use on Windows)
npm run build        # Compile TypeScript
./container/build.sh # Rebuild agent container (run from Git Bash, not PowerShell)
docker build -t nanoclaw-agent:latest container/  # Windows alternative to build.sh
```

## Running on Windows

PM2 does not work reliably on Windows with this project (pino-pretty worker thread conflicts, CWD issues). Use `start.ps1` instead:

```powershell
# Start (builds first, kills any existing instance, writes logs)
.\start.ps1

# Check if running
Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue

# Tail logs
Get-Content logs\nanoclaw-out.log -Wait

# Stop
Stop-Process -Id <PID> -Force
```

Logs are written to `logs/nanoclaw-out.log` and `logs/nanoclaw-err.log`.

The agent container is **ephemeral** — it spins up per conversation and disappears when done (`docker run --rm`). It will not appear as a persistent container in Docker Desktop. Only the Node.js host process (port 3001) is persistent.

## Troubleshooting

**Multiple orphaned containers:** If NanoClaw crashes and restarts repeatedly, previous containers may keep running (holding resources). Check with `docker ps --filter "name=nanoclaw"` and kill with `docker kill <name>`. NanoClaw kills orphans automatically on startup.

**Port 3001 EADDRINUSE:** A previous NanoClaw instance is still running. Find it with `Get-NetTCPConnection -LocalPort 3001` and stop it with `Stop-Process -Id <PID> -Force`. Running `.\start.ps1` handles this automatically.

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

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
