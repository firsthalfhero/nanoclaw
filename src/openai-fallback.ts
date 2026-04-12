export interface OpenAIFallbackResult {
  text: string;
  model: string;
}

export interface OpenAIFallbackError {
  status: number;
  message: string;
  code?: string;
}

export interface OpenAIFallbackResponse {
  result: OpenAIFallbackResult | null;
  error: OpenAIFallbackError | null;
}

type FetchLike = typeof fetch;

export async function fallbackToOpenAI(
  prompt: string,
  openaiKey: string,
  fetchImpl: FetchLike = fetch,
): Promise<OpenAIFallbackResponse> {
  if (!openaiKey) {
    return { result: null, error: null };
  }

  const res = await fetchImpl('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${openaiKey}`,
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 4096,
    }),
  });

  if (!res.ok) {
    const json = (await res.json().catch(() => null)) as any;
    return {
      result: null,
      error: {
        status: res.status,
        message:
          json?.error?.message || `OpenAI API returned HTTP ${res.status}`,
        code: json?.error?.code,
      },
    };
  }

  const json = (await res.json()) as any;
  const text = json?.choices?.[0]?.message?.content?.trim();
  return {
    result: text ? { text, model: 'GPT-4o mini' } : null,
    error: null,
  };
}
