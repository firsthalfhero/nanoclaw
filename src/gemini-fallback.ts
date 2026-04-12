export interface GeminiFallbackResult {
  text: string;
  model: string;
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
        contents: [{ parts: [{ text: prompt }] }],
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
  const text = (
    json?.candidates?.[0]?.content?.parts?.[0]?.text as string | undefined
  )?.trim();

  return {
    result: text ? { text, model: 'Gemini 2.5 Flash' } : null,
    error: null,
  };
}
