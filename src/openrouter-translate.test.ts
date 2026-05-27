import { describe, it, expect } from 'vitest';
import {
  translateRequestBody,
  translateResponseBody,
  StreamTranslator,
} from './openrouter-translate.js';

// ─── translateRequestBody ─────────────────────────────────────────────────────

describe('translateRequestBody', () => {
  it('translates a simple user message', () => {
    const result = translateRequestBody(
      {
        messages: [
          { role: 'user', content: [{ type: 'text', text: 'Hello' }] },
        ],
        max_tokens: 100,
      },
      'model-x',
    );
    expect(result.model).toBe('model-x');
    expect(result.messages).toEqual([{ role: 'user', content: 'Hello' }]);
    expect(result.max_tokens).toBe(100);
  });

  it('extracts system prompt into a system role message', () => {
    const result = translateRequestBody(
      {
        system: 'You are a helpful assistant.',
        messages: [{ role: 'user', content: [{ type: 'text', text: 'Hi' }] }],
        max_tokens: 50,
      },
      'model-x',
    );
    expect(result.messages[0]).toEqual({
      role: 'system',
      content: 'You are a helpful assistant.',
    });
    expect(result.messages[1]).toEqual({ role: 'user', content: 'Hi' });
  });

  it('extracts system prompt from array of text blocks', () => {
    const result = translateRequestBody(
      {
        system: [
          { type: 'text', text: 'Part one. ' },
          { type: 'text', text: 'Part two.' },
        ],
        messages: [],
        max_tokens: 50,
      },
      'model-x',
    );
    expect(result.messages[0].content).toBe('Part one. Part two.');
  });

  it('translates tool_result user messages to tool role', () => {
    const result = translateRequestBody(
      {
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'tool_result',
                tool_use_id: 'call_abc',
                content: 'tool output',
              },
            ],
          },
        ],
        max_tokens: 100,
      },
      'model-x',
    );
    expect(result.messages).toEqual([
      { role: 'tool', tool_call_id: 'call_abc', content: 'tool output' },
    ]);
  });

  it('translates assistant tool_use blocks to tool_calls', () => {
    const result = translateRequestBody(
      {
        messages: [
          {
            role: 'assistant',
            content: [
              {
                type: 'tool_use',
                id: 'call_1',
                name: 'get_weather',
                input: { city: 'Sydney' },
              },
            ],
          },
        ],
        max_tokens: 100,
      },
      'model-x',
    );
    expect(result.messages[0].tool_calls).toEqual([
      {
        id: 'call_1',
        type: 'function',
        function: {
          name: 'get_weather',
          arguments: JSON.stringify({ city: 'Sydney' }),
        },
      },
    ]);
  });

  it('passes thinking blocks back as reasoning_details (text)', () => {
    const result = translateRequestBody(
      {
        messages: [
          {
            role: 'assistant',
            content: [
              { type: 'thinking', thinking: 'Let me reason...', signature: '' },
              { type: 'text', text: 'The answer is 42.' },
            ],
          },
        ],
        max_tokens: 100,
      },
      'model-x',
    );
    expect(result.messages[0].reasoning_details).toEqual([
      { type: 'reasoning.text', text: 'Let me reason...' },
    ]);
    expect(result.messages[0].content).toBe('The answer is 42.');
  });

  it('passes encrypted thinking blocks back as reasoning.encrypted', () => {
    const result = translateRequestBody(
      {
        messages: [
          {
            role: 'assistant',
            content: [
              {
                type: 'thinking',
                thinking: '',
                signature: 'encrypted-blob-abc',
              },
            ],
          },
        ],
        max_tokens: 100,
      },
      'model-x',
    );
    expect(result.messages[0].reasoning_details).toEqual([
      { type: 'reasoning.encrypted', data: 'encrypted-blob-abc' },
    ]);
  });

  it('includes reasoning config when provided', () => {
    const result = translateRequestBody(
      { messages: [], max_tokens: 100 },
      'model-x',
      { effort: 'high' },
    );
    expect(result.reasoning).toEqual({ effort: 'high' });
  });

  it('includes reasoning max_tokens when provided', () => {
    const result = translateRequestBody(
      { messages: [], max_tokens: 100 },
      'model-x',
      { max_tokens: 2000 },
    );
    expect(result.reasoning).toEqual({ max_tokens: 2000 });
  });

  it('omits reasoning field when no config provided', () => {
    const result = translateRequestBody(
      { messages: [], max_tokens: 100 },
      'model-x',
    );
    expect(result.reasoning).toBeUndefined();
  });

  it('adds stream_options for streaming requests', () => {
    const result = translateRequestBody(
      { messages: [], max_tokens: 100, stream: true },
      'model-x',
    );
    expect(result.stream).toBe(true);
    expect(result.stream_options).toEqual({ include_usage: true });
  });

  it('omits stream_options for non-streaming requests', () => {
    const result = translateRequestBody(
      { messages: [], max_tokens: 100, stream: false },
      'model-x',
    );
    expect(result.stream_options).toBeUndefined();
  });
});

// ─── translateResponseBody ────────────────────────────────────────────────────

describe('translateResponseBody', () => {
  it('translates a simple text response', () => {
    const result = translateResponseBody({
      id: 'chatcmpl-1',
      model: 'model-x',
      choices: [
        {
          message: { role: 'assistant', content: 'Hello!' },
          finish_reason: 'stop',
        },
      ],
      usage: { prompt_tokens: 10, completion_tokens: 5 },
    });

    expect(result.type).toBe('message');
    expect(result.role).toBe('assistant');
    expect(result.content).toEqual([{ type: 'text', text: 'Hello!' }]);
    expect(result.stop_reason).toBe('end_turn');
    expect(result.usage).toEqual({ input_tokens: 10, output_tokens: 5 });
  });

  it('maps finish_reason tool_calls → stop_reason tool_use', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: { role: 'assistant', content: null, tool_calls: [] },
          finish_reason: 'tool_calls',
        },
      ],
    });
    expect(result.stop_reason).toBe('tool_use');
  });

  it('maps finish_reason length → stop_reason max_tokens', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: { role: 'assistant', content: 'truncated' },
          finish_reason: 'length',
        },
      ],
    });
    expect(result.stop_reason).toBe('max_tokens');
  });

  it('translates tool_calls to tool_use content blocks', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: {
            role: 'assistant',
            content: null,
            tool_calls: [
              {
                id: 'call_1',
                function: {
                  name: 'get_weather',
                  arguments: JSON.stringify({ city: 'Sydney' }),
                },
              },
            ],
          },
          finish_reason: 'tool_calls',
        },
      ],
    });
    expect(result.content).toEqual([
      {
        type: 'tool_use',
        id: 'call_1',
        name: 'get_weather',
        input: { city: 'Sydney' },
      },
    ]);
  });

  it('translates reasoning_details text blocks to thinking content blocks', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: {
            role: 'assistant',
            content: 'The answer.',
            reasoning_details: [
              { type: 'reasoning.text', text: 'Let me think.' },
            ],
          },
          finish_reason: 'stop',
        },
      ],
    });
    expect(result.content[0]).toEqual({
      type: 'thinking',
      thinking: 'Let me think.',
      signature: '',
    });
    expect(result.content[1]).toEqual({ type: 'text', text: 'The answer.' });
  });

  it('translates reasoning_details summary blocks to thinking content blocks', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: {
            role: 'assistant',
            content: 'Ok.',
            reasoning_details: [
              { type: 'reasoning.summary', text: 'Summary of reasoning.' },
            ],
          },
          finish_reason: 'stop',
        },
      ],
    });
    expect(result.content[0].type).toBe('thinking');
    expect(result.content[0].thinking).toBe('Summary of reasoning.');
  });

  it('translates reasoning_details encrypted blocks', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: {
            role: 'assistant',
            content: 'Ok.',
            reasoning_details: [
              { type: 'reasoning.encrypted', data: 'blob123' },
            ],
          },
          finish_reason: 'stop',
        },
      ],
    });
    expect(result.content[0]).toEqual({
      type: 'thinking',
      thinking: '',
      signature: 'blob123',
    });
  });

  it('places reasoning blocks before text blocks', () => {
    const result = translateResponseBody({
      choices: [
        {
          message: {
            role: 'assistant',
            content: 'Answer.',
            reasoning_details: [{ type: 'reasoning.text', text: 'Thinking.' }],
          },
          finish_reason: 'stop',
        },
      ],
    });
    expect(result.content[0].type).toBe('thinking');
    expect(result.content[1].type).toBe('text');
  });
});

// ─── StreamTranslator ─────────────────────────────────────────────────────────

function parseEvents(lines: string[]): any[] {
  return lines
    .map((l) => {
      if (!l.startsWith('data: ')) return null;
      try {
        return JSON.parse(l.slice(6));
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

describe('StreamTranslator', () => {
  it('emits message_start on the first chunk', () => {
    const t = new StreamTranslator();
    const lines = t.processLine(
      'data: ' +
        JSON.stringify({
          id: 'cmpl-1',
          model: 'model-x',
          choices: [{ delta: { role: 'assistant' }, finish_reason: null }],
        }),
    );
    const events = parseEvents(lines);
    expect(events[0].type).toBe('message_start');
    expect(events[0].message.role).toBe('assistant');
    expect(events[0].message.model).toBe('model-x');
  });

  it('emits content_block events for text deltas', () => {
    const t = new StreamTranslator();
    // First chunk emits message_start
    t.processLine(
      'data: ' +
        JSON.stringify({
          model: 'x',
          choices: [{ delta: { role: 'assistant' } }],
        }),
    );
    const lines = t.processLine(
      'data: ' +
        JSON.stringify({
          choices: [{ delta: { content: 'Hello' } }],
        }),
    );
    const events = parseEvents(lines);
    const start = events.find((e) => e.type === 'content_block_start');
    const delta = events.find((e) => e.type === 'content_block_delta');
    expect(start?.content_block.type).toBe('text');
    expect(delta?.delta.type).toBe('text_delta');
    expect(delta?.delta.text).toBe('Hello');
  });

  it('emits message_stop on [DONE]', () => {
    const t = new StreamTranslator();
    t.processLine(
      'data: ' +
        JSON.stringify({
          model: 'x',
          choices: [{ delta: { role: 'assistant' } }],
        }),
    );
    const lines = t.processLine('data: [DONE]');
    const events = parseEvents(lines);
    expect(events.some((e) => e.type === 'message_stop')).toBe(true);
  });

  it('emits thinking blocks for reasoning_details deltas', () => {
    const t = new StreamTranslator();
    t.processLine(
      'data: ' +
        JSON.stringify({
          model: 'x',
          choices: [{ delta: { role: 'assistant' } }],
        }),
    );
    const lines = t.processLine(
      'data: ' +
        JSON.stringify({
          choices: [
            {
              delta: {
                reasoning_details: [
                  { type: 'reasoning.text', text: 'Thinking...' },
                ],
              },
            },
          ],
        }),
    );
    const events = parseEvents(lines);
    const start = events.find((e) => e.type === 'content_block_start');
    const delta = events.find((e) => e.type === 'content_block_delta');
    expect(start?.content_block.type).toBe('thinking');
    expect(delta?.delta.type).toBe('thinking_delta');
    expect(delta?.delta.thinking).toBe('Thinking...');
  });

  it('closes thinking block before opening text block', () => {
    const t = new StreamTranslator();
    t.processLine(
      'data: ' +
        JSON.stringify({
          model: 'x',
          choices: [{ delta: { role: 'assistant' } }],
        }),
    );
    // Reasoning chunk
    t.processLine(
      'data: ' +
        JSON.stringify({
          choices: [
            {
              delta: {
                reasoning_details: [{ type: 'reasoning.text', text: 'think' }],
              },
            },
          ],
        }),
    );
    // Text chunk
    const lines = t.processLine(
      'data: ' +
        JSON.stringify({ choices: [{ delta: { content: 'answer' } }] }),
    );
    const events = parseEvents(lines);
    const stopIdx = events.findIndex((e) => e.type === 'content_block_stop');
    const startIdx = events.findIndex((e) => e.type === 'content_block_start');
    // thinking block must stop before text block starts
    expect(stopIdx).toBeLessThan(startIdx);
  });

  it('emits thinking and text blocks at separate indices', () => {
    const t = new StreamTranslator();
    t.processLine(
      'data: ' +
        JSON.stringify({
          model: 'x',
          choices: [{ delta: { role: 'assistant' } }],
        }),
    );
    const thinkLines = t.processLine(
      'data: ' +
        JSON.stringify({
          choices: [
            {
              delta: {
                reasoning_details: [{ type: 'reasoning.text', text: 'think' }],
              },
            },
          ],
        }),
    );
    const textLines = t.processLine(
      'data: ' + JSON.stringify({ choices: [{ delta: { content: 'text' } }] }),
    );

    const thinkEvents = parseEvents(thinkLines);
    const textEvents = parseEvents(textLines);

    const thinkStart = thinkEvents.find(
      (e) => e.type === 'content_block_start',
    );
    const textStart = textEvents.find((e) => e.type === 'content_block_start');
    expect(thinkStart?.index).not.toBe(textStart?.index);
  });

  it('translates finish_reason tool_calls to stop_reason tool_use', () => {
    const t = new StreamTranslator();
    t.processLine(
      'data: ' +
        JSON.stringify({
          model: 'x',
          choices: [{ delta: { role: 'assistant' } }],
        }),
    );
    const lines = t.processLine(
      'data: ' +
        JSON.stringify({
          choices: [{ delta: {}, finish_reason: 'tool_calls' }],
        }),
    );
    const events = parseEvents(lines);
    const msgDelta = events.find((e) => e.type === 'message_delta');
    expect(msgDelta?.delta.stop_reason).toBe('tool_use');
  });
});
