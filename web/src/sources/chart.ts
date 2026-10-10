import type { RawTrack } from '../core/types';
import { fetchHtml, htmlToText, parseNextData } from './beatport';
import { transcribeChart, transcribeFromUrl, type LlmSettings } from './llm';

export type ChartVia = 'cache' | 'direct' | 'gemini' | 'claude';
export interface ChartResult {
  tracks: RawTrack[];
  via: ChartVia;
  fetchedAt: number;
}

const TTL_MS = 6 * 60 * 60 * 1000;
const MIN_TRACKS = 10;

/** Reads a Beatport chart through the user's own proxy; falls back to a language model with the user's key. */
export async function loadChart(
  url: string,
  proxyUrl: string,
  llm: LlmSettings,
  opts: { signal?: AbortSignal; refresh?: boolean; onStatus?: (msg: string) => void },
): Promise<ChartResult> {
  const cacheKey = `chart:${url}`;
  if (!opts.refresh) {
    try {
      const raw = localStorage.getItem(cacheKey);
      if (raw) {
        const c = JSON.parse(raw) as { at: number; tracks: RawTrack[] };
        if (Date.now() - c.at < TTL_MS && c.tracks.length >= MIN_TRACKS) return { tracks: c.tracks, via: 'cache', fetchedAt: c.at };
      }
    } catch {
      /* cache unreadable: fetch again */
    }
  }

  opts.onStatus?.('Leyendo la lista de Beatport…');
  let html = '';
  let fetchError = '';
  try {
    html = await fetchHtml(url, proxyUrl, opts.signal);
  } catch (e) {
    if ((e as { name?: string }).name === 'AbortError') throw e;
    fetchError = (e as Error).message;
  }
  let tracks: RawTrack[] = html ? parseNextData(html) : [];
  let via: ChartVia = 'direct';

  if (tracks.length < MIN_TRACKS) {
    if (llm.provider === 'none') {
      throw new Error(`${fetchError || 'No pude leer los temas de la página de Beatport.'} También puedes añadir una clave de Gemini o de Claude en Avanzado.`);
    }
    const key = llm.provider === 'gemini' ? llm.geminiKey : llm.claudeKey;
    if (!key.trim()) throw new Error('Falta la clave del modelo elegido. Añádela en Avanzado.');
    const name = llm.provider === 'gemini' ? 'Gemini' : 'Claude';
    via = llm.provider;
    tracks = [];
    let lastError = '';
    if (html) {
      opts.onStatus?.(`${name} está interpretando la lista…`);
      try {
        tracks = await transcribeChart(htmlToText(html), llm, opts.signal);
      } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') throw e;
        lastError = (e as Error).message;
      }
    }
    if (tracks.length < MIN_TRACKS) {
      opts.onStatus?.(`${name} está abriendo la página desde sus servidores…`);
      try {
        tracks = await transcribeFromUrl(url, llm, opts.signal);
      } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') throw e;
        throw new Error(`${(e as Error).message}${lastError ? ` (antes: ${lastError})` : ''}`);
      }
    }
  }
  if (tracks.length < MIN_TRACKS) throw new Error(`Solo se leyeron ${tracks.length} temas de la lista. Prueba otra vez o elige otro género.`);
  const at = Date.now();
  try {
    localStorage.setItem(cacheKey, JSON.stringify({ at, tracks }));
  } catch {
    /* cache is optional */
  }
  return { tracks, via, fetchedAt: at };
}
