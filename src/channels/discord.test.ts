import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

// --- Mocks ---

// Mock registry (registerChannel runs at import time)
vi.mock('./registry.js', () => ({ registerChannel: vi.fn() }));

// Mock env reader (used by the factory, not needed in unit tests)
vi.mock('../env.js', () => ({ readEnvFile: vi.fn(() => ({})) }));

// Mock config
vi.mock('../config.js', () => ({
  ASSISTANT_NAME: 'Andy',
  TRIGGER_PATTERN: /^@Andy\b/i,
  GROUPS_DIR: '/tmp/test-groups',
}));

// Mock logger
vi.mock('../logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

// --- Discord.js mock ---

type Handler = (...args: any[]) => any;

const clientRef = vi.hoisted(() => ({ current: null as any }));

// Store mock channel classes for test access
const channelClassesRef = vi.hoisted(() => ({
  MockTextChannel: null as any,
  MockThreadChannel: null as any,
  MockDMChannel: null as any,
}));

vi.mock('discord.js', () => {
  // Create a shared mock channel instance that tests can access
  let mockChannelInstance: any = null;

  class MockTextChannel {
    id = '123456789012345678';
    name = 'test-channel';
    send = vi.fn().mockResolvedValue(undefined);
    sendTyping = vi.fn().mockResolvedValue(undefined);
  }

  class MockThreadChannel {
    id = '123456789012345678';
    name = 'test-thread';
    send = vi.fn().mockResolvedValue(undefined);
    sendTyping = vi.fn().mockResolvedValue(undefined);
  }

  class MockDMChannel {
    id = '123456789012345678';
    send = vi.fn().mockResolvedValue(undefined);
    sendTyping = vi.fn().mockResolvedValue(undefined);
  }

  // Store references for tests to use
  channelClassesRef.MockTextChannel = MockTextChannel;
  channelClassesRef.MockThreadChannel = MockThreadChannel;
  channelClassesRef.MockDMChannel = MockDMChannel;

  class MockClient {
    intents: any[];
    partials: any[];
    eventHandlers = new Map<string, Handler[]>();
    onceHandlers = new Map<string, Handler[]>();
    isReady = false;

    user = {
      id: '987654321098765432',
      tag: 'TestBot#1234',
      username: 'TestBot',
      displayName: 'TestBot',
    };

    guilds = {
      cache: new Map(),
    };

    channels = {
      fetch: vi.fn().mockImplementation(async () => {
        // Return the same mock channel instance so tests can verify calls
        if (!mockChannelInstance) {
          mockChannelInstance = new MockTextChannel();
        }
        return mockChannelInstance;
      }),
    };

    constructor(opts: { intents: any[]; partials: any[] }) {
      this.intents = opts.intents;
      this.partials = opts.partials;
      clientRef.current = this;
    }

    on(event: string, handler: Handler) {
      const existing = this.eventHandlers.get(event) || [];
      existing.push(handler);
      this.eventHandlers.set(event, existing);
    }

    once(event: string, handler: Handler) {
      const existing = this.onceHandlers.get(event) || [];
      existing.push(handler);
      this.onceHandlers.set(event, existing);
    }

    async login(_token: string) {
      this.isReady = true;
      // Trigger ClientReady handlers
      const handlers = this.onceHandlers.get('ready') || [];
      for (const h of handlers) {
        await h(this);
      }
    }

    destroy() {
      this.isReady = false;
    }
  }

  return {
    Client: MockClient,
    TextChannel: MockTextChannel,
    ThreadChannel: MockThreadChannel,
    DMChannel: MockDMChannel,
    GatewayIntentBits: {
      Guilds: 'Guilds',
      GuildMessages: 'GuildMessages',
      MessageContent: 'MessageContent',
      DirectMessages: 'DirectMessages',
      GuildVoiceStates: 'GuildVoiceStates',
      DirectMessageTyping: 'DirectMessageTyping',
    },
    Partials: {
      Channel: 'Channel',
      Message: 'Message',
    },
    Events: {
      ClientReady: 'ready',
      InteractionCreate: 'interactionCreate',
      MessageCreate: 'messageCreate',
      Error: 'error',
      TypingStart: 'typingStart',
    },
    SlashCommandBuilder: class {
      name = '';
      description = '';
      setName(n: string) {
        this.name = n;
        return this;
      }
      setDescription(d: string) {
        this.description = d;
        return this;
      }
      toJSON() {
        return { name: this.name, description: this.description };
      }
    },
    PermissionFlagsBits: {},
    REST: class {
      setToken() {
        return this;
      }
      put() {
        return Promise.resolve([]);
      }
    },
    Routes: {
      applicationCommands: (id: string) => `/applications/${id}/commands`,
    },
  };
});

import { DiscordChannel, DiscordChannelOpts } from './discord.js';

// --- Test helpers ---

function createTestOpts(
  overrides?: Partial<DiscordChannelOpts>,
): DiscordChannelOpts {
  return {
    onMessage: vi.fn(),
    onChatMetadata: vi.fn(),
    registeredGroups: vi.fn(() => ({
      'dc:123456789012345678': {
        name: 'Test Channel',
        folder: 'test-group',
        trigger: '@Andy',
        added_at: '2024-01-01T00:00:00.000Z',
        requiresTrigger: false,
      },
    })),
    ...overrides,
  };
}

function createMessageMock(overrides: {
  channelId?: string;
  channelType?: 'text' | 'thread' | 'dm';
  content: string;
  authorId?: string;
  authorName?: string;
  authorDisplayName?: string;
  messageId?: string;
  mentions?: Set<string>;
  attachments?: Map<string, any>;
}) {
  const isDm = overrides.channelType === 'dm';

  // Create an actual instance of the mock channel class
  let channel: any;
  if (overrides.channelType === 'thread') {
    channel = new channelClassesRef.MockThreadChannel();
  } else if (isDm) {
    channel = new channelClassesRef.MockDMChannel();
  } else {
    channel = new channelClassesRef.MockTextChannel();
  }

  // Override properties
  channel.id = overrides.channelId ?? '123456789012345678';
  if (!isDm) {
    channel.name = 'test-channel';
  }

  const author: any = {
    id: overrides.authorId ?? '111222333444555666',
    username: overrides.authorName ?? 'testuser',
    bot: false,
  };

  // Set displayName: prefer authorDisplayName, fall back to authorName, then default
  if (overrides.authorDisplayName !== undefined) {
    author.displayName = overrides.authorDisplayName;
  } else if (overrides.authorName !== undefined) {
    // If authorName is provided but not displayName, use the authorName as displayName too
    author.displayName = overrides.authorName;
  } else {
    // Default displayName
    author.displayName = 'Test User';
  }

  return {
    author,
    content: overrides.content,
    id: overrides.messageId ?? '1000000000000000001',
    mentions: {
      users: {
        has: (id: string) => (overrides.mentions ?? new Set()).has(id),
      },
    },
    attachments: overrides.attachments ?? new Map(),
    createdAt: new Date('2024-01-01T00:00:00.000Z'),
    system: false,
    channel,
  };
}

function currentClient() {
  return clientRef.current;
}

async function triggerMessage(
  msg: ReturnType<typeof createMessageMock>,
) {
  const handlers = currentClient().eventHandlers.get('messageCreate') || [];
  for (const h of handlers) await h(msg);
}

// --- Tests ---

describe('DiscordChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // --- Connection lifecycle ---

  describe('connection lifecycle', () => {
    it('resolves connect() when client logs in', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);

      await channel.connect();

      expect(channel.isConnected()).toBe(true);
    });

    it('registers message and interaction handlers on connect', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);

      await channel.connect();

      expect(currentClient().eventHandlers.has('messageCreate')).toBe(true);
      expect(currentClient().eventHandlers.has('interactionCreate')).toBe(true);
      expect(currentClient().eventHandlers.has('error')).toBe(true);
    });

    it('disconnects cleanly', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);

      await channel.connect();
      expect(channel.isConnected()).toBe(true);

      await channel.disconnect();
      expect(channel.isConnected()).toBe(false);
    });

    it('isConnected() returns false before connect', () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);

      expect(channel.isConnected()).toBe(false);
    });
  });

  // --- Text message handling ---

  describe('text message handling', () => {
    it('delivers message for registered channel', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({ content: 'Hello everyone' });
      await triggerMessage(msg);

      expect(opts.onChatMetadata).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.any(String),
        'test-channel',
        'discord',
        true,
      );
      expect(opts.onMessage).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.objectContaining({
          id: '1000000000000000001',
          chat_jid: 'dc:123456789012345678',
          sender: '111222333444555666',
          sender_name: 'Test User',
          content: 'Hello everyone',
          is_from_me: false,
        }),
      );
    });

    it('only emits metadata for unregistered channels', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({
        channelId: '999999999999999999',
        content: 'Unknown channel',
      });
      await triggerMessage(msg);

      expect(opts.onChatMetadata).toHaveBeenCalledWith(
        'dc:999999999999999999',
        expect.any(String),
        'test-channel',
        'discord',
        true,
      );
      expect(opts.onMessage).not.toHaveBeenCalled();
    });

    it('skips bot messages', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({ content: 'I am a bot' });
      msg.author.bot = true;
      await triggerMessage(msg);

      expect(opts.onMessage).not.toHaveBeenCalled();
      expect(opts.onChatMetadata).not.toHaveBeenCalled();
    });

    it('extracts sender name from displayName', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({
        content: 'Hi',
        authorDisplayName: 'Bob',
      });
      await triggerMessage(msg);

      expect(opts.onMessage).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.objectContaining({ sender_name: 'Bob' }),
      );
    });

    it('falls back to username when displayName missing', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({
        content: 'Hi',
        authorDisplayName: undefined as any,
        authorName: 'bob_user',
      });
      await triggerMessage(msg);

      expect(opts.onMessage).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.objectContaining({ sender_name: 'bob_user' }),
      );
    });

    it('converts createdAt to ISO timestamp', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({ content: 'Hello' });
      await triggerMessage(msg);

      expect(opts.onMessage).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.objectContaining({
          timestamp: '2024-01-01T00:00:00.000Z',
        }),
      );
    });
  });

  // --- @mention translation ---

  describe('@mention translation', () => {
    it('detects bot mention as trigger', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({
        content: '<@987654321098765432> what time is it?',
        mentions: new Set(['987654321098765432']),
      });
      await triggerMessage(msg);

      expect(opts.onMessage).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.objectContaining({
          content: '<@987654321098765432> what time is it?',
        }),
      );
    });

    it('ignores messages without trigger when trigger required', async () => {
      const opts = createTestOpts({
        registeredGroups: vi.fn(() => ({
          'dc:123456789012345678': {
            name: 'Test Channel',
            folder: 'test-group',
            trigger: '@Andy',
            added_at: '2024-01-01T00:00:00.000Z',
            requiresTrigger: true,
          },
        })),
      });
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({
        content: 'hello there',
        mentions: new Set(),
      });
      await triggerMessage(msg);

      expect(opts.onMessage).not.toHaveBeenCalled();
    });

    it('passes messages with trigger pattern', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const msg = createMessageMock({
        content: '@Andy hello there',
        mentions: new Set(),
      });
      await triggerMessage(msg);

      expect(opts.onMessage).toHaveBeenCalledWith(
        'dc:123456789012345678',
        expect.objectContaining({
          content: '@Andy hello there',
        }),
      );
    });
  });

  // --- sendMessage ---

  describe('sendMessage', () => {
    it('sends message via channel API', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.sendMessage('dc:123456789012345678', 'Hello');

      const fetchedChannel = await currentClient().channels.fetch();
      expect(fetchedChannel.send).toHaveBeenCalledWith('Hello');
    });

    it('strips dc: prefix from JID', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.sendMessage('dc:123456789012345678', 'Group message');

      expect(currentClient().channels.fetch).toHaveBeenCalledWith(
        '123456789012345678',
      );
    });

    it('splits messages exceeding 2000 characters', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const longText = 'x'.repeat(3000);
      await channel.sendMessage('dc:123456789012345678', longText);

      const fetchedChannel = await currentClient().channels.fetch();
      expect(fetchedChannel.send).toHaveBeenCalledTimes(2);
      expect(fetchedChannel.send).toHaveBeenNthCalledWith(
        1,
        'x'.repeat(2000),
      );
      expect(fetchedChannel.send).toHaveBeenNthCalledWith(
        2,
        'x'.repeat(1000),
      );
    });

    it('sends exactly one message at 2000 characters', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      const exactText = 'y'.repeat(2000);
      await channel.sendMessage('dc:123456789012345678', exactText);

      const fetchedChannel = await currentClient().channels.fetch();
      expect(fetchedChannel.send).toHaveBeenCalledTimes(1);
    });

    it('handles send failure gracefully', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      currentClient().channels.fetch.mockResolvedValueOnce({
        send: vi.fn().mockRejectedValueOnce(new Error('Network error')),
      });

      // Should not throw
      await expect(
        channel.sendMessage('dc:123456789012345678', 'Will fail'),
      ).resolves.toBeUndefined();
    });

    it('does nothing when client is not initialized', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);

      // Don't connect — client is null
      await channel.sendMessage('dc:123456789012345678', 'No client');

      // No error, no API call
    });
  });

  // --- ownsJid ---

  describe('ownsJid', () => {
    it('owns dc: JIDs', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.ownsJid('dc:123456')).toBe(true);
    });

    it('owns dc:thread: JIDs', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.ownsJid('dc:thread:789012')).toBe(true);
    });

    it('owns dc:dm: JIDs', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.ownsJid('dc:dm:345678')).toBe(true);
    });

    it('does not own Telegram JIDs', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.ownsJid('tg:123456')).toBe(false);
    });

    it('does not own WhatsApp group JIDs', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.ownsJid('12345@g.us')).toBe(false);
    });

    it('does not own unknown JID formats', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.ownsJid('random-string')).toBe(false);
    });
  });

  // --- setTyping ---

  describe('setTyping', () => {
    it('sends typing action when isTyping is true', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.setTyping('dc:123456789012345678', true);

      const fetchedChannel = await currentClient().channels.fetch();
      expect(fetchedChannel.sendTyping).toHaveBeenCalled();
    });

    it('does nothing when isTyping is false', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.setTyping('dc:123456789012345678', false);

      expect(currentClient().channels.fetch).not.toHaveBeenCalled();
    });

    it('does nothing when client is not initialized', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);

      // Don't connect
      await channel.setTyping('dc:123456789012345678', true);

      // No error, no API call
    });

    it('handles typing indicator failure gracefully', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      currentClient().channels.fetch.mockResolvedValueOnce({
        sendTyping: vi.fn().mockRejectedValueOnce(new Error('Rate limited')),
      });

      await expect(
        channel.setTyping('dc:123456789012345678', true),
      ).resolves.toBeUndefined();
    });
  });

  // --- Channel properties ---

  describe('channel properties', () => {
    it('has name "discord"', () => {
      const channel = new DiscordChannel('test-token', createTestOpts());
      expect(channel.name).toBe('discord');
    });
  });

  // --- JID helpers (via ownsJid and sendMessage) ---

  describe('JID format handling', () => {
    it('extracts channel ID from dc: JID', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.sendMessage('dc:123456789012345678', 'test');

      expect(currentClient().channels.fetch).toHaveBeenCalledWith(
        '123456789012345678',
      );
    });

    it('extracts channel ID from dc:thread: JID', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.sendMessage('dc:thread:987654321098765432', 'test');

      expect(currentClient().channels.fetch).toHaveBeenCalledWith(
        '987654321098765432',
      );
    });

    it('extracts channel ID from dc:dm: JID', async () => {
      const opts = createTestOpts();
      const channel = new DiscordChannel('test-token', opts);
      await channel.connect();

      await channel.sendMessage('dc:dm:111222333444555666', 'test');

      expect(currentClient().channels.fetch).toHaveBeenCalledWith(
        '111222333444555666',
      );
    });
  });
});
