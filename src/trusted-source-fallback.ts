export interface TrustedSourceFallbackResult {
  text: string;
  model: string;
}

type FetchLike = typeof fetch;

const WHITE_HOUSE_ADMIN_URL = 'https://www.whitehouse.gov/administration/';

function formatSlugName(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map((part) => {
      if (part.length === 1) return part.toUpperCase();
      return part[0].toUpperCase() + part.slice(1);
    })
    .join(' ');
}

function parseWhiteHousePresident(html: string): string | null {
  const match =
    html.match(
      /href=["']https?:\/\/www\.whitehouse\.gov\/administration\/([a-z-]+)\/["']/i,
    ) || html.match(/href=["']\/administration\/([a-z-]+)\/["']/i);
  if (!match?.[1]) return null;
  return formatSlugName(match[1]);
}

function isCurrentUsPresidentQuestion(prompt: string): boolean {
  return /who\s+is\s+the\s+(current\s+)?president\s+of\s+(the\s+)?(usa|us|united states)/i.test(
    prompt,
  );
}

export async function fallbackToTrustedSource(
  prompt: string,
  fetchImpl: FetchLike = fetch,
): Promise<TrustedSourceFallbackResult | null> {
  if (!isCurrentUsPresidentQuestion(prompt)) return null;

  const res = await fetchImpl(WHITE_HOUSE_ADMIN_URL);
  if (!res.ok) return null;

  const html = await res.text();
  const president = parseWhiteHousePresident(html);
  if (!president) return null;

  return {
    text:
      `According to the White House administration page, the current President of the United States is ${president}.` +
      `\n\nSource:\n${WHITE_HOUSE_ADMIN_URL}`,
    model: 'Trusted source fetch',
  };
}

export const _internal = {
  formatSlugName,
  parseWhiteHousePresident,
  isCurrentUsPresidentQuestion,
};
