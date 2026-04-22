/**
 * Translates between Anthropic and OpenAI API formats for OpenRouter.
 * OpenRouter only supports the OpenAI /v1/chat/completions format;
 * the Claude Agent SDK only speaks Anthropic /v1/messages format.
 * This module handles both request and streaming-response translation.
 */

// ─── Request: Anthropic → OpenAI ─────────────────────────────────────────────

export function translateRequestBody(
  anthropicBody: any,
  targetModel: string,
): any {
  const messages: any[] = [];

  // System prompt → system role message
  if (anthropicBody.system) {
    const text =
      typeof anthropicBody.system === 'string'
        ? anthropicBody.system
        : anthropicBody.system
            .map((b: any) => (b.type === 'text' ? b.text : ''))
            .join('');
    if (text) messages.push({ role: 'system', content: text });
  }

  for (const msg of anthropicBody.messages ?? []) {
    if (msg.role === 'user' && Array.isArray(msg.content)) {
      const toolResults = msg.content.filter(
        (b: any) => b.type === 'tool_result',
      );
      const textBlocks = msg.content.filter((b: any) => b.type === 'text');

      if (toolResults.length > 0) {
        for (const tr of toolResults) {
          const content =
            typeof tr.content === 'string'
              ? tr.content
              : Array.isArray(tr.content)
                ? tr.content.map((c: any) => c.text ?? '').join('')
                : '';
          messages.push({
            role: 'tool',
            tool_call_id: tr.tool_use_id,
            content,
          });
        }
        if (textBlocks.length > 0) {
          messages.push({
            role: 'user',
            content: textBlocks.map((b: any) => b.text).join('\n'),
          });
        }
      } else {
        const text = msg.content.map((b: any) => b.text ?? '').join('\n');
        messages.push({ role: 'user', content: text });
      }
    } else if (msg.role === 'assistant' && Array.isArray(msg.content)) {
      const textBlocks = msg.content.filter((b: any) => b.type === 'text');
      const toolUseBlocks = msg.content.filter(
        (b: any) => b.type === 'tool_use',
      );

      const out: any = {
        role: 'assistant',
        content: textBlocks.map((b: any) => b.text).join('') || null,
      };
      if (toolUseBlocks.length > 0) {
        out.tool_calls = toolUseBlocks.map((b: any) => ({
          id: b.id,
          type: 'function',
          function: { name: b.name, arguments: JSON.stringify(b.input ?? {}) },
        }));
      }
      messages.push(out);
    } else {
      messages.push(msg);
    }
  }

  const tools = anthropicBody.tools?.map((t: any) => ({
    type: 'function',
    function: {
      name: t.name,
      description: t.description ?? '',
      parameters: t.input_schema ?? { type: 'object', properties: {} },
    },
  }));

  const out: any = {
    model: targetModel,
    messages,
    max_tokens: anthropicBody.max_tokens,
    stream: anthropicBody.stream ?? false,
  };
  if (tools?.length) out.tools = tools;
  if (anthropicBody.temperature != null)
    out.temperature = anthropicBody.temperature;

  return out;
}

// ─── Response (non-streaming): OpenAI → Anthropic ────────────────────────────

export function translateResponseBody(openaiBody: any): any {
  const msgId = openaiBody.id ?? `msg_${Math.random().toString(36).slice(2)}`;
  const choice = openaiBody.choices?.[0];
  const msg = choice?.message ?? {};
  const content: any[] = [];

  if (msg.content) content.push({ type: 'text', text: msg.content });

  if (msg.tool_calls) {
    for (const tc of msg.tool_calls) {
      let input: any = {};
      try {
        input = JSON.parse(tc.function.arguments ?? '{}');
      } catch {
        /* raw string fallback */
      }
      content.push({
        type: 'tool_use',
        id: tc.id,
        name: tc.function.name,
        input,
      });
    }
  }

  const stopReason =
    choice?.finish_reason === 'tool_calls'
      ? 'tool_use'
      : choice?.finish_reason === 'length'
        ? 'max_tokens'
        : 'end_turn';

  return {
    id: msgId,
    type: 'message',
    role: 'assistant',
    content,
    model: openaiBody.model ?? 'unknown',
    stop_reason: stopReason,
    stop_sequence: null,
    usage: {
      input_tokens: openaiBody.usage?.prompt_tokens ?? 0,
      output_tokens: openaiBody.usage?.completion_tokens ?? 0,
    },
  };
}

// ─── Response (streaming): OpenAI SSE → Anthropic SSE ────────────────────────

export class StreamTranslator {
  private msgId = `msg_${Math.random().toString(36).slice(2)}`;
  private started = false;
  private inputToks = 0;
  private outToks = 0;
  // Track open content blocks: index → { type, closed }
  private blocks = new Map<number, { type: string; closed: boolean }>();
  private nextIndex = 0; // next block index to open

  /** Feed one raw SSE line; returns translated SSE lines to emit. */
  processLine(line: string): string[] {
    if (!line.startsWith('data: ')) return [];
    const raw = line.slice(6).trim();
    if (raw === '[DONE]') return this.flush();

    let chunk: any;
    try {
      chunk = JSON.parse(raw);
    } catch {
      return [];
    }

    const events: string[] = [];

    if (!this.started) {
      this.started = true;
      this.inputToks = chunk.usage?.prompt_tokens ?? 0;
      events.push(
        sse({
          type: 'message_start',
          message: {
            id: this.msgId,
            type: 'message',
            role: 'assistant',
            model: chunk.model ?? 'unknown',
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: this.inputToks, output_tokens: 0 },
          },
        }),
      );
    }

    for (const choice of chunk.choices ?? []) {
      const delta = choice.delta ?? {};

      // Text delta
      if (typeof delta.content === 'string' && delta.content.length > 0) {
        if (!this.blocks.has(0)) {
          this.blocks.set(0, { type: 'text', closed: false });
          this.nextIndex = Math.max(this.nextIndex, 1);
          events.push(
            sse({
              type: 'content_block_start',
              index: 0,
              content_block: { type: 'text', text: '' },
            }),
          );
        }
        events.push(
          sse({
            type: 'content_block_delta',
            index: 0,
            delta: { type: 'text_delta', text: delta.content },
          }),
        );
      }

      // Tool call deltas
      for (const tc of delta.tool_calls ?? []) {
        // OpenAI tool_calls[].index = tool call slot (0-based, not content block index)
        const blockIdx = 1 + tc.index; // reserve index 0 for text

        if (tc.id) {
          // First chunk for this tool call — open the block
          // Close text block first if open and not yet closed
          const textBlock = this.blocks.get(0);
          if (textBlock && !textBlock.closed) {
            textBlock.closed = true;
            events.push(sse({ type: 'content_block_stop', index: 0 }));
          }
          this.blocks.set(blockIdx, { type: 'tool_use', closed: false });
          this.nextIndex = Math.max(this.nextIndex, blockIdx + 1);
          events.push(
            sse({
              type: 'content_block_start',
              index: blockIdx,
              content_block: {
                type: 'tool_use',
                id: tc.id,
                name: tc.function?.name ?? '',
                input: {},
              },
            }),
          );
        }

        if (tc.function?.arguments) {
          events.push(
            sse({
              type: 'content_block_delta',
              index: blockIdx,
              delta: {
                type: 'input_json_delta',
                partial_json: tc.function.arguments,
              },
            }),
          );
        }
      }

      // Finish reason
      if (choice.finish_reason) {
        const stopReason =
          choice.finish_reason === 'tool_calls'
            ? 'tool_use'
            : choice.finish_reason === 'length'
              ? 'max_tokens'
              : 'end_turn';

        events.push(...this.closeAllBlocks());

        if (chunk.usage?.completion_tokens)
          this.outToks = chunk.usage.completion_tokens;
        events.push(
          sse({
            type: 'message_delta',
            delta: { stop_reason: stopReason, stop_sequence: null },
            usage: { output_tokens: this.outToks },
          }),
        );
        events.push(sse({ type: 'message_stop' }));
      }
    }

    // Usage-only chunk (some providers send this at the end)
    if (chunk.usage?.completion_tokens) {
      this.outToks = chunk.usage.completion_tokens;
    }

    return events;
  }

  private flush(): string[] {
    const events = this.closeAllBlocks();
    events.push(
      sse({
        type: 'message_delta',
        delta: { stop_reason: 'end_turn', stop_sequence: null },
        usage: { output_tokens: this.outToks },
      }),
    );
    events.push(sse({ type: 'message_stop' }));
    return events;
  }

  private closeAllBlocks(): string[] {
    const events: string[] = [];
    for (const [idx, block] of this.blocks) {
      if (!block.closed) {
        block.closed = true;
        events.push(sse({ type: 'content_block_stop', index: idx }));
      }
    }
    return events;
  }
}

function sse(obj: any): string {
  return `data: ${JSON.stringify(obj)}\n\n`;
}
