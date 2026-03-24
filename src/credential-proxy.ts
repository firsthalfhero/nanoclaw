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
  ]);

  const authMode: AuthMode = secrets.ANTHROPIC_API_KEY ? 'api-key' : 'oauth';
  const oauthToken =
    secrets.CLAUDE_CODE_OAUTH_TOKEN || secrets.ANTHROPIC_AUTH_TOKEN;

  const upstreamUrl = new URL(
    secrets.ANTHROPIC_BASE_URL || 'https://api.anthropic.com',
  );
  const isHttps = upstreamUrl.protocol === 'https:';
  const makeRequest = isHttps ? httpsRequest : httpRequest;

  return new Promise((resolve, reject) => {
    const server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on('data', (c) => chunks.push(c));
      req.on('end', () => {
        const body = Buffer.concat(chunks);
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

        if (authMode === 'api-key') {
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

        const isMessagesEndpoint = req.url?.includes('/v1/messages');

        const upstream = makeRequest(
          {
            hostname: upstreamUrl.hostname,
            port: upstreamUrl.port || (isHttps ? 443 : 80),
            path: req.url,
            method: req.method,
            headers,
          } as RequestOptions,
          (upRes) => {
            res.writeHead(upRes.statusCode!, upRes.headers);

            // Tee: capture body for usage parsing while streaming to client
            if (
              onTokenUsage &&
              isMessagesEndpoint &&
              upRes.statusCode === 200
            ) {
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
