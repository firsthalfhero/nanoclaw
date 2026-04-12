import { describe, expect, it, vi } from 'vitest';

import {
  _internal,
  fallbackToTrustedSource,
} from './trusted-source-fallback.js';

describe('trusted-source-fallback', () => {
  it('detects questions about the current US president', () => {
    expect(
      _internal.isCurrentUsPresidentQuestion(
        'Who is the President of the USA?',
      ),
    ).toBe(true);
    expect(
      _internal.isCurrentUsPresidentQuestion(
        'Tell me about the US constitution',
      ),
    ).toBe(false);
  });

  it('parses the current president from the White House administration page', () => {
    const html = `
      <html>
        <body>
          <a href="/administration/donald-j-trump/">Donald J. Trump</a>
        </body>
      </html>
    `;

    expect(_internal.parseWhiteHousePresident(html)).toBe('Donald J Trump');
  });

  it('returns a trusted-source answer for current US president questions', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () =>
        '<a href="/administration/donald-j-trump/">Donald J. Trump</a>',
    });

    await expect(
      fallbackToTrustedSource(
        'Who is the President of the USA?',
        fetchMock as any,
      ),
    ).resolves.toEqual({
      text: 'According to the White House administration page, the current President of the United States is Donald J Trump.\n\nSource:\nhttps://www.whitehouse.gov/administration/',
      model: 'Trusted source fetch',
    });
  });

  it('skips unrelated prompts', async () => {
    const fetchMock = vi.fn();

    await expect(
      fallbackToTrustedSource(
        'What is the capital of France?',
        fetchMock as any,
      ),
    ).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
