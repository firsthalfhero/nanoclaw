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

## Custom Skills (ported from OpenClaw)

Skills live in `container/skills/` and are synced into `/home/node/.claude/skills/` inside every container at startup. Adding or editing a skill file takes effect on the next container run — no rebuild needed.

| Skill | Script | Notes |
|-------|--------|-------|
| `adhd-coach` | `scripts/adhd_coach.py` | State at `/workspace/group/adhd-coach-state.json`. Cron jobs for morning briefing (8am AEST weekdays), check-ins (45 min), end-of-day (3pm AEST weekdays). Calls groceries script at end-of-day. |
| `google-calendar` | `scripts/gcal.py` | OAuth2 device flow. Token at `/workspace/group/.gcal-token.json`. Re-auth: run `python3 .../gcal.py auth` inside container. Needs `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`. |
| `groceries` | `scripts/groceries.py` | Simple list manager. No env vars needed. |
| `brave-search` | none (curl) | Needs `BRAVE_API_KEY`. Uses Brave LLM Context API. |
| `weather` | none (web_fetch) | No API key. Uses wttr.in + open-meteo. |
| `motion` | `motion_cli.py` | **Blocked** — imports from external `motion-scheduler` project. See Motion section below. |

### Env Vars Injected into Containers

`src/container-runner.ts` explicitly injects these from `.env` (explicit allowlist, not full env):
`MOTION_API_KEY`, `MOTION_WORKSPACE_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BRAVE_API_KEY`

To add a new skill env var, add it to the `skillEnv` allowlist in `buildContainerArgs()`.

### Motion Skill — Blocked

`motion_cli.py` imports Python modules from a separate `motion-scheduler` project
(expected at `/opt/motion-scheduler/motion/` in the container). Until that project is available:
- The SKILL.md is installed and the skill description will load, but running the script will fail.
- To fix: either mount the motion-scheduler project into the container via `additionalMounts`,
  or rewrite `motion_cli.py` as a self-contained script using the Motion REST API directly.

## Development

Run commands directly—don't tell the user to run them.

```bash
npm run dev          # Run with hot reload
npm run build        # Compile TypeScript
./container/build.sh # Rebuild agent container
```

Service management:
```bash
# macOS (launchd)
launchctl load ~/Library/LaunchAgents/com.nanoclaw.plist
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist
launchctl kickstart -k gui/$(id -u)/com.nanoclaw  # restart

# Linux (systemd)
systemctl --user start nanoclaw
systemctl --user stop nanoclaw
systemctl --user restart nanoclaw
```

## Troubleshooting

**WhatsApp not connecting after upgrade:** WhatsApp is now a separate channel fork, not bundled in core. Run `/add-whatsapp` (or `git remote add whatsapp https://github.com/qwibitai/nanoclaw-whatsapp.git && git fetch whatsapp main && (git merge whatsapp/main || { git checkout --theirs package-lock.json && git add package-lock.json && git merge --continue; }) && npm run build`) to install it. Existing auth credentials and groups are preserved.

## Container Build Cache

The container buildkit caches the build context aggressively. `--no-cache` alone does NOT invalidate COPY steps — the builder's volume retains stale files. To force a truly clean rebuild, prune the builder then re-run `./container/build.sh`.
