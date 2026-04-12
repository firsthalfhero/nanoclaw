import { describe, expect, it, vi } from 'vitest';

import { fallbackToOpenAI } from './openai-fallback.js';

describe('fallbackToOpenAI', () => {
  it('calls the current chat completions endpoint with gpt-4o-mini', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        choices: [{ message: { content: 'OK' } }],
      }),
    });

    const result = await fallbackToOpenAI(
      'Reply with exactly: OK',
      'test-key',
      fetchMock as any,
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.openai.com/v1/chat/completions',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer test-key',
        },
      }),
    );

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
      max_tokens: 4096,
    });
    expect(result).toEqual({
      result: {
        text: 'OK',
        model: 'GPT-4o mini',
      },
      error: null,
    });
  });

  it('returns status and error details when the API responds with an error', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        error: {
          code: 'model_not_found',
          message: 'The model does not exist.',
        },
      }),
    });

    await expect(
      fallbackToOpenAI('test prompt', 'test-key', fetchMock as any),
    ).resolves.toEqual({
      result: null,
      error: {
        status: 404,
        message: 'The model does not exist.',
        code: 'model_not_found',
      },
    });
  });
});
