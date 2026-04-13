import { describe, expect, it, vi } from 'vitest';

import {
  executeDirectProviderRequest,
  parseDirectProviderRequest,
} from './direct-provider.js';

describe('parseDirectProviderRequest', () => {
  it('parses a basic direct-provider request', () => {
    expect(
      parseDirectProviderRequest(
        'please tell me who is the president of the usa using Gemini',
        'Pip',
      ),
    ).toEqual({
      prompt: 'who is the president of the usa',
      provider: 'gemini',
    });
  });

  it('parses an optional trigger prefix', () => {
    expect(
      parseDirectProviderRequest(
        '@Pip please tell me write a haiku using Claude',
        'Pip',
      ),
    ).toEqual({
      prompt: 'write a haiku',
      provider: 'claude',
    });
  });

  it('returns null for unrelated text', () => {
    expect(
      parseDirectProviderRequest('please summarize this chat', 'Pip'),
    ).toBeNull();
  });
});

describe('executeDirectProviderRequest', () => {
  it('dispatches to claude only', async () => {
    const runClaude = vi.fn().mockResolvedValue({
      ok: true,
      provider: 'claude',
      model: 'Claude',
      text: 'ok',
    });
    const runOpenAI = vi.fn();
    const runGemini = vi.fn();

    const result = await executeDirectProviderRequest(
      { prompt: 'write a haiku', provider: 'claude' },
      { runClaude, runOpenAI: runOpenAI as any, runGemini: runGemini as any },
    );

    expect(runClaude).toHaveBeenCalledWith('write a haiku');
    expect(runOpenAI).not.toHaveBeenCalled();
    expect(runGemini).not.toHaveBeenCalled();
    expect(result).toEqual({
      ok: true,
      provider: 'claude',
      model: 'Claude',
      text: 'ok',
    });
  });

  it('dispatches to openai only', async () => {
    const runClaude = vi.fn();
    const runOpenAI = vi.fn().mockResolvedValue({
      ok: true,
      provider: 'openai',
      model: 'GPT-4',
      text: 'ok',
    });
    const runGemini = vi.fn();

    const result = await executeDirectProviderRequest(
      { prompt: 'write a haiku', provider: 'openai' },
      { runClaude: runClaude as any, runOpenAI, runGemini: runGemini as any },
    );

    expect(runOpenAI).toHaveBeenCalledWith('write a haiku');
    expect(runClaude).not.toHaveBeenCalled();
    expect(runGemini).not.toHaveBeenCalled();
    expect(result).toEqual({
      ok: true,
      provider: 'openai',
      model: 'GPT-4',
      text: 'ok',
    });
  });

  it('dispatches to gemini only', async () => {
    const runClaude = vi.fn();
    const runOpenAI = vi.fn();
    const runGemini = vi.fn().mockResolvedValue({
      ok: true,
      provider: 'gemini',
      model: 'Gemini 2.5 Flash',
      text: 'ok',
    });

    const result = await executeDirectProviderRequest(
      { prompt: 'write a haiku', provider: 'gemini' },
      { runClaude: runClaude as any, runOpenAI: runOpenAI as any, runGemini },
    );

    expect(runGemini).toHaveBeenCalledWith('write a haiku');
    expect(runClaude).not.toHaveBeenCalled();
    expect(runOpenAI).not.toHaveBeenCalled();
    expect(result).toEqual({
      ok: true,
      provider: 'gemini',
      model: 'Gemini 2.5 Flash',
      text: 'ok',
    });
  });
});
