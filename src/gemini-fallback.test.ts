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
              parts: [{ text: 'Grounded answer' }],
            },
            groundingMetadata: {
              webSearchQueries: ['current president of the usa'],
              groundingChunks: [{ web: { uri: 'https://example.com' } }],
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
      contents: [
        {
          parts: [
            {
              text: 'Use Google Search grounding for any factual claim that could be time-sensitive or stale. Base the answer on grounded search results from websites and cite the websites you used. If you cannot verify the answer with grounding, say so.\n\nUser request: Who is the President of the USA?',
            },
          ],
        },
      ],
      tools: [{ google_search: {} }],
    });
    expect(result).toEqual({
      result: {
        text: 'Grounded answer\n\nSources:\nhttps://example.com',
        model: 'Gemini 2.5 Flash',
        grounded: true,
        sources: ['https://example.com'],
      },
      error: null,
    });
  });

  it('rejects successful but ungrounded responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        candidates: [
          {
            content: {
              parts: [{ text: 'Ungrounded answer' }],
            },
          },
        ],
      }),
    });

    await expect(
      fallbackToGeminiApi(
        'Who is the President of the USA?',
        'test-key',
        fetchMock as any,
      ),
    ).resolves.toEqual({
      result: null,
      error: {
        status: 200,
        message:
          'Gemini returned a response without grounded website sources for a fallback request that requires fresh web verification.',
      },
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
