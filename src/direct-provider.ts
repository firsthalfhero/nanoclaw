export type DirectProvider = 'claude' | 'openai' | 'gemini';

export interface DirectProviderRequest {
  prompt: string;
  provider: DirectProvider;
}

export interface DirectProviderResult {
  ok: boolean;
  provider: DirectProvider;
  model: string;
  text?: string;
  error?: string;
}

export interface DirectProviderDeps {
  runClaude(prompt: string): Promise<DirectProviderResult>;
  runOpenAI(prompt: string): Promise<DirectProviderResult>;
  runGemini(prompt: string): Promise<DirectProviderResult>;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function parseDirectProviderRequest(
  text: string,
  assistantName: string,
): DirectProviderRequest | null {
  const pattern = new RegExp(
    `^(?:@${escapeRegex(assistantName)}\\s+)?please\\s+tell\\s+me\\s+(.+?)\\s+using\\s+(claude|openai|gemini)\\s*[.!?]?\\s*$`,
    'i',
  );
  const match = text.trim().match(pattern);
  if (!match) return null;

  const prompt = match[1]?.trim();
  const provider = match[2]?.toLowerCase() as DirectProvider | undefined;
  if (!prompt || !provider) return null;

  return {
    prompt,
    provider,
  };
}

export async function executeDirectProviderRequest(
  request: DirectProviderRequest,
  deps: DirectProviderDeps,
): Promise<DirectProviderResult> {
  if (request.provider === 'claude') {
    return deps.runClaude(request.prompt);
  }
  if (request.provider === 'openai') {
    return deps.runOpenAI(request.prompt);
  }
  return deps.runGemini(request.prompt);
}
