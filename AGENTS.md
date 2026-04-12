# NanoClaw

Project guidance for Codex-style coding agents working in this repository.

## Quick Context

Single Node.js process with a skill-based channel system. Channels self-register at startup. Messages route through the orchestrator to isolated agent containers. Each group has its own filesystem and memory.

## Key Files

- `src/index.ts` - orchestrator entry point, state loading, polling loop, agent invocation
- `src/channels/registry.ts` - channel registry and self-registration
- `src/router.ts` - inbound formatting and outbound routing
- `src/ipc.ts` - IPC watcher and task processing
- `src/container-runner.ts` - container execution and streaming
- `src/container-runtime.ts` - runtime management and cleanup
- `src/task-scheduler.ts` - scheduled task execution
- `src/db.ts` - SQLite schema and persistence
- `groups/*/CLAUDE.md` - per-group memory files

## Working Style

- Prefer small, direct code changes over adding new configuration.
- Preserve the existing architecture: channels register themselves, the orchestrator stays small, and isolation happens at the container boundary.
- When changing runtime or security behavior, trace impacts across `src/index.ts`, container execution, IPC, and the database.
- Run direct commands yourself instead of instructing the user to do so.

## Graphify

This project has a Graphify knowledge graph at `graphify-out/`.

Rules:

- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes and community structure.
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files first.
- After modifying code files in this session, rebuild the code graph with:

```bash
python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

## Validation

- Build with `npm run build` after TypeScript changes.
- Run targeted tests when possible.
- If a change affects container behavior, verify the impacted path end-to-end when practical.
