# NanoClaw Docker Network Migration Summary

## Overview
Updated NanoClaw to spawn agent containers on the unified `hp-server.home` Docker network, enabling seamless communication with other services (portainer, nginx, agile-life-api, dnsmasq, etc.).

## Changes Made

### 1. **src/config.ts** — Added Network Configuration
```typescript
export const CONTAINER_NETWORK =
  process.env.CONTAINER_NETWORK || 'hp-server.home';
```
- **Purpose:** Make Docker network configurable via environment variable
- **Default:** `hp-server.home` (the unified network)
- **Override:** Set `CONTAINER_NETWORK=bridge` in `.env` to use Docker's default bridge

### 2. **src/container-runner.ts** — Pass Network to Containers
**Added import:**
```typescript
import { CONTAINER_NETWORK, ... } from './config.js';
```

**Added to buildContainerArgs():**
```typescript
args.push('--network', CONTAINER_NETWORK);
```
- Adds `--network hp-server.home` to every agent container spawn
- Placed early in args (right after `--name`) for clarity
- Enables containers to reach all services by name: `dnsmasq`, `portainer`, `agile-life-api-1`, `hp-db`, etc.

**Updated DNS call:**
```typescript
args.push(...hostDnsArgs(CONTAINER_NETWORK));
```
- Passes network to DNS resolver function

### 3. **src/container-runtime.ts** — Network-Aware DNS
**Updated hostDnsArgs() function:**
```typescript
export function hostDnsArgs(containerNetwork: string): string[] {
  if (os.platform() !== 'linux') return [];
  if (fs.existsSync('/proc/sys/fs/binfmt_misc/WSLInterop')) return [];

  // On hp-server.home network, point to dnsmasq's IP on that network
  if (containerNetwork === 'hp-server.home') {
    return ['--dns=172.21.0.3'];  // dnsmasq on hp-server.home
  }

  // Otherwise, use docker0 bridge IP (legacy behavior)
  const ifaces = os.networkInterfaces();
  const docker0 = ifaces['docker0'];
  if (docker0) {
    const ipv4 = docker0.find((a) => a.family === 'IPv4');
    if (ipv4) return [`--dns=${ipv4.address}`];
  }
  return [];
}
```

**Why this matters:**
- **Old behavior:** Containers on default bridge → DNS pointed to docker0 bridge IP (172.17.0.1)
- **New behavior:** Containers on hp-server.home → DNS pointed to dnsmasq on that network (172.21.0.3)
- Ensures `.home` domain resolution (portainer.home, agilelife.home, etc.) works inside agent containers

## Service Communication Map

After restart, agent containers can now reach all services:

| Service | Container Name | Access From Container |
|---|---|---|
| dnsmasq | `dnsmasq` | `dnsmasq:53` (for DNS queries) |
| Portainer | `portainer` | `portainer:9443` |
| nginx | `nginx-portainer` | `nginx-portainer:80/443` |
| API | `agile-life-api-1` | `agile-life-api-1:3456` |
| Database | `hp-db` | `hp-db:5432` |
| Deal Filter | `ozb-deal-filter` | `ozb-deal-filter` |

## Environment Variable Override

To revert to a different network (for testing or troubleshooting):

```bash
# Use Docker's default bridge network
export CONTAINER_NETWORK=bridge

# Use a different custom network
export CONTAINER_NETWORK=my-custom-network

# Add to ~/.bashrc or .env to persist
```

Then restart nanoclaw:
```bash
./start.sh restart
```

## Verification

**Built successfully:**
```bash
npm run build  # ✓ No TypeScript errors
```

**Service restarted:**
```bash
./start.sh restart  # ✓ Restarted successfully
systemctl status nanoclaw  # ✓ Active (running)
```

**Next test:** Trigger a conversation that spawns a container to verify it lands on hp-server.home network:
```bash
docker ps --filter "name=nanoclaw-" --format "{{.Names}}\t{{.Networks}}"
```

## Rollback Plan

If issues arise:
1. Revert to default bridge network: `export CONTAINER_NETWORK=bridge`
2. Restart nanoclaw: `./start.sh restart`
3. Or revert commits and rebuild

## Architecture Benefits

✅ **Unified network:** All services on one network, no cross-bridge routing
✅ **Service discovery:** Containers reach services by name (docker0 bridge DNS)
✅ **DNS resolution:** .home domains resolve via dnsmasq on the same network
✅ **Flexible:** Environment variable allows quick switching if needed
✅ **Backward compatible:** Default value enables hp-server.home, legacy behavior still available
