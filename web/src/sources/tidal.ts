import { songKeyOf } from '../core/planner';
import type { RawTrack } from '../core/types';

/** Dirección de la función de Cloudflare que habla con Tidal (ver functions/tidal.js), relativa a la página. */
export const TIDAL_ENDPOINT = 'tidal';

/** True when this site ships the Tidal reader AND the server has credentials (X-SP-Tidal: 1). */
export async function probeTidal(signal?: AbortSignal): Promise<boolean> {
  try {
    const res = await fetch(`${TIDAL_ENDPOINT}?probe=1`, { signal });
    return res.headers.get('x-sp-tidal') === '1';
  } catch {
    return false;
  }
}

/* ───────────── JSON:API → RawTrack ───────────── */

interface Resource {
  id?: unknown;
  type?: unknown;
  attributes?: Record<string, unknown>;
  relationships?: Record<string, { data?: unknown; links?: { next?: unknown } } | undefined>;
}

const isObj = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);

/** Tidal sends the root as a letter plus an optional accidental ("C", "Ab", "CSharp"...) and the mode apart. */
export function tidalKeyToString(key: unknown, scale: unknown): string | null {
  if (typeof key !== 'string') return null;
  const m = /^([A-Ga-g])\s*(sharp|flat|#|b|♯|♭)?$/i.exec(key.trim());
  if (!m) return null;
  const acc = (m[2] ?? '').toLowerCase();
  const accidental = acc === 'sharp' || acc === '#' || acc === '♯' ? '#' : acc === 'flat' || acc === 'b' || acc === '♭' ? 'b' : '';
  const mode = typeof scale === 'string' ? scale.trim().toLowerCase() : '';
  if (mode !== 'major' && mode !== 'minor') return null;
  return `${m[1].toUpperCase()}${accidental} ${mode === 'minor' ? 'Minor' : 'Major'}`;
}

export interface TidalParsed {
  tracks: (RawTrack & { tidalId: string })[];
  /** Ids of tracks whose artist names did not come in the response (they are asked for separately). */
  needArtists: string[];
  /** Cursor for the next page of results, or null. */
  next: string | null;
}

function cursorFrom(link: unknown): string | null {
  if (typeof link !== 'string') return null;
  try {
    return new URL(link, 'https://openapi.tidal.com').searchParams.get('page[cursor]');
  } catch {
    return null;
  }
}

export function parseTidalResponse(payload: unknown): TidalParsed {
  const empty: TidalParsed = { tracks: [], needArtists: [], next: null };
  if (!isObj(payload)) return empty;
  const data = payload.data;
  const included = Array.isArray(payload.included) ? payload.included : [];
  const all = [...(Array.isArray(data) ? data : data ? [data] : []), ...included].filter(isObj) as Resource[];

  const byKey = new Map<string, Resource>();
  for (const r of all) if (typeof r.type === 'string' && r.id != null) byKey.set(`${r.type}:${String(r.id)}`, r);

  const out: TidalParsed = { tracks: [], needArtists: [], next: null };
  const seen = new Set<string>();
  for (const r of all) {
    if (r.type !== 'tracks' || r.id == null) continue;
    const id = String(r.id);
    if (seen.has(id)) continue;
    seen.add(id);
    const a = r.attributes ?? {};
    const title = typeof a.title === 'string' ? a.title.trim() : '';
    if (!title) continue;
    const rel = r.relationships?.artists?.data;
    const artists = (Array.isArray(rel) ? rel : [])
      .filter(isObj)
      .map((ref) => {
        const name = byKey.get(`artists:${String(ref.id)}`)?.attributes?.name;
        return typeof name === 'string' ? name.trim() : '';
      })
      .filter(Boolean);
    if (!artists.length) out.needArtists.push(id);
    const bpm = typeof a.bpm === 'number' && a.bpm > 0 ? Math.round(a.bpm * 100) / 100 : null;
    out.tracks.push({
      tidalId: id,
      artists,
      title,
      mix: typeof a.version === 'string' && a.version.trim() ? a.version.trim() : null,
      genre: null,
      bpm,
      key: tidalKeyToString(a.key, a.keyScale),
    });
  }

  // Pagination: the link sits either at the top level or on the "tracks" relationship of the search result.
  const top = isObj(payload.links) ? cursorFrom(payload.links.next) : null;
  const viaRel = (Array.isArray(data) ? data : [data]).filter(isObj).map((d) => cursorFrom((d as Resource).relationships?.tracks?.links?.next)).find(Boolean) ?? null;
  out.next = top ?? viaRel;
  return out;
}

/* ───────────── carga ───────────── */

const TTL_MS = 6 * 60 * 60 * 1000;
const VARIANTS = ['', ' extended mix', ' original mix', ' remix', ' club mix'];
const EXTRA_PAGES = 2;

async function call(query: string, signal?: AbortSignal): Promise<unknown> {
  const res = await fetch(`${TIDAL_ENDPOINT}?${query}`, { signal });
  if (res.status === 501 || res.headers.get('x-sp-tidal') === '0') throw new Error('Tidal no está configurado en este servidor. Añade las credenciales en Cloudflare (ver README).');
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.text()).slice(0, 200); } catch { /* sin detalle */ }
    throw new Error(`Tidal respondió con el código ${res.status}.${detail ? ` ${detail}` : ''}`);
  }
  return res.json();
}

export interface TidalPool {
  tracks: RawTrack[];
  fetchedAt: number;
}

/** Builds a pool of tracks with Tidal's own BPM and key for a search term (several wordings, a few pages each). */
export async function loadTidalPool(
  term: string,
  opts: { signal?: AbortSignal; refresh?: boolean; onStatus?: (msg: string) => void },
): Promise<TidalPool> {
  const cacheKey = `tidal:${term.toLowerCase()}`;
  if (!opts.refresh) {
    try {
      const raw = localStorage.getItem(cacheKey);
      if (raw) {
        const c = JSON.parse(raw) as { at: number; tracks: RawTrack[] };
        if (Date.now() - c.at < TTL_MS && c.tracks.length >= 10) return { tracks: c.tracks, fetchedAt: c.at };
      }
    } catch { /* caché ilegible: se vuelve a pedir */ }
  }

  const found = new Map<string, RawTrack & { tidalId: string }>();
  const missing = new Set<string>();
  let firstError: Error | null = null;
  for (const [i, extra] of VARIANTS.entries()) {
    opts.onStatus?.(`Buscando en Tidal (${i + 1}/${VARIANTS.length})…`);
    let cursor: string | null = null;
    for (let page = 0; page <= EXTRA_PAGES; page++) {
      try {
        const q = `q=${encodeURIComponent(term + extra)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`;
        const parsed = parseTidalResponse(await call(q, opts.signal));
        for (const t of parsed.tracks) {
          if (!found.has(t.tidalId)) found.set(t.tidalId, t);
          if (!t.artists.length) missing.add(t.tidalId);
        }
        cursor = parsed.next;
      } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') throw e;
        if (!found.size && !firstError) firstError = e as Error;
        cursor = null;
      }
      if (!cursor) break;
    }
    if (i === 0 && !found.size && firstError) throw firstError;
  }

  const ids = [...missing];
  for (let i = 0; i < ids.length; i += 20) {
    opts.onStatus?.('Completando artistas…');
    try {
      const parsed = parseTidalResponse(await call(`ids=${ids.slice(i, i + 20).join(',')}`, opts.signal));
      for (const t of parsed.tracks) {
        const cur = found.get(t.tidalId);
        if (cur && t.artists.length) cur.artists = t.artists;
      }
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') throw e;
    }
  }

  const seen = new Set<string>();
  const tracks: RawTrack[] = [];
  for (const { tidalId: _id, ...t } of found.values()) {
    if (!t.artists.length) continue;
    const k = songKeyOf(t.artists.join(', '), `${t.title} ${t.mix ?? ''}`);
    if (seen.has(k)) continue;
    seen.add(k);
    tracks.push(t);
  }
  if (!tracks.length) throw new Error(`Tidal no devolvió temas para «${term}». Prueba con otra búsqueda.`);
  const at = Date.now();
  try { localStorage.setItem(cacheKey, JSON.stringify({ at, tracks })); } catch { /* la caché es opcional */ }
  return { tracks, fetchedAt: at };
}
