/**
 * One-off script: add Obsidian vault mounts to the main group's containerConfig.
 * Safe to re-run — idempotent (strips existing obsidian- mounts before re-adding).
 *
 * Usage: npx tsx scripts/add-vault-mounts.ts
 */
import Database from 'better-sqlite3';
import path from 'path';

const VAULT_BASE =
  'C:\\Users\\George\\Documents\\projects\\obsidian-vault';

const db = new Database(path.resolve('data/nanoclaw.db'));

const row = db
  .prepare('SELECT * FROM registered_groups WHERE is_main = 1')
  .get() as { container_config: string | null; name: string } | undefined;

if (!row) {
  console.error('No main group found in registered_groups');
  process.exit(1);
}

console.log(`Updating main group: ${row.name}`);

const config: { additionalMounts?: Array<{ hostPath: string; containerPath: string; readonly: boolean }> } =
  row.container_config ? JSON.parse(row.container_config) : {};

// Strip any previous obsidian mounts so this is idempotent
const existing = (config.additionalMounts ?? []).filter(
  (m) => !m.containerPath?.startsWith('obsidian-'),
);

config.additionalMounts = [
  ...existing,
  {
    hostPath: `${VAULT_BASE}\\projects`,
    containerPath: 'obsidian-projects',
    readonly: true,
  },
  {
    hostPath: `${VAULT_BASE}\\nanoclaw-memory`,
    containerPath: 'obsidian-memory',
    readonly: false,
  },
];

db.prepare(
  'UPDATE registered_groups SET container_config = ? WHERE is_main = 1',
).run(JSON.stringify(config));

console.log('Done. Updated additionalMounts:');
console.log(JSON.stringify(config.additionalMounts, null, 2));
db.close();
