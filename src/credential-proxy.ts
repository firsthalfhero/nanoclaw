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
 *
 * OpenRouter mode: uses OpenRouter's OpenAI-compat endpoint
 *   (https://openrouter.ai/v1/chat/completions). Requests are translated
 *   from Anthropic format to OpenAI format, and responses are translated
 *   back, including reasoning token support (reasoning param + reasoning_details).
 */
import { createServer, Server } from 'http';
import { request as httpsRequest } from 'https';
import { request as httpRequest, RequestOptions } from 'http';

import { readEnvFile } from './env.js';
import { logger } from './logger.js';
import {
  translateRequestBody,
  translateResponseBody,
  StreamTranslator,
} from './openrouter-translate.js';

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
    'OPENROUTER_REASONING_EFFORT',
    'OPENROUTER_REASONING_MAX_TOKENS',
  ]);

  const openrouterKey = secrets['OPENROUTER_API_KEY'];
  const openrouterModel = secrets['OPENROUTER_MODEL'];
  const openrouterReferer = secrets['OPENROUTER_REFERER'];
  const openrouterTitle = secrets['OPENROUTER_TITLE'];
  const openrouterReasoningEffort = secrets['OPENROUTER_REASONING_EFFORT'];
  const openrouterReasoningMaxTokens = secrets[
    'OPENROUTER_REASONING_MAX_TOKENS'
  ]
    ? parseInt(secrets['OPENROUTER_REASONING_MAX_TOKENS'], 10)
    : undefined;
  const useOpenRouter = !!(openrouterKey && openrouterModel);

  const reasoningConfig =
    openrouterReasoningEffort || openrouterReasoningMaxTokens
      ? {
          ...(openrouterReasoningEffort
            ? { effort: openrouterReasoningEffort }
            : {}),
          ...(openrouterReasoningMaxTokens
            ? { max_tokens: openrouterReasoningMaxTokens }
            : {}),
        }
      : undefined;

  const authMode: AuthMode = secrets.ANTHROPIC_API_KEY ? 'api-key' : 'oauth';
  const oauthToken =
    secrets.CLAUDE_CODE_OAUTH_TOKEN || secrets.ANTHROPIC_AUTH_TOKEN;

  // OpenRouter's OpenAI-compat endpoint is at openrouter.ai/v1/chat/completions.
  // The /v1/messages path from the container is overridden to /v1/chat/completions
  // in the request handler below.
  const upstreamBase = useOpenRouter
    ? 'https://openrouter.ai'
    : secrets.ANTHROPIC_BASE_URL || 'https://api.anthropic.com';
  const upstreamUrl = new URL(upstreamBase);
  const isHttps = upstreamUrl.protocol === 'https:';
  const makeRequest = isHttps ? httpsRequest : httpRequest;

  if (useOpenRouter) {
    logger.info(
      { model: openrouterModel },
      'Credential proxy: OpenRouter mode active',
    );
    if (!openrouterReferer && !openrouterTitle) {
      logger.warn(
        'OpenRouter mode active but neither OPENROUTER_REFERER nor OPENROUTER_TITLE is set — requests may be rejected by OpenRouter',
      );
    }
  }

  return new Promise((resolve, reject) => {
    const server = createServer((req, res) => {
      logger.debug(
        {
          method: req.method,
          url: req.url,
          contentLength: req.headers['content-length'],
        },
        'Proxy received request',
      );
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
        let isRequestStreaming = false;

        if (useOpenRouter) {
          // OpenRouter OpenAI-compat endpoint uses Bearer auth
          delete headers['x-api-key'];
          delete headers['authorization'];
          headers['authorization'] = `Bearer ${openrouterKey}`;

          if (openrouterReferer) headers['HTTP-Referer'] = openrouterReferer;
          if (openrouterTitle) headers['X-Title'] = openrouterTitle;

          // Translate from Anthropic to OpenAI format for the chat completions endpoint
          if (isMessagesEndpoint && req.method === 'POST' && body.length > 0) {
            try {
              const anthropicJson = JSON.parse(body.toString('utf-8'));
              isRequestStreaming = !!anthropicJson.stream;
              const openaiJson = translateRequestBody(
                anthropicJson,
                openrouterModel!,
                reasoningConfig,
              );
              body = Buffer.from(JSON.stringify(openaiJson), 'utf-8');
              headers['content-length'] = body.length;
              logger.debug(
                {
                  openrouterModel,
                  isRequestStreaming,
                  hasReasoning: !!reasoningConfig,
                },
                'OpenRouter: translated request to OpenAI format',
              );
            } catch (err) {
              logger.warn(
                { err },
                'OpenRouter: failed to translate request body',
              );
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
        // OpenRouter (OpenAI-compat): /v1/messages → /v1/chat/completions
        // Direct Anthropic: forward as-is.
        const pathPrefix =
          upstreamUrl.pathname !== '/' ? upstreamUrl.pathname : '';
        let upstreamPath = pathPrefix + (req.url ?? '/');

        if (useOpenRouter && isMessagesEndpoint) {
          // Route to the OpenAI-compat endpoint; strip any query params too
          upstreamPath = '/v1/chat/completions';
        } else if (useOpenRouter && upstreamPath.includes('?beta=true')) {
          // Strip ?beta=true that the Claude Code SDK appends on other paths
          upstreamPath = upstreamPath.replace('?beta=true', '');
        }
        logger.debug(
          { upstreamPath, model: useOpenRouter ? openrouterModel : undefined },
          'Proxy forwarding request',
        );
        logger.debug(
          {
            upstreamPath,
            headers: {
              ...headers,
              authorization: headers.authorization
                ? 'Bearer [redacted]'
                : undefined,
              'x-api-key': headers['x-api-key'] ? '[redacted]' : undefined,
            },
          },
          'Forwarding to upstream with headers (sensitive headers redacted)',
        );

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
              logger.debug(
                { status: upRes.statusCode, headers: upRes.headers },
                'Upstream non-200 response',
              );
              const errChunks: Buffer[] = [];
              upRes.on('data', (c: Buffer) => errChunks.push(c));
              upRes.on('end', () => {
                const errBody = Buffer.concat(errChunks)
                  .toString('utf-8')
                  .slice(0, 500);
                logger.warn(
                  {
                    status: upRes.statusCode,
                    path: upstreamPath,
                    body: errBody,
                  },
                  'Proxy upstream non-200 response',
                );
                if (!res.headersSent) {
                  res.writeHead(upRes.statusCode!, upRes.headers);
                  res.end(Buffer.concat(errChunks));
                }
              });
              return;
            }

            logger.debug(
              {
                status: upRes.statusCode,
                contentType: upRes.headers['content-type'],
              },
              'Upstream response received, piping to client',
            );

            if (useOpenRouter && isMessagesEndpoint) {
              // Translate OpenAI response back to Anthropic format
              const upstreamContentType = String(
                upRes.headers['content-type'] || '',
              );
              const isStreaming =
                isRequestStreaming ||
                upstreamContentType.includes('text/event-stream');

              if (isStreaming) {
                const translator = new StreamTranslator();
                let lineBuffer = '';
                const allTranslated: string[] = [];

                res.writeHead(200, {
                  'content-type': 'text/event-stream',
                  'cache-control': 'no-cache',
                  connection: 'keep-alive',
                });

                upRes.on('data', (chunk: Buffer) => {
                  const text = lineBuffer + chunk.toString('utf-8');
                  const lines = text.split('\n');
                  lineBuffer = lines.pop()!;

                  for (const line of lines) {
                    const translated = translator.processLine(line);
                    for (const t of translated) {
                      res.write(t);
                      if (onTokenUsage) allTranslated.push(t);
                    }
                  }
                });

                upRes.on('end', () => {
                  if (lineBuffer) {
                    const translated = translator.processLine(lineBuffer);
                    for (const t of translated) {
                      res.write(t);
                      if (onTokenUsage) allTranslated.push(t);
                    }
                  }
                  res.end();

                  if (onTokenUsage && allTranslated.length > 0) {
                    const fullBody = allTranslated.join('');
                    const usage = parseTokenUsage(
                      fullBody,
                      'text/event-stream',
                    );
                    if (usage) onTokenUsage(usage);
                  }
                });
              } else {
                // Non-streaming: buffer, translate, re-send
                const upChunks: Buffer[] = [];
                upRes.on('data', (c: Buffer) => upChunks.push(c));
                upRes.on('end', () => {
                  try {
                    const openaiBody = JSON.parse(
                      Buffer.concat(upChunks).toString('utf-8'),
                    );
                    const anthropicBody = translateResponseBody(openaiBody);
                    const translatedBuf = Buffer.from(
                      JSON.stringify(anthropicBody),
                      'utf-8',
                    );
                    res.writeHead(200, {
                      'content-type': 'application/json',
                      'content-length': translatedBuf.length,
                    });
                    res.end(translatedBuf);

                    if (onTokenUsage) {
                      const usage = parseTokenUsage(
                        JSON.stringify(anthropicBody),
                        'application/json',
                      );
                      if (usage) onTokenUsage(usage);
                    }
                  } catch (err) {
                    logger.error(
                      { err },
                      'OpenRouter: failed to translate response',
                    );
                    if (!res.headersSent) {
                      res.writeHead(502);
                      res.end('Translation error');
                    }
                  }
                });
              }
            } else if (
              onTokenUsage &&
              isMessagesEndpoint &&
              upRes.statusCode === 200
            ) {
              // Non-OpenRouter: tee the stream for token counting
              res.writeHead(upRes.statusCode!, upRes.headers);
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
              res.writeHead(upRes.statusCode!, upRes.headers);
              upRes.pipe(res);
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
