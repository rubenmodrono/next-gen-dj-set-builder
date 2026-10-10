/** Lowercase, accent-free, no brackets, no punctuation. */
export function normalizeText(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\(.*?\)|\[.*?\]/g, ' ')
    .replace(/\b(feat|ft|featuring)\b.*$/, ' ')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function bigrams(s: string): Map<string, number> {
  const m = new Map<string, number>();
  for (let i = 0; i < s.length - 1; i++) {
    const g = s.slice(i, i + 2);
    m.set(g, (m.get(g) ?? 0) + 1);
  }
  return m;
}

/** Dice coefficient on character bigrams, 0..1. Inputs are normalised first. */
export function similarity(a: string, b: string): number {
  const x = normalizeText(a);
  const y = normalizeText(b);
  if (!x || !y) return 0;
  if (x === y) return 1;
  if (x.length < 2 || y.length < 2) return 0;
  const bx = bigrams(x);
  const by = bigrams(y);
  let hit = 0;
  for (const [g, n] of bx) hit += Math.min(n, by.get(g) ?? 0);
  return (2 * hit) / (x.length - 1 + (y.length - 1));
}

/** True when the lead artist of the wanted track appears in the candidate's artist text. */
export function artistMatches(wantedLead: string, candidate: string): boolean {
  const w = normalizeText(wantedLead);
  const c = normalizeText(candidate);
  if (!w || !c) return false;
  return c.includes(w) || w.includes(c) || similarity(w, c) >= 0.8;
}
