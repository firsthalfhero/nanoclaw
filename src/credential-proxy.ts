/**
 * Credential proxy for container isolation.
 * Containers connect here instead of directly to the Anthropic API.
 * The proxy injects real credentials so containers never see them.
 *
 * Two auth modes:
 *   API key:  Proxy injects x-api-key on every request.
 *   OAuth:    Container CLI exchanges its placeholder token for a temp
 *             API key via /api/oauth/claude_cli/create_api_key.
 *             Proxy injects real OAuth token on that exchange request;
 *             subsequent requests carry the temp key which is valid as-is.
 */
import { createServer, Server } from 'http';
import { request as httpsRequest } from 'https';
import { request as httpRequest, RequestOptions } from 'http';

import { readEnvFile } from './env.js';
import { logger } from './logger.js';
import { translateRequestBody, translateResponseBody, StreamTranslator } from './openrouter-translate.js';

export type AuthMode = 'api-key' | 'oauth';

export interface ProxyConfig {
  authMode: AuthMode;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
}

export type OnTokenUsage = (usage: TokenUsage) => void;

/**
 * Parse token usage from a buffered Anthropic API response body.
 * Handles both streaming (SSE) and non-streaming (JSON) responses.
 */
function parseTokenUsage(body: string, contentType: string): TokenUsage | null {
  let input = 0,
    output = 0,
    cacheCreate = 0,
    cacheRead = 0;

  if (contentType.includes('text/event-stream')) {
    // SSE: scan for message_start (input tokens) and message_delta (output tokens)
    for (const line of body.split('\n')) {
      if (!line.startsWith('data: ')) continue;
      try {
        const ev = JSON.parse(line.slice(6));
        if (ev.type === 'message_start' && ev.message?.usage) {
          input += ev.message.usage.input_tokens ?? 0;
          cacheCreate += ev.message.usage.cache_creation_input_tokens ?? 0;
          cacheRead += ev.message.usage.cache_read_input_tokens ?? 0;
        }
        if (ev.type === 'message_delta' && ev.usage) {
          output += ev.usage.output_tokens ?? 0;
        }
      } catch {
        /* skip malformed lines */
      }
    }
  } else {
    // Non-streaming JSON
    try {
      const json = JSON.parse(body);
      if (json.usage) {
        input = json.usage.input_tokens ?? 0;
        output = json.usage.output_tokens ?? 0;
        cacheCreate = json.usage.cache_creation_input_tokens ?? 0;
        cacheRead = json.usage.cache_read_input_tokens ?? 0;
      }
    } catch {
      return null;
    }
  }

  if (input === 0 && output === 0) return null;
  return {
    input_tokens: input,
    output_tokens: output,
    cache_creation_tokens: cacheCreate,
    cache_read_tokens: cacheRead,
  };
}

export function startCredentialProxy(
  port: number,
  host = '127.0.0.1',
  onTokenUsage?: OnTokenUsage,
): Promise<Server> {
  const secrets = readEnvFile([
    'ANTHROPIC_API_KEY',
    'CLAUDE_CODE_OAUTH_TOKEN',
    'ANTHROPIC_AUTH_TOKEN',
    'ANTHROPIC_BASE_URL',
    'OPENROUTER_API_KEY',
    'OPENROUTER_MODEL',
    'OPENROUTER_REFERER',
    'OPENROUTER_TITLE',
  ]);

  const openrouterKey = secrets['OPENROUTER_API_KEY'];
  const openrouterModel = secrets['OPENROUTER_MODEL'];
  const openrouterReferer = secrets['OPENROUTER_REFERER'];
  const openrouterTitle = secrets['OPENROUTER_TITLE'];
  const useOpenRouter = !!(openrouterKey && openrouterModel);

  const authMode: AuthMode = secrets.ANTHROPIC_API_KEY ? 'api-key' : 'oauth';
  const oauthToken =
    secrets.CLAUDE_CODE_OAUTH_TOKEN || secrets.ANTHROPIC_AUTH_TOKEN;

  // OpenRouter's Anthropic-compat endpoint lives under /api (i.e. /api/v1/messages).
  // Setting the base to openrouter.ai/api means the container's /v1/messages path
  // gets prepended with /api by the pathPrefix logic below.
  const upstreamBase = useOpenRouter
    ? 'https://openrouter.ai/api'
    : secrets.ANTHROPIC_BASE_URL || 'https://api.anthropic.com';
  const upstreamUrl = new URL(upstreamBase);
  const isHttps = upstreamUrl.protocol === 'https:';
  const makeRequest = isHttps ? httpsRequest : httpRequest;

  if (useOpenRouter) {
    logger.info({ model: openrouterModel }, 'Credential proxy: OpenRouter mode active');
    if (!openrouterReferer && !openrouterTitle) {
      logger.warn('OpenRouter mode active but neither OPENROUTER_REFERER nor OPENROUTER_TITLE is set — requests may be rejected by OpenRouter');
    }
  }

  return new Promise((resolve, reject) => {
    const server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on('data', (c) => chunks.push(c));
      req.on('end', () => {
        let body = Buffer.concat(chunks);
        const headers: Record<string, string | number | string[] | undefined> =
          {
            ...(req.headers as Record<string, string>),
            host: upstreamUrl.host,
            'content-length': body.length,
          };

        // Strip hop-by-hop headers that must not be forwarded by proxies
        delete headers['connection'];
        delete headers['keep-alive'];
        delete headers['transfer-encoding'];

        const isMessagesEndpoint = req.url?.includes('/v1/messages');

        if (useOpenRouter) {
          // OpenRouter uses Bearer auth (not x-api-key)
          delete headers['x-api-key'];
          delete headers['authorization'];
          headers['authorization'] = `Bearer ${openrouterKey}`;

          // OpenRouter requires either Referer or X-Title for routing/identification
          delete headers['referer'];
          delete headers['Referer'];
          if (openrouterReferer) {
            headers['Referer'] = openrouterReferer;
          }
          if (openrouterTitle) {
            headers['X-Title'] = openrouterTitle;
          }

          // Translate Anthropic /v1/messages body → OpenAI /v1/chat/completions format
          if (isMessagesEndpoint && req.method === 'POST' && body.length > 0) {
            try {
              const anthropicJson = JSON.parse(body.toString('utf-8'));
              const openaiJson = translateRequestBody(anthropicJson, openrouterModel!);
              body = Buffer.from(JSON.stringify(openaiJson), 'utf-8');
              headers['content-length'] = body.length;
              headers['content-type'] = 'application/json';
            } catch {
              // Unparseable body — send as-is
            }
          }
        } else if (authMode === 'api-key') {
          // API key mode: inject x-api-key on every request
          delete headers['x-api-key'];
          headers['x-api-key'] = secrets.ANTHROPIC_API_KEY;
        } else {
          // OAuth mode: replace placeholder Bearer token with the real one
          // only when the container actually sends an Authorization header
          // (exchange request + auth probes). Post-exchange requests use
          // x-api-key only, so they pass through without token injection.
          if (headers['authorization']) {
            delete headers['authorization'];
            if (oauthToken) {
              headers['authorization'] = `Bearer ${oauthToken}`;
            }
          }
        }

        // Build upstream path.
        // OpenRouter messages: /v1/messages → /api/v1/chat/completions (OpenAI endpoint)
        // OpenRouter other:    strip Anthropic-specific query params (?beta=true etc)
        // Direct:              forward as-is
        const pathPrefix = upstreamUrl.pathname !== '/' ? upstreamUrl.pathname : '';
        let reqPath: string;
        if (useOpenRouter && isMessagesEndpoint) {
          reqPath = '/v1/chat/completions';
        } else if (useOpenRouter) {
          reqPath = (req.url ?? '/').split('?')[0];
        } else {
          reqPath = req.url ?? '/';
        }
        const upstreamPath = pathPrefix + reqPath;
        logger.debug({ upstreamPath, model: useOpenRouter ? openrouterModel : undefined }, 'Proxy forwarding request');

        const upstream = makeRequest(
          {
            hostname: upstreamUrl.hostname,
            port: upstreamUrl.port || (isHttps ? 443 : 80),
            path: upstreamPath,
            method: req.method,
            headers,
          } as RequestOptions,
          (upRes) => {
            if (upRes.statusCode !== 200) {
              const errChunks: Buffer[] = [];
              upRes.on('data', (c: Buffer) => errChunks.push(c));
              upRes.on('end', () => {
                const errBody = Buffer.concat(errChunks).toString('utf-8').slice(0, 500);
                logger.warn({ status: upRes.statusCode, path: upstreamPath, body: errBody }, 'Proxy upstream non-200 response');
                if (!res.headersSent) {
                  res.writeHead(upRes.statusCode!, upRes.headers);
                  res.end(Buffer.concat(errChunks));
                }
              });
              return;
            }

            if (useOpenRouter && isMessagesEndpoint && upRes.statusCode === 200) {
              // Translate OpenRouter OpenAI-format response → Anthropic format
              const contentType = String(upRes.headers['content-type'] || '');
              const isStreaming = contentType.includes('text/event-stream');
              res.writeHead(200, upRes.headers);

              if (isStreaming) {
                const translator = new StreamTranslator();
                const translatedChunks: string[] = [];
                let lineBuffer = '';
                upRes.on('data', (chunk: Buffer) => {
                  lineBuffer += chunk.toString('utf-8');
                  const lines = lineBuffer.split('\n');
                  lineBuffer = lines.pop() ?? '';
                  for (const line of lines) {
                    for (const ev of translator.processLine(line)) {
                      res.write(ev);
                      translatedChunks.push(ev);
                    }
                  }
                });
                upRes.on('end', () => {
                  if (lineBuffer) {
                    for (const ev of translator.processLine(lineBuffer)) {
                      res.write(ev);
                      translatedChunks.push(ev);
                    }
                  }
                  res.end();
                  if (onTokenUsage) {
                    const usage = parseTokenUsage(translatedChunks.join(''), 'text/event-stream');
                    if (usage) onTokenUsage(usage);
                  }
                });
              } else {
                const chunks: Buffer[] = [];
                upRes.on('data', (c: Buffer) => chunks.push(c));
                upRes.on('end', () => {
                  try {
                    const openaiBody = JSON.parse(Buffer.concat(chunks).toString('utf-8'));
                    const anthropicBody = translateResponseBody(openaiBody);
                    const translated = Buffer.from(JSON.stringify(anthropicBody), 'utf-8');
                    res.write(translated);
                    res.end();
                    if (onTokenUsage) {
                      const usage = parseTokenUsage(JSON.stringify(anthropicBody), 'application/json');
                      if (usage) onTokenUsage(usage);
                    }
                  } catch {
                    res.write(Buffer.concat(chunks));
                    res.end();
                  }
                });
              }
            } else {
              res.writeHead(upRes.statusCode!, upRes.headers);
              // Tee: capture body for usage parsing while streaming to client
              if (onTokenUsage && isMessagesEndpoint && upRes.statusCode === 200) {
                const contentType = String(upRes.headers['content-type'] || '');
                const chunks: Buffer[] = [];
                upRes.on('data', (chunk: Buffer) => {
                  chunks.push(chunk);
                  res.write(chunk);
                });
                upRes.on('end', () => {
                  res.end();
                  const bodyText = Buffer.concat(chunks).toString('utf-8');
                  const usage = parseTokenUsage(bodyText, contentType);
                  if (usage) onTokenUsage(usage);
                });
              } else {
                upRes.pipe(res);
              }
            }
          },
        );

        upstream.on('error', (err) => {
          logger.error(
            { err, url: req.url },
            'Credential proxy upstream error',
          );
          if (!res.headersSent) {
            res.writeHead(502);
            res.end('Bad Gateway');
          }
        });

        upstream.write(body);
        upstream.end();
      });
    });

    server.listen(port, host, () => {
      logger.info({ port, host, authMode }, 'Credential proxy started');
      resolve(server);
    });

    server.on('error', reject);
  });
}

/** Detect which auth mode the host is configured for. */
export function detectAuthMode(): AuthMode {
  const secrets = readEnvFile(['ANTHROPIC_API_KEY']);
  return secrets.ANTHROPIC_API_KEY ? 'api-key' : 'oauth';
}
