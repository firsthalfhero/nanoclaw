import dns from 'dns';
import fs from 'fs';
import path from 'path';

// Force IPv4-only DNS on systems where IPv6 routes are unavailable.
// undici's happy eyeballs immediately rejects on ENETUNREACH (IPv6) without waiting for IPv4.
const _lookup = dns.lookup.bind(dns);
(dns as any).lookup = (
  hostname: string,
  options: any,
  callback: (...args: any[]) => void,
) => {
  if (typeof options === 'function') {
    callback = options;
    options = {};
  }
  return _lookup(hostname, { ...options, family: 4 }, callback);
};

import {
  ASSISTANT_NAME,
  CREDENTIAL_PROXY_PORT,
  IDLE_TIMEOUT,
  POLL_INTERVAL,
  TIMEZONE,
  TRIGGER_PATTERN,
} from './config.js';
import { startCredentialProxy } from './credential-proxy.js';
import './channels/index.js';
import {
  getChannelFactory,
  getRegisteredChannelNames,
} from './channels/registry.js';
import {
  ContainerOutput,
  runContainerAgent,
  writeGroupsSnapshot,
  writeTasksSnapshot,
} from './container-runner.js';
import {
  cleanupOrphans,
  ensureContainerRuntimeRunning,
  PROXY_BIND_HOST,
} from './container-runtime.js';
import {
  getAllChats,
  getAllRegisteredGroups,
  getAllSessions,
  getAllTasks,
  getMessagesSince,
  getNewMessages,
  getRegisteredGroup,
  getRouterState,
  initDatabase,
  recordTokenUsage,
  setRegisteredGroup,
  setRouterState,
  setSession,
  storeChatMetadata,
  storeMessage,
} from './db.js';
import { GroupQueue } from './group-queue.js';
import { resolveGroupFolderPath } from './group-folder.js';
import { startIpcWatcher } from './ipc.js';
import { findChannel, formatMessages, formatOutbound } from './router.js';
import { readEnvFile } from './env.js';
import {
  type DirectProviderResult,
  executeDirectProviderRequest,
  parseDirectProviderRequest,
} from './direct-provider.js';
import { fallbackToGeminiApi } from './gemini-fallback.js';
import { fallbackToOpenAI } from './openai-fallback.js';
import { fallbackToTrustedSource } from './trusted-source-fallback.js';
import {
  restoreRemoteControl,
  startRemoteControl,
  stopRemoteControl,
} from './remote-control.js';
import {
  isSenderAllowed,
  isTriggerAllowed,
  loadSenderAllowlist,
  shouldDropMessage,
} from './sender-allowlist.js';
import { startSchedulerLoop } from './task-scheduler.js';
import { Channel, NewMessage, RegisteredGroup } from './types.js';
import { logger } from './logger.js';

// Re-export for backwards compatibility during refactor
export { escapeXml, formatMessages } from './router.js';

let lastTimestamp = '';
let sessions: Record<string, string> = {};
let registeredGroups: Record<string, RegisteredGroup> = {};
let lastAgentTimestamp: Record<string, string> = {};
let messageLoopRunning = false;

const channels: Channel[] = [];
const queue = new GroupQueue();

function loadState(): void {
  lastTimestamp = getRouterState('last_timestamp') || '';
  const agentTs = getRouterState('last_agent_timestamp');
  try {
    lastAgentTimestamp = agentTs ? JSON.parse(agentTs) : {};
  } catch {
    logger.warn('Corrupted last_agent_timestamp in DB, resetting');
    lastAgentTimestamp = {};
  }
  sessions = getAllSessions();
  registeredGroups = getAllRegisteredGroups();
  logger.info(
    { groupCount: Object.keys(registeredGroups).length },
    'State loaded',
  );
}

function saveState(): void {
  setRouterState('last_timestamp', lastTimestamp);
  setRouterState('last_agent_timestamp', JSON.stringify(lastAgentTimestamp));
}

function registerGroup(jid: string, group: RegisteredGroup): void {
  let groupDir: string;
  try {
    groupDir = resolveGroupFolderPath(group.folder);
  } catch (err) {
    logger.warn(
      { jid, folder: group.folder, err },
      'Rejecting group registration with invalid folder',
    );
    return;
  }

  registeredGroups[jid] = group;
  setRegisteredGroup(jid, group);

  // Create group folder
  fs.mkdirSync(path.join(groupDir, 'logs'), { recursive: true });

  logger.info(
    { jid, name: group.name, folder: group.folder },
    'Group registered',
  );
}

/**
 * Get available groups list for the agent.
 * Returns groups ordered by most recent activity.
 */
export function getAvailableGroups(): import('./container-runner.js').AvailableGroup[] {
  const chats = getAllChats();
  const registeredJids = new Set(Object.keys(registeredGroups));

  return chats
    .filter((c) => c.jid !== '__group_sync__' && c.is_group)
    .map((c) => ({
      jid: c.jid,
      name: c.name,
      lastActivity: c.last_message_time,
      isRegistered: registeredJids.has(c.jid),
    }));
}

/** @internal - exported for testing */
export function _setRegisteredGroups(
  groups: Record<string, RegisteredGroup>,
): void {
  registeredGroups = groups;
}

/**
 * Process all pending messages for a group.
 * Called by the GroupQueue when it's this group's turn.
 */
interface FallbackResult {
  text: string;
  model: string;
}


async function fallbackToGemini(
  prompt: string,
): Promise<FallbackResult | null> {
  try {
    const envVars = readEnvFile(['GOOGLE_GEMINI_API_KEY']);
    const geminiKey =
      process.env.GOOGLE_GEMINI_API_KEY || envVars.GOOGLE_GEMINI_API_KEY;
    if (!geminiKey) return null;

    const { result, error } = await fallbackToGeminiApi(prompt, geminiKey);
    if (!result) {
      if (error) {
        logger.warn(
          {
            status: error.status,
            code: error.code,
            message: error.message,
          },
          'Gemini fallback API error',
        );
      } else {
        logger.warn('Gemini fallback API error');
      }
      return null;
    }
    return result;
  } catch (err) {
    logger.warn({ err }, 'Gemini fallback failed');
    return null;
  }
}

async function fallbackToChatGPT(
  prompt: string,
): Promise<FallbackResult | null> {
  try {
    const envVars = readEnvFile(['OPENAI_API_KEY']);
    const openaiKey = process.env.OPENAI_API_KEY || envVars.OPENAI_API_KEY;
    if (!openaiKey) return null;

    const { result, error } = await fallbackToOpenAI(prompt, openaiKey);
    if (!result) {
      if (error) {
        logger.warn(
          {
            status: error.status,
            code: error.code,
            message: error.message,
          },
          'ChatGPT fallback API error',
        );
      } else {
        logger.warn('ChatGPT fallback API error');
      }
      return null;
    }
    return result;
  } catch (err) {
    logger.warn({ err }, 'ChatGPT fallback failed');
    return null;
  }
}

function formatProviderError(message: string, code?: string | number): string {
  return code ? `${message} (${code})` : message;
}

function stripInternalText(raw: string): string {
  return raw.replace(/<internal>[\s\S]*?<\/internal>/g, '').trim();
}

// Note: Claude runs through the full agent path (system prompt, workspace mounts,
// conversation history) while OpenAI and Gemini receive the bare user prompt.
// This is intentional — the command tests provider routing, not response parity.
async function runClaudeDirectProviderTest(
  group: RegisteredGroup,
  prompt: string,
  chatJid: string,
): Promise<DirectProviderResult> {
  const outputs: string[] = [];
  let lastError = '';

  const status = await runAgent(group, prompt, chatJid, async (result) => {
    if (result.error) {
      lastError = result.error;
    }
    if (!result.result) return;

    const raw =
      typeof result.result === 'string'
        ? result.result
        : JSON.stringify(result.result);
    const text = stripInternalText(raw);
    if (text) outputs.push(text);
  });

  const text = outputs.join('\n\n').trim();
  if (status === 'success' && text) {
    return {
      ok: true,
      provider: 'claude',
      model: 'Claude',
      text,
    };
  }

  return {
    ok: false,
    provider: 'claude',
    model: 'Claude',
    error: extractApiErrorMessage(text || lastError || 'Claude request failed.'),
  };
}

async function runOpenAIDirectProviderTest(
  prompt: string,
): Promise<DirectProviderResult> {
  try {
    const envVars = readEnvFile(['OPENAI_API_KEY']);
    const openaiKey = process.env.OPENAI_API_KEY || envVars.OPENAI_API_KEY;
    if (!openaiKey) {
      return {
        ok: false,
        provider: 'openai',
        model: 'OpenAI',
        error: 'OPENAI_API_KEY is not configured.',
      };
    }

    const { result, error } = await fallbackToOpenAI(prompt, openaiKey);
    if (!result) {
      return {
        ok: false,
        provider: 'openai',
        model: 'OpenAI',
        error: error
          ? formatProviderError(error.message, error.code)
          : 'OpenAI request failed.',
      };
    }

    return {
      ok: true,
      provider: 'openai',
      model: result.model,
      text: result.text,
    };
  } catch (err) {
    return {
      ok: false,
      provider: 'openai',
      model: 'OpenAI',
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

async function runGeminiDirectProviderTest(
  prompt: string,
): Promise<DirectProviderResult> {
  try {
    const envVars = readEnvFile(['GOOGLE_GEMINI_API_KEY']);
    const geminiKey =
      process.env.GOOGLE_GEMINI_API_KEY || envVars.GOOGLE_GEMINI_API_KEY;
    if (!geminiKey) {
      return {
        ok: false,
        provider: 'gemini',
        model: 'Gemini',
        error: 'GOOGLE_GEMINI_API_KEY is not configured.',
      };
    }

    const { result, error } = await fallbackToGeminiApi(prompt, geminiKey);
    if (!result) {
      return {
        ok: false,
        provider: 'gemini',
        model: 'Gemini',
        error: error
          ? formatProviderError(error.message, error.code)
          : 'Gemini request failed.',
      };
    }

    return {
      ok: true,
      provider: 'gemini',
      model: result.model,
      text: result.text,
    };
  } catch (err) {
    return {
      ok: false,
      provider: 'gemini',
      model: 'Gemini',
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/** Try OpenAI then Gemini in order. Returns the first that succeeds. */
async function tryFallback(prompt: string): Promise<FallbackResult | null> {
  return (
    (await fallbackToTrustedSource(prompt)) ??
    (await fallbackToChatGPT(prompt)) ??
    (await fallbackToGemini(prompt))
  );
}

/**
 * Extract a human-readable error message from a Claude SDK error string.
 * The SDK embeds JSON like: `... {"type":"error","error":{"message":"..."}}`
 */
function extractApiErrorMessage(raw: string): string {
  try {
    const jsonStart = raw.indexOf('{');
    if (jsonStart !== -1) {
      const parsed = JSON.parse(raw.slice(jsonStart));
      if (typeof parsed?.error?.message === 'string') {
        return parsed.error.message;
      }
    }
  } catch {
    /* ignore */
  }
  // Fall back to first line, capped at 150 chars
  const first = raw.split('\n')[0].trim();
  return first.length <= 150 ? first : `${first.slice(0, 150)}...`;
}

async function processGroupMessages(chatJid: string): Promise<boolean> {
  const group = registeredGroups[chatJid];
  if (!group) return true;

  const channel = findChannel(channels, chatJid);
  if (!channel) {
    logger.warn({ chatJid }, 'No channel owns JID, skipping messages');
    return true;
  }

  const isMainGroup = group.isMain === true;

  const sinceTimestamp = lastAgentTimestamp[chatJid] || '';
  const missedMessages = getMessagesSince(
    chatJid,
    sinceTimestamp,
    ASSISTANT_NAME,
  );

  if (missedMessages.length === 0) return true;

  // For non-main groups, check if trigger is required and present
  if (!isMainGroup && group.requiresTrigger !== false) {
    const allowlistCfg = loadSenderAllowlist();
    const hasTrigger = missedMessages.some(
      (m) =>
        TRIGGER_PATTERN.test(m.content.trim()) &&
        (m.is_from_me || isTriggerAllowed(chatJid, m.sender, allowlistCfg)),
    );
    if (!hasTrigger) return true;
  }

  const latestMessage = missedMessages[missedMessages.length - 1];
  const directProviderRequest = latestMessage
    ? parseDirectProviderRequest(latestMessage.content, ASSISTANT_NAME)
    : null;

  const prompt = formatMessages(missedMessages, TIMEZONE);

  // Advance cursor so the piping path in startMessageLoop won't re-fetch
  // these messages. Save the old cursor so we can roll back on error.
  const previousCursor = lastAgentTimestamp[chatJid] || '';
  lastAgentTimestamp[chatJid] =
    missedMessages[missedMessages.length - 1].timestamp;
  saveState();

  logger.info(
    { group: group.name, messageCount: missedMessages.length },
    'Processing messages',
  );

  if (directProviderRequest) {
    await channel.setTyping?.(chatJid, true);
    await channel.sendMessage(chatJid, 'Got it, on it...');

    const result = await executeDirectProviderRequest(directProviderRequest, {
      runClaude: (providerPrompt) =>
        runClaudeDirectProviderTest(group, providerPrompt, chatJid),
      runOpenAI: runOpenAIDirectProviderTest,
      runGemini: runGeminiDirectProviderTest,
    });

    await channel.setTyping?.(chatJid, false);
    if (result.ok) {
      await channel.sendMessage(
        chatJid,
        `_(Direct provider test via ${result.model})_\n\n${result.text}`,
      );
    } else {
      await channel.sendMessage(
        chatJid,
        `_(Direct provider test failed: ${result.model})_\n\n${result.error}`,
      );
    }
    return true;
  }

  // Track idle timer for closing stdin when agent is idle
  let idleTimer: ReturnType<typeof setTimeout> | null = null;

  const resetIdleTimer = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      logger.debug(
        { group: group.name },
        'Idle timeout, closing container stdin',
      );
      queue.closeStdin(chatJid);
    }, IDLE_TIMEOUT);
  };

  await channel.setTyping?.(chatJid, true);
  await channel.sendMessage(chatJid, 'Got it, on it...');
  let hadError = false;
  let outputSentToUser = false;
  let usageLimitHit = false;
  let apiErrorHit = false;
  let apiErrorMessage = '';

  // Patterns that indicate Claude's usage cap was hit — intercept and failover
  const USAGE_LIMIT_PATTERNS = [
    /you're out of extra usage/i,
    /out of extra usage/i,
    /usage.*resets/i,
    /claude\.ai\/upgrade/i,
    /you've hit your limit/i,
    /hit your limit/i,
    /you.?ve hit/i,
    // NOTE: do NOT add broad patterns like /limit/i or /resets/i here —
    // they match normal responses and cause false-positive failovers.
  ];

  // Patterns that indicate a Claude API-level failure (auth, server error, etc.)
  // These are returned as result text by the SDK rather than thrown as exceptions.
  const API_ERROR_PATTERNS = [
    /failed to authenticate/i,
    /authentication_error/i,
    /invalid bearer token/i,
    /invalid api key/i,
    /api error.*40[13]/i,
    /api error.*5\d\d/i,
    /overloaded_error/i,
  ];

  const output = await runAgent(group, prompt, chatJid, async (result) => {
    // Streaming output callback — called for each agent result
    if (result.result) {
      const raw =
        typeof result.result === 'string'
          ? result.result
          : JSON.stringify(result.result);
      // Strip <internal>...</internal> blocks — agent uses these for internal reasoning
      const text = raw.replace(/<internal>[\s\S]*?<\/internal>/g, '').trim();
      logger.info({ group: group.name }, `Agent output: ${raw.slice(0, 200)}`);
      logger.info(
        { group: group.name, text },
        `Processed text: ${text.slice(0, 200)}`,
      );

      // Intercept usage-limit messages — don't forward to user, flag for failover
      const matches = USAGE_LIMIT_PATTERNS.some((p) => p.test(text));
      logger.info(
        { group: group.name, text, matches },
        `Checking patterns for text`,
      );
      if (text && matches) {
        logger.warn(
          { group: group.name, text },
          'Claude usage limit hit, flagging for failover',
        );
        usageLimitHit = true;
        // Stop the container immediately so it doesn't consume more IPC
        // messages and produce a cascade of identical "hit your limit" results.
        queue.closeStdin(chatJid);
        return;
      }

      // Intercept API error messages — don't forward raw SDK error to user
      if (text && API_ERROR_PATTERNS.some((p) => p.test(text))) {
        logger.warn(
          { group: group.name, text },
          'Claude API error detected, flagging for failover',
        );
        apiErrorHit = true;
        apiErrorMessage = text;
        queue.closeStdin(chatJid);
        return;
      }

      if (text) {
        await channel.sendMessage(chatJid, text);
        outputSentToUser = true;
      }
      // Only reset idle timer on actual results, not session-update markers (result: null)
      resetIdleTimer();
    }

    if (result.status === 'success') {
      queue.notifyIdle(chatJid);
    }

    if (result.status === 'error') {
      hadError = true;
    }
  });

  await channel.setTyping?.(chatJid, false);
  if (idleTimer) clearTimeout(idleTimer);

  if (usageLimitHit && !outputSentToUser) {
    logger.warn(
      { group: group.name },
      'Claude usage limit hit, attempting fallback',
    );
    const fallback = await tryFallback(prompt);
    if (fallback) {
      logger.info(
        { group: group.name, model: fallback.model },
        'Fallback succeeded after usage limit',
      );
      await channel.sendMessage(
        chatJid,
        `_(Claude usage limit reached. Failed over to ${fallback.model})_\n\n${fallback.text}`,
      );
      return true;
    }
    await channel.sendMessage(
      chatJid,
      "Claude's usage limit has been reached and all fallback services failed. Please try again later.",
    );
    return true;
  }

  if (apiErrorHit && !outputSentToUser) {
    const cleanError = extractApiErrorMessage(apiErrorMessage);
    logger.warn(
      { group: group.name, cleanError },
      'Claude API error, attempting fallback',
    );
    const fallback = await tryFallback(prompt);
    if (fallback) {
      logger.info(
        { group: group.name, model: fallback.model },
        'Fallback succeeded after API error',
      );
      await channel.sendMessage(
        chatJid,
        `The Claude API has failed with: ${cleanError}\n\nFailed over to ${fallback.model} and the response is below.\n\n${fallback.text}`,
      );
      return true;
    }
    await channel.sendMessage(
      chatJid,
      `The Claude API has failed with: ${cleanError}\n\nAll fallback services also failed. Please try again later.`,
    );
    return true;
  }

  if (output === 'error' || hadError) {
    // If we already sent output to the user, don't roll back the cursor —
    // the user got their response and re-processing would send duplicates.
    if (outputSentToUser) {
      logger.warn(
        { group: group.name },
        'Agent error after output was sent, skipping cursor rollback to prevent duplicates',
      );
      return true;
    }

    // Claude is down — attempt fallback before giving up
    logger.warn(
      { group: group.name },
      'Claude agent failed, attempting fallback',
    );
    const fallback = await tryFallback(prompt);
    if (fallback) {
      logger.info(
        { group: group.name, model: fallback.model },
        'Fallback succeeded',
      );
      await channel.sendMessage(
        chatJid,
        `_(Claude is unavailable. Failed over to ${fallback.model})_\n\n${fallback.text}`,
      );
      return true;
    }

    // Roll back cursor so retries can re-process these messages
    lastAgentTimestamp[chatJid] = previousCursor;
    saveState();
    logger.warn(
      { group: group.name },
      'Agent error, rolled back message cursor for retry',
    );
    return false;
  }

  return true;
}

async function runAgent(
  group: RegisteredGroup,
  prompt: string,
  chatJid: string,
  onOutput?: (output: ContainerOutput) => Promise<void>,
): Promise<'success' | 'error'> {
  const isMain = group.isMain === true;
  const sessionId = sessions[group.folder];

  // Update tasks snapshot for container to read (filtered by group)
  const tasks = getAllTasks();
  writeTasksSnapshot(
    group.folder,
    isMain,
    tasks.map((t) => ({
      id: t.id,
      groupFolder: t.group_folder,
      prompt: t.prompt,
      schedule_type: t.schedule_type,
      schedule_value: t.schedule_value,
      status: t.status,
      next_run: t.next_run,
    })),
  );

  // Update available groups snapshot (main group only can see all groups)
  const availableGroups = getAvailableGroups();
  writeGroupsSnapshot(
    group.folder,
    isMain,
    availableGroups,
    new Set(Object.keys(registeredGroups)),
  );

  // Wrap onOutput to track session ID from streamed results
  const wrappedOnOutput = onOutput
    ? async (output: ContainerOutput) => {
        if (output.newSessionId) {
          sessions[group.folder] = output.newSessionId;
          setSession(group.folder, output.newSessionId);
        }
        await onOutput(output);
      }
    : undefined;

  try {
    const output = await runContainerAgent(
      group,
      {
        prompt,
        sessionId,
        groupFolder: group.folder,
        chatJid,
        isMain,
        assistantName: ASSISTANT_NAME,
      },
      (proc, containerName) =>
        queue.registerProcess(chatJid, proc, containerName, group.folder),
      wrappedOnOutput,
    );

    if (output.newSessionId) {
      sessions[group.folder] = output.newSessionId;
      setSession(group.folder, output.newSessionId);
    }

    if (output.status === 'error') {
      logger.error(
        { group: group.name, error: output.error },
        'Container agent error',
      );
      return 'error';
    }

    return 'success';
  } catch (err) {
    logger.error({ group: group.name, err }, 'Agent error');
    return 'error';
  }
}

async function startMessageLoop(): Promise<void> {
  if (messageLoopRunning) {
    logger.debug('Message loop already running, skipping duplicate start');
    return;
  }
  messageLoopRunning = true;

  logger.info(`NanoClaw running (trigger: @${ASSISTANT_NAME})`);

  while (true) {
    try {
      const jids = Object.keys(registeredGroups);
      const { messages, newTimestamp } = getNewMessages(
        jids,
        lastTimestamp,
        ASSISTANT_NAME,
      );

      if (messages.length > 0) {
        logger.info({ count: messages.length }, 'New messages');

        // Advance the "seen" cursor for all messages immediately
        lastTimestamp = newTimestamp;
        saveState();

        // Deduplicate by group
        const messagesByGroup = new Map<string, NewMessage[]>();
        for (const msg of messages) {
          const existing = messagesByGroup.get(msg.chat_jid);
          if (existing) {
            existing.push(msg);
          } else {
            messagesByGroup.set(msg.chat_jid, [msg]);
          }
        }

        for (const [chatJid, groupMessages] of messagesByGroup) {
          const group = registeredGroups[chatJid];
          if (!group) continue;

          const channel = findChannel(channels, chatJid);
          if (!channel) {
            logger.warn({ chatJid }, 'No channel owns JID, skipping messages');
            continue;
          }

          const isMainGroup = group.isMain === true;
          const needsTrigger = !isMainGroup && group.requiresTrigger !== false;

          // For non-main groups, only act on trigger messages.
          // Non-trigger messages accumulate in DB and get pulled as
          // context when a trigger eventually arrives.
          if (needsTrigger) {
            const allowlistCfg = loadSenderAllowlist();
            const hasTrigger = groupMessages.some(
              (m) =>
                TRIGGER_PATTERN.test(m.content.trim()) &&
                (m.is_from_me ||
                  isTriggerAllowed(chatJid, m.sender, allowlistCfg)),
            );
            if (!hasTrigger) continue;
          }

          // Pull all messages since lastAgentTimestamp so non-trigger
          // context that accumulated between triggers is included.
          const allPending = getMessagesSince(
            chatJid,
            lastAgentTimestamp[chatJid] || '',
            ASSISTANT_NAME,
          );
          const messagesToSend =
            allPending.length > 0 ? allPending : groupMessages;
          const formatted = formatMessages(messagesToSend, TIMEZONE);

          if (queue.sendMessage(chatJid, formatted)) {
            logger.debug(
              { chatJid, count: messagesToSend.length },
              'Piped messages to active container',
            );
            lastAgentTimestamp[chatJid] =
              messagesToSend[messagesToSend.length - 1].timestamp;
            saveState();
            // Show typing indicator while the container processes the piped message
            channel
              .setTyping?.(chatJid, true)
              ?.catch((err) =>
                logger.warn({ chatJid, err }, 'Failed to set typing indicator'),
              );
          } else {
            // No active container — enqueue for a new one
            queue.enqueueMessageCheck(chatJid);
          }
        }
      }
    } catch (err) {
      logger.error({ err }, 'Error in message loop');
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL));
  }
}

/**
 * Startup recovery: check for unprocessed messages in registered groups.
 * Handles crash between advancing lastTimestamp and processing messages.
 */
function recoverPendingMessages(): void {
  for (const [chatJid, group] of Object.entries(registeredGroups)) {
    const sinceTimestamp = lastAgentTimestamp[chatJid] || '';
    const pending = getMessagesSince(chatJid, sinceTimestamp, ASSISTANT_NAME);
    if (pending.length > 0) {
      logger.info(
        { group: group.name, pendingCount: pending.length },
        'Recovery: found unprocessed messages',
      );
      queue.enqueueMessageCheck(chatJid);
    }
  }
}

function ensureContainerSystemRunning(): void {
  ensureContainerRuntimeRunning();
  cleanupOrphans();
}

async function main(): Promise<void> {
  ensureContainerSystemRunning();
  initDatabase();
  logger.info('Database initialized');
  loadState();
  restoreRemoteControl();

  // Start credential proxy (containers route API calls through this)
  const proxyServer = await startCredentialProxy(
    CREDENTIAL_PROXY_PORT,
    PROXY_BIND_HOST,
    (usage) =>
      recordTokenUsage(
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_creation_tokens,
        usage.cache_read_tokens,
      ),
  );

  // Graceful shutdown handlers
  const shutdown = async (signal: string) => {
    logger.info({ signal }, 'Shutdown signal received');
    proxyServer.close();
    await queue.shutdown(10000);
    for (const ch of channels) await ch.disconnect();
    process.exit(0);
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  // Handle /remote-control and /remote-control-end commands
  async function handleRemoteControl(
    command: string,
    chatJid: string,
    msg: NewMessage,
  ): Promise<void> {
    const group = registeredGroups[chatJid];
    if (!group?.isMain) {
      logger.warn(
        { chatJid, sender: msg.sender },
        'Remote control rejected: not main group',
      );
      return;
    }

    const channel = findChannel(channels, chatJid);
    if (!channel) return;

    if (command === '/remote-control') {
      const result = await startRemoteControl(
        msg.sender,
        chatJid,
        process.cwd(),
      );
      if (result.ok) {
        await channel.sendMessage(chatJid, result.url);
      } else {
        await channel.sendMessage(
          chatJid,
          `Remote Control failed: ${result.error}`,
        );
      }
    } else {
      const result = stopRemoteControl();
      if (result.ok) {
        await channel.sendMessage(chatJid, 'Remote Control session ended.');
      } else {
        await channel.sendMessage(chatJid, result.error);
      }
    }
  }

  // Channel callbacks (shared by all channels)
  const channelOpts = {
    onMessage: (chatJid: string, msg: NewMessage) => {
      // Remote control commands — intercept before storage
      const trimmed = msg.content.trim();
      if (trimmed === '/remote-control' || trimmed === '/remote-control-end') {
        handleRemoteControl(trimmed, chatJid, msg).catch((err) =>
          logger.error({ err, chatJid }, 'Remote control command error'),
        );
        return;
      }

      // Sender allowlist drop mode: discard messages from denied senders before storing
      if (!msg.is_from_me && !msg.is_bot_message && registeredGroups[chatJid]) {
        const cfg = loadSenderAllowlist();
        if (
          shouldDropMessage(chatJid, cfg) &&
          !isSenderAllowed(chatJid, msg.sender, cfg)
        ) {
          if (cfg.logDenied) {
            logger.debug(
              { chatJid, sender: msg.sender },
              'sender-allowlist: dropping message (drop mode)',
            );
          }
          return;
        }
      }
      storeMessage(msg);
    },
    onChatMetadata: (
      chatJid: string,
      timestamp: string,
      name?: string,
      channel?: string,
      isGroup?: boolean,
    ) => storeChatMetadata(chatJid, timestamp, name, channel, isGroup),
    registeredGroups: () => registeredGroups,
  };

  // Create and connect all registered channels.
  // Each channel self-registers via the barrel import above.
  // Factories return null when credentials are missing, so unconfigured channels are skipped.
  for (const channelName of getRegisteredChannelNames()) {
    const factory = getChannelFactory(channelName)!;
    const channel = factory(channelOpts);
    if (!channel) {
      logger.warn(
        { channel: channelName },
        'Channel installed but credentials missing — skipping. Check .env or re-run the channel skill.',
      );
      continue;
    }
    channels.push(channel);
    await channel.connect();
  }
  if (channels.length === 0) {
    logger.fatal('No channels connected');
    process.exit(1);
  }

  // Start subsystems (independently of connection handler)
  startSchedulerLoop({
    registeredGroups: () => registeredGroups,
    getSessions: () => sessions,
    queue,
    onProcess: (groupJid, proc, containerName, groupFolder) =>
      queue.registerProcess(groupJid, proc, containerName, groupFolder),
    sendMessage: async (jid, rawText) => {
      const channel = findChannel(channels, jid);
      if (!channel) {
        logger.warn({ jid }, 'No channel owns JID, cannot send message');
        return;
      }
      const text = formatOutbound(rawText);
      if (text) await channel.sendMessage(jid, text);
    },
  });
  startIpcWatcher({
    sendMessage: (jid, text) => {
      const channel = findChannel(channels, jid);
      if (!channel) throw new Error(`No channel for JID: ${jid}`);
      return channel.sendMessage(jid, text);
    },
    registeredGroups: () => registeredGroups,
    registerGroup,
    syncGroups: async (force: boolean) => {
      await Promise.all(
        channels
          .filter((ch) => ch.syncGroups)
          .map((ch) => ch.syncGroups!(force)),
      );
    },
    getAvailableGroups,
    writeGroupsSnapshot: (gf, im, ag, rj) =>
      writeGroupsSnapshot(gf, im, ag, rj),
    onTasksChanged: () => {
      const tasks = getAllTasks();
      const taskRows = tasks.map((t) => ({
        id: t.id,
        groupFolder: t.group_folder,
        prompt: t.prompt,
        schedule_type: t.schedule_type,
        schedule_value: t.schedule_value,
        status: t.status,
        next_run: t.next_run,
      }));
      for (const group of Object.values(registeredGroups)) {
        writeTasksSnapshot(group.folder, group.isMain === true, taskRows);
      }
    },
  });
  queue.setProcessMessagesFn(processGroupMessages);
  recoverPendingMessages();
  startMessageLoop().catch((err) => {
    logger.fatal({ err }, 'Message loop crashed unexpectedly');
    process.exit(1);
  });
}

// Guard: only run when executed directly, not when imported by tests
const isDirectRun =
  process.argv[1] &&
  new URL(import.meta.url).pathname ===
    new URL(`file://${process.argv[1]}`).pathname;

if (isDirectRun) {
  // Global safety net: catch any error that escapes explicit try/catch blocks.
  // Without these, Node.js 15+ exits silently on unhandled rejections, leaving
  // an empty stderr log with no crash cause recorded.
  process.on('uncaughtException', (err) => {
    logger.fatal({ err }, 'Uncaught exception — process exiting');
    process.exit(1);
  });
  process.on('unhandledRejection', (reason) => {
    logger.fatal({ reason }, 'Unhandled promise rejection — process exiting');
    process.exit(1);
  });

  main().catch((err) => {
    logger.error({ err }, 'Failed to start NanoClaw');
    process.exit(1);
  });
}
