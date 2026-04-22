import fs from 'fs';
import path from 'path';

import { Api, Bot } from 'grammy';

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

export interface TelegramChannelOpts {
  onMessage: OnInboundMessage;
  onChatMetadata: OnChatMetadata;
  registeredGroups: () => Record<string, RegisteredGroup>;
}

/**
 * Send a message with Telegram Markdown parse mode, falling back to plain text.
 */
async function sendTelegramMessage(
  api: { sendMessage: Api['sendMessage'] },
  chatId: string | number,
  text: string,
  options: { message_thread_id?: number } = {},
): Promise<void> {
  try {
    await api.sendMessage(chatId, text, {
      ...options,
      parse_mode: 'Markdown',
    });
  } catch (err) {
    logger.debug({ err }, 'Markdown send failed, falling back to plain text');
    await api.sendMessage(chatId, text, options);
  }
}

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

export class TelegramChannel implements Channel {
  name = 'telegram';

  private bot: Bot | null = null;
  private opts: TelegramChannelOpts;
  private botToken: string;
  private botUsername: string | null = null;

  constructor(botToken: string, opts: TelegramChannelOpts) {
    this.botToken = botToken;
    this.opts = opts;
  }

  async connect(): Promise<void> {
    this.bot = new Bot(this.botToken);

    this.bot.command('chatid', (ctx) => {
      const chatId = ctx.chat.id;
      const chatType = ctx.chat.type;
      const chatName =
        chatType === 'private'
          ? ctx.from?.first_name || 'Private'
          : (ctx.chat as any).title || 'Unknown';

      ctx.reply(
        `Chat ID: \`tg:${chatId}\`\nName: ${chatName}\nType: ${chatType}`,
        { parse_mode: 'Markdown' },
      );
    });

    this.bot.command('ping', (ctx) => {
      ctx.reply(`${ASSISTANT_NAME} is online.`);
    });

    const TELEGRAM_BOT_COMMANDS = new Set(['chatid', 'ping']);

    this.bot.on('message:text', async (ctx) => {
      if (ctx.message.text.startsWith('/')) {
        const cmd = ctx.message.text.slice(1).split(/[\s@]/)[0].toLowerCase();
        if (TELEGRAM_BOT_COMMANDS.has(cmd)) return;
      }

      const chatJid = `tg:${ctx.chat.id}`;
      let content = ctx.message.text;
      const timestamp = new Date(ctx.message.date * 1000).toISOString();
      const senderName =
        ctx.from?.first_name ||
        ctx.from?.username ||
        ctx.from?.id.toString() ||
        'Unknown';
      const sender = ctx.from?.id.toString() || '';
      const msgId = ctx.message.message_id.toString();

      const chatName =
        ctx.chat.type === 'private'
          ? senderName
          : (ctx.chat as any).title || chatJid;

      const isGroup =
        ctx.chat.type === 'group' || ctx.chat.type === 'supergroup';
      this.opts.onChatMetadata(
        chatJid,
        timestamp,
        chatName,
        'telegram',
        isGroup,
      );

      const group = this.opts.registeredGroups()[chatJid];
      if (!group) {
        logger.debug(
          { chatJid, chatName },
          'Message from unregistered Telegram chat',
        );
        return;
      }

      const requiresTrigger = group.requiresTrigger !== false;
      let hasTrigger = TRIGGER_PATTERN.test(content);

      if (!hasTrigger && requiresTrigger) {
        const botUsername = this.botUsername || ctx.me?.username?.toLowerCase();
        const entities = ctx.message.entities || [];

        const isBotMentioned = entities.some((entity) => {
          if (entity.type === 'mention') {
            const mentionText = content
              .substring(entity.offset, entity.offset + entity.length)
              .toLowerCase();
            return mentionText === `@${botUsername}`;
          }
          if (entity.type === 'text_mention') {
            const mentionedUser = (entity as any).user;
            return mentionedUser?.username?.toLowerCase() === botUsername;
          }
          return false;
        });

        if (isBotMentioned) {
          content = `@${ASSISTANT_NAME} ${content}`;
          hasTrigger = true;
          logger.debug(
            { chatJid, botUsername: `@${botUsername}` },
            'Bot mention detected, prepended trigger',
          );
        }
      }

      if (requiresTrigger && !hasTrigger) {
        logger.debug(
          { chatJid, content: content.slice(0, 100) },
          'Telegram message ignored: no trigger word and group requires trigger',
        );
        return;
      }

      logger.info(
        { chatJid, chatName, sender: senderName, hasTrigger, contentLength: content.length },
        'Telegram message stored, forwarding to agent',
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
    });

    const storeNonText = (ctx: any, placeholder: string) => {
      const chatJid = `tg:${ctx.chat.id}`;
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) {
        logger.debug({ chatJid }, 'Non-text message from unregistered chat, ignoring');
        return;
      }

      const timestamp = new Date(ctx.message.date * 1000).toISOString();
      const senderName =
        ctx.from?.first_name ||
        ctx.from?.username ||
        ctx.from?.id?.toString() ||
        'Unknown';
      const caption = ctx.message.caption ? ` ${ctx.message.caption}` : '';

      const isGroup =
        ctx.chat.type === 'group' || ctx.chat.type === 'supergroup';
      this.opts.onChatMetadata(
        chatJid,
        timestamp,
        undefined,
        'telegram',
        isGroup,
      );

      logger.info(
        { chatJid, placeholder, hasCaption: !!ctx.message.caption },
        'Non-text Telegram message stored',
      );

      this.opts.onMessage(chatJid, {
        id: ctx.message.message_id.toString(),
        chat_jid: chatJid,
        sender: ctx.from?.id?.toString() || '',
        sender_name: senderName,
        content: `${placeholder}${caption}`,
        timestamp,
        is_from_me: false,
      });
    };

    this.bot.on('message:photo', async (ctx) => {
      const chatJid = `tg:${ctx.chat.id}`;
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) return;

      try {
        const photos = ctx.message.photo;
        const best = photos[photos.length - 1];
        const file = await ctx.api.getFile(best.file_id);
        const fileUrl = `https://api.telegram.org/file/bot${this.botToken}/${file.file_path}`;

        const mediaDir = path.join(GROUPS_DIR, group.folder, 'media');
        fs.mkdirSync(mediaDir, { recursive: true });
        const fname = `photo_${ctx.message.message_id}_${Date.now()}.jpg`;
        const dest = path.join(mediaDir, fname);
        const res = await fetch(fileUrl);
        const buf = await res.arrayBuffer();
        fs.writeFileSync(dest, Buffer.from(buf));

        const containerPath = `/workspace/group/media/${fname}`;
        const caption = ctx.message.caption ? ` ${ctx.message.caption}` : '';
        storeNonText(ctx, `[Photo: ${containerPath}]${caption}`);
      } catch (err) {
        logger.warn({ err }, 'Failed to download photo, using placeholder');
        storeNonText(ctx, '[Photo]');
      }
    });

    this.bot.on('message:video', (ctx) => storeNonText(ctx, '[Video]'));
    this.bot.on('message:voice', async (ctx) => {
      const chatJid = `tg:${ctx.chat.id}`;
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) return;

      try {
        const voice = ctx.message.voice;
        const file = await ctx.api.getFile(voice.file_id);
        const fileUrl = `https://api.telegram.org/file/bot${this.botToken}/${file.file_path}`;

        const mediaDir = path.join(GROUPS_DIR, group.folder, 'media');
        fs.mkdirSync(mediaDir, { recursive: true });
        const fname = `voice_${ctx.message.message_id}_${Date.now()}.ogg`;
        const dest = path.join(mediaDir, fname);
        const res = await fetch(fileUrl);
        const buf = await res.arrayBuffer();
        fs.writeFileSync(dest, Buffer.from(buf));

        const containerPath = `/workspace/group/media/${fname}`;
        const caption = ctx.message.caption ? ` ${ctx.message.caption}` : '';

        const envVars = readEnvFile(['GOOGLE_GEMINI_API_KEY']);
        const geminiKey =
          process.env.GOOGLE_GEMINI_API_KEY || envVars.GOOGLE_GEMINI_API_KEY;
        if (geminiKey) {
          logger.info(
            { dest, mimeHint: 'audio/opus' },
            'Attempting Gemini voice transcription',
          );
          const transcript = await transcribeWithGemini(dest, geminiKey);
          if (transcript) {
            storeNonText(ctx, `[Voice transcription: ${transcript}]${caption}`);
            return;
          }
          logger.warn(
            'Gemini transcription returned null, falling back to placeholder',
          );
        } else {
          logger.warn('No GOOGLE_GEMINI_API_KEY found, skipping transcription');
        }

        storeNonText(ctx, `[Voice: ${containerPath}]`);
      } catch (err) {
        logger.warn(
          { err },
          'Failed to download voice message, using placeholder',
        );
        storeNonText(ctx, '[Voice message]');
      }
    });

    this.bot.on('message:audio', async (ctx) => {
      const chatJid = `tg:${ctx.chat.id}`;
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) return;

      try {
        const audio = ctx.message.audio;
        const file = await ctx.api.getFile(audio.file_id);
        const fileUrl = `https://api.telegram.org/file/bot${this.botToken}/${file.file_path}`;

        const mediaDir = path.join(GROUPS_DIR, group.folder, 'media');
        fs.mkdirSync(mediaDir, { recursive: true });
        const ext = path.extname(file.file_path ?? '.mp3').slice(1) || 'mp3';
        const fname = `audio_${ctx.message.message_id}_${Date.now()}.${ext}`;
        const dest = path.join(mediaDir, fname);
        const res = await fetch(fileUrl);
        const buf = await res.arrayBuffer();
        fs.writeFileSync(dest, Buffer.from(buf));

        const containerPath = `/workspace/group/media/${fname}`;
        const envVars = readEnvFile(['GOOGLE_GEMINI_API_KEY']);
        const geminiKey =
          process.env.GOOGLE_GEMINI_API_KEY || envVars.GOOGLE_GEMINI_API_KEY;
        if (geminiKey) {
          const transcript = await transcribeWithGemini(dest, geminiKey);
          if (transcript) {
            storeNonText(ctx, `[Audio transcription: ${transcript}]`);
            return;
          }
        }

        storeNonText(ctx, `[Audio: ${containerPath}]`);
      } catch (err) {
        logger.warn({ err }, 'Failed to process audio message');
        storeNonText(ctx, '[Audio]');
      }
    });

    this.bot.on('message:document', (ctx) => {
      const name = ctx.message.document?.file_name || 'file';
      storeNonText(ctx, `[Document: ${name}]`);
    });

    this.bot.on('message:sticker', (ctx) => {
      const emoji = ctx.message.sticker?.emoji || '';
      storeNonText(ctx, `[Sticker ${emoji}]`);
    });

    this.bot.on('message:location', (ctx) => storeNonText(ctx, '[Location]'));
    this.bot.on('message:contact', (ctx) => storeNonText(ctx, '[Contact]'));

    this.bot.catch((err) => {
      logger.error({ err: err.message }, 'Telegram bot error');
    });

    return new Promise<void>((resolve, reject) => {
      this.bot!
        .start({
          onStart: async (botInfo) => {
            this.botUsername = botInfo.username?.toLowerCase() || null;
            logger.info(
              { username: botInfo.username, id: botInfo.id, cachedUsername: this.botUsername },
              'Telegram bot connected',
            );
            console.log(`\n  Telegram bot: @${botInfo.username}`);
            console.log(
              `  Send /chatid to the bot to get a chat's registration ID\n`,
            );
            resolve();
          },
        })
        .catch((err) => {
          logger.error({ err: err.message }, 'Telegram bot start error');
          reject(err);
        });
    });
  }

  async sendMessage(jid: string, text: string): Promise<void> {
    if (!this.bot) {
      logger.warn('Telegram bot not initialized');
      return;
    }

    try {
      const numericId = jid.replace(/^tg:/, '');

      const MAX_LENGTH = 4096;
      if (text.length <= MAX_LENGTH) {
        await sendTelegramMessage(this.bot.api, numericId, text);
      } else {
        for (let i = 0; i < text.length; i += MAX_LENGTH) {
          await sendTelegramMessage(
            this.bot.api,
            numericId,
            text.slice(i, i + MAX_LENGTH),
          );
        }
      }
      logger.info({ jid, length: text.length }, 'Telegram message sent');
    } catch (err) {
      logger.error({ jid, err }, 'Failed to send Telegram message');
    }
  }

  isConnected(): boolean {
    return this.bot !== null;
  }

  ownsJid(jid: string): boolean {
    return jid.startsWith('tg:');
  }

  async disconnect(): Promise<void> {
    if (this.bot) {
      this.bot.stop();
      this.bot = null;
      logger.info('Telegram bot stopped');
    }
  }

  async setTyping(jid: string, isTyping: boolean): Promise<void> {
    if (!this.bot || !isTyping) return;
    try {
      const numericId = jid.replace(/^tg:/, '');
      await this.bot.api.sendChatAction(numericId, 'typing');
    } catch (err) {
      logger.debug({ jid, err }, 'Failed to send Telegram typing indicator');
    }
  }
}

registerChannel('telegram', (opts: ChannelOpts) => {
  const envVars = readEnvFile(['TELEGRAM_BOT_TOKEN']);
  const token =
    process.env.TELEGRAM_BOT_TOKEN || envVars.TELEGRAM_BOT_TOKEN || '';
  if (!token) {
    logger.warn('Telegram: TELEGRAM_BOT_TOKEN not set');
    return null;
  }
  return new TelegramChannel(token, opts);
});
