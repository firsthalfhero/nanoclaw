export interface GeminiFallbackResult {
  text: string;
  model: string;
  grounded: boolean;
  sources: string[];
}

export interface GeminiFallbackError {
  status: number;
  message: string;
  code?: string | number;
}

export interface GeminiFallbackResponse {
  result: GeminiFallbackResult | null;
  error: GeminiFallbackError | null;
}

type FetchLike = typeof fetch;

const GROUNDING_INSTRUCTION =
  'Use Google Search grounding for any factual claim that could be time-sensitive or stale. Base the answer on grounded search results from websites and cite the websites you used. If you cannot verify the answer with grounding, say so.';

export async function fallbackToGeminiApi(
  prompt: string,
  geminiKey: string,
  fetchImpl: FetchLike = fetch,
): Promise<GeminiFallbackResponse> {
  if (!geminiKey) {
    return { result: null, error: null };
  }

  const res = await fetchImpl(
    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': geminiKey,
      },
      body: JSON.stringify({
        contents: [
          {
            parts: [
              {
                text: `${GROUNDING_INSTRUCTION}\n\nUser request: ${prompt}`,
              },
            ],
          },
        ],
        tools: [{ google_search: {} }],
      }),
    },
  );

  if (!res.ok) {
    const json = (await res.json().catch(() => null)) as any;
    return {
      result: null,
      error: {
        status: res.status,
        message:
          json?.error?.message || `Gemini API returned HTTP ${res.status}`,
        code: json?.error?.code,
      },
    };
  }

  const json = (await res.json()) as any;
  const candidate = json?.candidates?.[0];
  const text = (
    candidate?.content?.parts?.[0]?.text as string | undefined
  )?.trim();
  const groundingMetadata = candidate?.groundingMetadata;
  const sources: string[] = Array.from(
    new Set<string>(
      (groundingMetadata?.groundingChunks || [])
        .map((chunk: any) => chunk?.web?.uri as string | undefined)
        .filter((uri: string | undefined): uri is string => Boolean(uri)),
    ),
  );
  const grounded =
    Boolean(groundingMetadata?.webSearchQueries?.length) && sources.length > 0;

  if (text && !grounded) {
    return {
      result: null,
      error: {
        status: 200,
        message:
          'Gemini returned a response without grounded website sources for a fallback request that requires fresh web verification.',
      },
    };
  }

  const sourcedText =
    text && sources.length > 0
      ? `${text}\n\nSources:\n${sources.join('\n')}`
      : text;

  return {
    result: sourcedText
      ? {
          text: sourcedText,
          model: 'Gemini 2.5 Flash',
          grounded: true,
          sources,
        }
      : null,
    error: null,
  };
}
