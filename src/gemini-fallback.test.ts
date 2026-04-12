import { describe, expect, it, vi } from 'vitest';

import { fallbackToGeminiApi } from './gemini-fallback.js';

describe('fallbackToGeminiApi', () => {
  it('calls the current Gemini generateContent endpoint with header auth', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        candidates: [
          {
            content: {
              parts: [{ text: 'Joe Biden' }],
            },
          },
        ],
      }),
    });

    const result = await fallbackToGeminiApi(
      'Who is the President of the USA?',
      'test-key',
      fetchMock as any,
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-goog-api-key': 'test-key',
        },
      }),
    );

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      contents: [{ parts: [{ text: 'Who is the President of the USA?' }] }],
    });
    expect(result).toEqual({
      result: {
        text: 'Joe Biden',
        model: 'Gemini 2.5 Flash',
      },
      error: null,
    });
  });

  it('returns status and error details when Gemini responds with an error', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        error: {
          code: 404,
          message: 'models/gemini-1.5-flash is not found.',
        },
      }),
    });

    await expect(
      fallbackToGeminiApi('test prompt', 'test-key', fetchMock as any),
    ).resolves.toEqual({
      result: null,
      error: {
        status: 404,
        message: 'models/gemini-1.5-flash is not found.',
        code: 404,
      },
    });
  });
});
