import type { RawTrack } from '../core/types';

/**
 * Browsers cannot read beatport.com directly (no CORS headers), so the page is fetched through a proxy
 * the user runs themselves (see worker/beatport-proxy.js). The proxy receives the target as ?url=...
 */
export async function fetchHtml(url: string, proxyUrl: string, signal?: AbortSignal): Promise<string> {
  if (!proxyUrl.trim()) {
    throw new Error('El navegador no puede leer Beatport directamente. Configura tu propio proxy en Avanzado, o usa tu biblioteca.');
  }
  const sep = proxyUrl.includes('?') ? '&' : '?';
  const res = await fetch(`${proxyUrl}${sep}url=${encodeURIComponent(url)}`, { signal });
  if (!res.ok) throw new Error(`El proxy respondió con el código ${res.status}.`);
  return res.text();
}

const asRecord = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;

function keyFrom(v: unknown): string | null {
  if (typeof v === 'string') return v;
  const o = asRecord(v);
  if (!o) return null;
  const num = o.camelot_number;
  const letter = o.camelot_letter;
  if ((typeof num === 'number' || typeof num === 'string') && typeof letter === 'string') return `${num}${letter}`;
  if (typeof o.name === 'string') return o.name;
  if (typeof o.short_name === 'string') return o.short_name;
  return null;
}

function trackFrom(o: Record<string, unknown>): RawTrack | null {
  if (typeof o.name !== 'string' || !Array.isArray(o.artists)) return null;
  const bpm = typeof o.bpm === 'number' ? o.bpm : typeof o.bpm === 'string' ? Number(o.bpm) : NaN;
  if (!Number.isFinite(bpm)) return null;
  const artists = o.artists
    .map((a) => (typeof a === 'string' ? a : asRecord(a)?.name))
    .filter((a): a is string => typeof a === 'string' && a.length > 0);
  if (!artists.length) return null;
  const genre = asRecord(o.genre)?.name;
  const start = typeof o.sample_start_ms === 'number' ? o.sample_start_ms : null;
  return {
    previewUrl: typeof o.sample_url === 'string' && o.sample_url.startsWith('https://') ? o.sample_url : null,
    previewStartMs: start,
    artists,
    title: o.name,
    mix: typeof o.mix_name === 'string' ? o.mix_name : null,
    genre: typeof genre === 'string' ? genre : null,
    bpm,
    key: keyFrom(o.key),
  };
}

/**
 * Reads the tracks embedded in the page's __NEXT_DATA__ JSON.
 * Walks the whole structure looking for track-shaped objects so it does not depend on one exact path.
 */
export function parseNextData(html: string): RawTrack[] {
  const m = /<script[^>]*id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/.exec(html);
  if (!m) return [];
  let data: unknown;
  try {
    data = JSON.parse(m[1]);
  } catch {
    return [];
  }
  const out: RawTrack[] = [];
  const seen = new Set<string>();
  const visit = (node: unknown, depth: number): void => {
    if (depth > 40 || node == null || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const x of node) visit(x, depth + 1);
      return;
    }
    const o = node as Record<string, unknown>;
    const t = trackFrom(o);
    if (t) {
      const id = o.id != null ? String(o.id) : `${t.artists.join(',')}|${t.title}|${t.mix ?? ''}`;
      if (!seen.has(id)) {
        seen.add(id);
        out.push(t);
      }
      return;
    }
    for (const v of Object.values(o)) visit(v, depth + 1);
  };
  visit(data, 0);
  return out;
}

const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

/** Visible text of an HTML page, one block per line. Used to give a language model a small input. */
export function htmlToText(html: string, maxChars = 60000): string {
  const text = html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<\/(tr|li|div|p|h[1-6]|section|article|a)>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#(\d+);/g, (_, d: string) => String.fromCodePoint(Number(d)))
    .replace(/&#x([0-9a-f]+);/gi, (_, h: string) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&([a-z]+);/gi, (whole, name: string) => ENTITIES[name.toLowerCase()] ?? whole);
  return text
    .split('\n')
    .map((l) => l.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .join('\n')
    .slice(0, maxChars);
}
