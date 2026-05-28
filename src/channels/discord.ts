import fs from 'fs';
import path from 'path';

import {
  Client,
  GatewayIntentBits,
  Partials,
  Events,
  Message,
  TextChannel,
  ThreadChannel,
  DMChannel,
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  PermissionFlagsBits,
  REST,
  Routes,
} from 'discord.js';

import { ASSISTANT_NAME, GROUPS_DIR, TRIGGER_PATTERN } from '../config.js';
import { readEnvFile } from '../env.js';
import { logger } from '../logger.js';
import { registerChannel, ChannelOpts } from './registry.js';
import {
  Channel,
  OnChatMetadata,
  OnInboundMessage,
  RegisteredGroup,
} from '../types.js';

export interface DiscordChannelOpts {
  onMessage: OnInboundMessage;
  onChatMetadata: OnChatMetadata;
  registeredGroups: () => Record<string, RegisteredGroup>;
}

const MAX_DISCORD_MESSAGE_LENGTH = 2000;

/**
 * Convert a Discord channel to a NanoClaw JID.
 */
function channelToJid(
  channel: TextChannel | ThreadChannel | DMChannel,
): string {
  if (channel instanceof DMChannel) {
    return `dc:dm:${channel.id}`;
  }
  if (channel instanceof ThreadChannel) {
    return `dc:thread:${channel.id}`;
  }
  return `dc:${channel.id}`;
}

/**
 * Extract the Discord channel ID from a JID.
 */
function jidToChannelId(jid: string): string {
  return jid.replace(/^dc:(thread:|dm:)?/, '');
}

/**
 * Transcribe an audio file using Google Gemini.
 * (Same pattern as Telegram's voice transcription)
 */
async function transcribeWithGemini(
  filePath: string,
  apiKey: string,
): Promise<string | null> {
  try {
    const fileBuffer = fs.readFileSync(filePath);
    const base64Audio = fileBuffer.toString('base64');
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mimeType =
      ext === 'ogg' ? 'audio/opus' : ext === 'mp3' ? 'audio/mpeg' : 'audio/wav';

    const body = {
      contents: [
        {
          parts: [
            {
              text: 'Transcribe this audio message exactly as spoken. Return only the transcription, no commentary.',
            },
            { inline_data: { mime_type: mimeType, data: base64Audio } },
          ],
        },
      ],
    };

    const res = await fetch(
      'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-goog-api-key': apiKey,
        },
        body: JSON.stringify(body),
      },
    );

    if (!res.ok) {
      const body = await res.text().catch(() => '(unreadable)');
      logger.warn(
        { status: res.status, body },
        'Gemini transcription API error',
      );
      return null;
    }

    const json = (await res.json()) as any;
    const text = (
      json?.candidates?.[0]?.content?.parts?.[0]?.text as string | undefined
    )?.trim();
    if (!text) {
      logger.warn(
        { json: JSON.stringify(json).slice(0, 300) },
        'Gemini transcription returned empty',
      );
    }
    return text || null;
  } catch (err) {
    logger.warn({ err }, 'transcribeWithGemini failed');
    return null;
  }
}

export class DiscordChannel implements Channel {
  name = 'discord';

  private client: Client<boolean> | null = null;
  private opts: DiscordChannelOpts;
  private botToken: string;
  private applicationId: string | null = null;

  constructor(botToken: string, opts: DiscordChannelOpts) {
    this.botToken = botToken;
    this.opts = opts;
  }

  async connect(): Promise<void> {
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages,
      ],
      partials: [Partials.Channel],
    });

    // Slash command definitions
    const chatIdCommand = new SlashCommandBuilder()
      .setName('chatid')
      .setDescription('Get the chat ID for NanoClaw registration')
      .toJSON();

    const pingCommand = new SlashCommandBuilder()
      .setName('ping')
      .setDescription('Check if the bot is online')
      .toJSON();

    const logMealCommand = new SlashCommandBuilder()
      .setName('log-meal')
      .setDescription('Log a meal to the nutrition tracker')
      .addStringOption((option) =>
        option
          .setName('category')
          .setDescription('Meal category')
          .setRequired(true)
          .addChoices(
            { name: 'Breakfast', value: 'breakfast' },
            { name: 'Lunch', value: 'lunch' },
            { name: 'Dinner', value: 'dinner' },
            { name: 'Snack', value: 'snack' },
          ),
      )
      .addStringOption((option) =>
        option
          .setName('description')
          .setDescription('What did you eat?')
          .setRequired(true),
      )
      .toJSON();

    const nutritionTodayCommand = new SlashCommandBuilder()
      .setName('nutrition-today')
      .setDescription("Get today's nutrition summary")
      .toJSON();

    const nutritionWeekCommand = new SlashCommandBuilder()
      .setName('nutrition-week')
      .setDescription("Get this week's nutrition summary")
      .toJSON();

    // Register slash commands once bot is ready
    this.client.once(Events.ClientReady, async (readyClient) => {
      this.applicationId = readyClient.user.id;
      logger.info(
        { username: readyClient.user.tag, id: readyClient.user.id },
        'Discord bot connected',
      );
      console.log(`\n  Discord bot: ${readyClient.user.tag}`);
      console.log(`  Use /chatid to get a channel's registration ID`);
      console.log(
        `  Use /log-meal, /nutrition-today, /nutrition-week for nutrition tracking\n`,
      );

      // Register commands globally
      try {
        const rest = new REST({ version: '10' }).setToken(this.botToken);
        await rest.put(Routes.applicationCommands(readyClient.user.id), {
          body: [
            chatIdCommand,
            pingCommand,
            logMealCommand,
            nutritionTodayCommand,
            nutritionWeekCommand,
          ],
        });
        logger.info('Discord slash commands registered');
      } catch (err) {
        logger.warn({ err }, 'Failed to register Discord slash commands');
      }
    });

    // Handle slash command interactions
    this.client.on(Events.InteractionCreate, async (interaction) => {
      if (!interaction.isChatInputCommand()) return;

      const { commandName } = interaction;
      if (commandName === 'chatid') {
        await this.handleChatIdCommand(interaction);
      } else if (commandName === 'ping') {
        await interaction.reply(`${ASSISTANT_NAME} is online.`);
      } else if (commandName === 'log-meal') {
        await this.handleLogMealCommand(interaction);
      } else if (commandName === 'nutrition-today') {
        await this.handleNutritionTodayCommand(interaction);
      } else if (commandName === 'nutrition-week') {
        await this.handleNutritionWeekCommand(interaction);
      }
    });

    // Handle incoming messages
    this.client.on(Events.MessageCreate, async (message: Message) => {
      if (message.author.bot) return;
      if (message.system) return;

      const channel = message.channel;
      if (
        !(
          channel instanceof TextChannel ||
          channel instanceof ThreadChannel ||
          channel instanceof DMChannel
        )
      ) {
        return;
      }

      await this.handleMessage(message, channel);
    });

    // Error handling
    this.client.on(Events.Error, (error) => {
      logger.error({ err: error.message }, 'Discord client error');
    });

    // Login — wrap so a bad token or missing intent doesn't crash the whole app
    try {
      await this.client.login(this.botToken);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (
        msg.includes('disallowed intents') ||
        msg.includes('Used disallowed')
      ) {
        logger.error(
          'Discord: Message Content Intent is not enabled. ' +
            'Go to Discord Developer Portal → your app → Bot → Privileged Gateway Intents → enable Message Content Intent.',
        );
      } else {
        logger.error({ err }, 'Discord: failed to connect');
      }
      return;
    }
  }

  private async handleChatIdCommand(
    interaction: ChatInputCommandInteraction,
  ): Promise<void> {
    const channel = interaction.channel;
    if (!channel) return;

    if (
      !(
        channel instanceof TextChannel ||
        channel instanceof ThreadChannel ||
        channel instanceof DMChannel
      )
    ) {
      return;
    }

    const jid = channelToJid(channel);
    const isDm = channel instanceof DMChannel;
    const name = isDm
      ? interaction.user.displayName
      : (channel as TextChannel | ThreadChannel).name || jid;
    const type = isDm
      ? 'DM'
      : channel instanceof ThreadChannel
        ? 'Thread'
        : 'Channel';

    await interaction.reply(
      `Chat ID: \`${jid}\`\nName: ${name}\nType: ${type}`,
    );
  }

  private async handleLogMealCommand(
    interaction: ChatInputCommandInteraction,
  ): Promise<void> {
    await interaction.deferReply();

    const category = interaction.options.getString('category', true);
    const description = interaction.options.getString('description', true);
    const channel = interaction.channel;

    if (
      !channel ||
      !(
        channel instanceof TextChannel ||
        channel instanceof ThreadChannel ||
        channel instanceof DMChannel
      )
    ) {
      await interaction.editReply('Error: Could not determine channel');
      return;
    }

    const jid = channelToJid(channel);
    const timestamp = new Date().toISOString();
    const senderName =
      interaction.user.displayName || interaction.user.username || 'Unknown';

    try {
      // Send nutrition skill request through NanoClaw
      const nutriMessage = `Log meal: ${category} - ${description}`;
      this.opts.onMessage(jid, {
        id: interaction.id,
        chat_jid: jid,
        sender: interaction.user.id,
        sender_name: senderName,
        content: nutriMessage,
        timestamp,
      });

      await interaction.editReply(
        `📝 Logging meal: **${category}** - ${description}`,
      );
    } catch (err) {
      logger.error({ err }, 'Failed to handle log meal command');
      await interaction.editReply(
        'Error logging meal. Try asking in chat instead.',
      );
    }
  }

  private async handleNutritionTodayCommand(
    interaction: ChatInputCommandInteraction,
  ): Promise<void> {
    await interaction.deferReply();

    const channel = interaction.channel;
    if (
      !channel ||
      !(
        channel instanceof TextChannel ||
        channel instanceof ThreadChannel ||
        channel instanceof DMChannel
      )
    ) {
      await interaction.editReply('Error: Could not determine channel');
      return;
    }

    const jid = channelToJid(channel);
    const timestamp = new Date().toISOString();
    const senderName =
      interaction.user.displayName || interaction.user.username || 'Unknown';

    try {
      // Send nutrition summary request
      this.opts.onMessage(jid, {
        id: interaction.id,
        chat_jid: jid,
        sender: interaction.user.id,
        sender_name: senderName,
        content: 'Show my nutrition summary for today',
        timestamp,
      });

      await interaction.editReply("📊 Fetching today's nutrition summary...");
    } catch (err) {
      logger.error({ err }, 'Failed to handle nutrition today command');
      await interaction.editReply(
        'Error fetching nutrition summary. Try asking in chat instead.',
      );
    }
  }

  private async handleNutritionWeekCommand(
    interaction: ChatInputCommandInteraction,
  ): Promise<void> {
    await interaction.deferReply();

    const channel = interaction.channel;
    if (
      !channel ||
      !(
        channel instanceof TextChannel ||
        channel instanceof ThreadChannel ||
        channel instanceof DMChannel
      )
    ) {
      await interaction.editReply('Error: Could not determine channel');
      return;
    }

    const jid = channelToJid(channel);
    const timestamp = new Date().toISOString();
    const senderName =
      interaction.user.displayName || interaction.user.username || 'Unknown';

    try {
      // Send nutrition summary request
      this.opts.onMessage(jid, {
        id: interaction.id,
        chat_jid: jid,
        sender: interaction.user.id,
        sender_name: senderName,
        content: 'Show my nutrition summary for this week',
        timestamp,
      });

      await interaction.editReply(
        "📊 Fetching this week's nutrition summary...",
      );
    } catch (err) {
      logger.error({ err }, 'Failed to handle nutrition week command');
      await interaction.editReply(
        'Error fetching nutrition summary. Try asking in chat instead.',
      );
    }
  }

  private async handleMessage(
    message: Message,
    channel: TextChannel | ThreadChannel | DMChannel,
  ): Promise<void> {
    const chatJid = channelToJid(channel);
    const content = message.content || '';
    const timestamp = message.createdAt.toISOString();
    const senderName =
      message.author.displayName || message.author.username || 'Unknown';
    const sender = message.author.id;
    const msgId = message.id;

    const isDm = channel instanceof DMChannel;
    const chatName = isDm
      ? senderName
      : (channel as TextChannel | ThreadChannel).name || chatJid;

    const isGroup = !isDm;
    this.opts.onChatMetadata(chatJid, timestamp, chatName, 'discord', isGroup);

    const group = this.opts.registeredGroups()[chatJid];
    if (!group) {
      logger.debug(
        { chatJid, chatName },
        'Message from unregistered Discord channel',
      );
      return;
    }

    const requiresTrigger = group.requiresTrigger !== false;
    let hasTrigger = TRIGGER_PATTERN.test(content);

    if (!hasTrigger && requiresTrigger) {
      const isBotMentioned =
        this.client?.user?.id &&
        message.mentions.users.has(this.client.user.id);
      if (isBotMentioned) {
        hasTrigger = true;
      }
    }

    if (requiresTrigger && !hasTrigger) {
      logger.debug(
        { chatJid, content: content.slice(0, 100) },
        'Discord message ignored: no trigger and group requires trigger',
      );
      return;
    }

    logger.info(
      {
        chatJid,
        chatName,
        sender: senderName,
        hasTrigger,
        contentLength: content.length,
      },
      'Discord message stored, forwarding to agent',
    );

    this.opts.onMessage(chatJid, {
      id: msgId,
      chat_jid: chatJid,
      sender,
      sender_name: senderName,
      content,
      timestamp,
      is_from_me: false,
    });

    // Handle attachments
    if (message.attachments.size > 0) {
      await this.handleAttachments(message, chatJid, group);
    }
  }

  private async handleAttachments(
    message: Message,
    chatJid: string,
    group: RegisteredGroup,
  ): Promise<void> {
    const mediaDir = path.join(GROUPS_DIR, group.folder, 'media');
    fs.mkdirSync(mediaDir, { recursive: true });

    for (const attachment of message.attachments.values()) {
      try {
        const res = await fetch(attachment.url);
        const buf = await res.arrayBuffer();

        const ext = path.extname(attachment.name || 'file').slice(1) || 'bin';
        const typeLabel = attachment.contentType?.split('/')[0] || 'file';
        const fname = `${typeLabel}_${message.id}_${Date.now()}.${ext}`;
        const dest = path.join(mediaDir, fname);
        fs.writeFileSync(dest, Buffer.from(buf));

        const containerPath = `/workspace/group/media/${fname}`;

        // Voice transcription for audio attachments
        if (attachment.contentType?.startsWith('audio/')) {
          const envVars = readEnvFile(['GOOGLE_GEMINI_API_KEY']);
          const geminiKey =
            process.env.GOOGLE_GEMINI_API_KEY || envVars.GOOGLE_GEMINI_API_KEY;
          if (geminiKey) {
            logger.info(
              { dest, mimeHint: attachment.contentType },
              'Attempting Gemini voice transcription',
            );
            const transcript = await transcribeWithGemini(dest, geminiKey);
            if (transcript) {
              this.opts.onMessage(chatJid, {
                id: `${message.id}_audio_${Date.now()}`,
                chat_jid: chatJid,
                sender: message.author.id,
                sender_name: message.author.displayName || 'Unknown',
                content: `[Voice transcription: ${transcript}]`,
                timestamp: message.createdAt.toISOString(),
                is_from_me: false,
              });
              continue;
            }
            logger.warn(
              'Gemini transcription returned null, falling back to placeholder',
            );
          } else {
            logger.warn(
              'No GOOGLE_GEMINI_API_KEY found, skipping transcription',
            );
          }
        }

        // Image/file placeholder
        this.opts.onMessage(chatJid, {
          id: `${message.id}_${typeLabel}_${Date.now()}`,
          chat_jid: chatJid,
          sender: message.author.id,
          sender_name: message.author.displayName || 'Unknown',
          content: `[${typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1)}: ${containerPath}]${message.content ? ` ${message.content}` : ''}`,
          timestamp: message.createdAt.toISOString(),
          is_from_me: false,
        });
      } catch (err) {
        logger.warn({ err }, 'Failed to download Discord attachment');
      }
    }
  }

  async sendMessage(jid: string, text: string): Promise<void> {
    if (!this.client) {
      logger.warn('Discord client not initialized');
      return;
    }

    try {
      const channelId = jidToChannelId(jid);
      const channel = await this.client.channels.fetch(channelId);

      if (
        !channel ||
        !(
          channel instanceof TextChannel ||
          channel instanceof ThreadChannel ||
          channel instanceof DMChannel
        )
      ) {
        logger.warn({ jid }, 'Could not resolve Discord channel for JID');
        return;
      }

      if (text.length <= MAX_DISCORD_MESSAGE_LENGTH) {
        await channel.send(text);
      } else {
        // Split into chunks respecting Discord's 2000 char limit
        for (let i = 0; i < text.length; i += MAX_DISCORD_MESSAGE_LENGTH) {
          await channel.send(text.slice(i, i + MAX_DISCORD_MESSAGE_LENGTH));
        }
      }
      logger.info({ jid, length: text.length }, 'Discord message sent');
    } catch (err) {
      logger.error({ jid, err }, 'Failed to send Discord message');
    }
  }

  isConnected(): boolean {
    return this.client?.isReady() ?? false;
  }

  ownsJid(jid: string): boolean {
    return jid.startsWith('dc:');
  }

  async disconnect(): Promise<void> {
    if (this.client) {
      this.client.destroy();
      this.client = null;
      logger.info('Discord bot stopped');
    }
  }

  async setTyping(jid: string, isTyping: boolean): Promise<void> {
    if (!this.client || !isTyping) return;
    try {
      const channelId = jidToChannelId(jid);
      const channel = await this.client.channels.fetch(channelId);
      if (
        channel instanceof TextChannel ||
        channel instanceof ThreadChannel ||
        channel instanceof DMChannel
      ) {
        await channel.sendTyping();
      }
    } catch (err) {
      logger.debug({ jid, err }, 'Failed to send Discord typing indicator');
    }
  }

  async syncGroups(force: boolean): Promise<void> {
    if (!this.client) return;

    try {
      for (const guild of this.client.guilds.cache.values()) {
        const channels = await guild.channels.fetch();
        for (const [id, ch] of channels) {
          if (ch instanceof TextChannel) {
            const jid = `dc:${id}`;
            this.opts.onChatMetadata(
              jid,
              new Date().toISOString(),
              ch.name,
              'discord',
              true,
            );
          }
        }
      }
      logger.info('Discord channel sync completed');
    } catch (err) {
      logger.warn({ err }, 'Discord sync failed');
    }
  }
}

registerChannel('discord', (opts: ChannelOpts) => {
  const envVars = readEnvFile(['DISCORD_BOT_TOKEN']);
  const token =
    process.env.DISCORD_BOT_TOKEN || envVars.DISCORD_BOT_TOKEN || '';
  if (!token) {
    logger.warn('Discord: DISCORD_BOT_TOKEN not set');
    return null;
  }
  return new DiscordChannel(token, opts);
});
