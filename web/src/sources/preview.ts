import { artistMatches, similarity } from '../core/match';
import type { Track } from '../core/types';

export type PreviewSource = 'beatport' | 'deezer' | 'itunes';
export interface Preview {
  url: string;
  source: PreviewSource;
  startMs: number;
}

const TITLE_MIN = 0.78;

interface Candidate { artist: string; title: string; url: string }

function best(track: Track, list: Candidate[]): Candidate | null {
  const lead = track.artist.split(',')[0].trim();
  let pick: Candidate | null = null;
  let score = 0;
  for (const c of list) {
    if (!c.url || !artistMatches(lead, c.artist)) continue;
    const s = similarity(track.title, c.title);
    if (s >= TITLE_MIN && s > score) {
      score = s;
      pick = c;
    }
  }
  return pick;
}

let seq = 0;

/**
 * Both the iTunes Search API and Deezer's API answer with a JSONP callback, which a web page may load
 * from another origin without CORS. The audio itself is played with a plain <audio> element.
 */
function jsonp<T>(url: string, callbackParam: string, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const name = `__sp_cb_${Date.now()}_${seq++}`;
    const w = window as unknown as Record<string, unknown>;
    const script = document.createElement('script');
    const done = (): void => {
      delete w[name];
      script.remove();
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    };
    const onAbort = (): void => {
      done();
      reject(Object.assign(new Error('abort'), { name: 'AbortError' }));
    };
    const timer = setTimeout(() => {
      done();
      reject(new Error('timeout'));
    }, 8000);
    w[name] = (data: T): void => {
      done();
      resolve(data);
    };
    script.onerror = (): void => {
      done();
      reject(new Error('blocked'));
    };
    signal?.addEventListener('abort', onAbort);
    script.src = `${url}${url.includes('?') ? '&' : '?'}${callbackParam}=${name}`;
    document.head.appendChild(script);
  });
}

async function fromDeezer(track: Track, signal?: AbortSignal): Promise<Preview | null> {
  const lead = track.artist.split(',')[0].trim().replace(/"/g, '');
  const title = track.title.replace(/"/g, '');
  const q = encodeURIComponent(`artist:"${lead}" track:"${title}"`);
  const body = await jsonp<{ data?: { title?: string; artist?: { name?: string }; preview?: string }[] }>(
    `https://api.deezer.com/search?q=${q}&limit=8&output=jsonp`, 'callback', signal);
  const list: Candidate[] = (body.data ?? []).map((d) => ({ artist: d.artist?.name ?? '', title: d.title ?? '', url: d.preview ?? '' }));
  const hit = best(track, list);
  return hit ? { url: hit.url, source: 'deezer', startMs: 0 } : null;
}

async function fromItunes(track: Track, signal?: AbortSignal): Promise<Preview | null> {
  const term = encodeURIComponent(`${track.artist.split(',')[0]} ${track.title}`);
  const body = await jsonp<{ results?: { artistName?: string; trackName?: string; previewUrl?: string }[] }>(
    `https://itunes.apple.com/search?term=${term}&media=music&entity=song&limit=10`, 'callback', signal);
  const list: Candidate[] = (body.results ?? []).map((r) => ({ artist: r.artistName ?? '', title: r.trackName ?? '', url: r.previewUrl ?? '' }));
  const hit = best(track, list);
  return hit ? { url: hit.url, source: 'itunes', startMs: 0 } : null;
}

/**
 * Finds a short audio preview for a track: the one Beatport lists (when the chart was read from Beatport),
 * then Deezer (30 s), then Apple Music (30 s). Returns null when no result closely matches,
 * so the app never plays the wrong song.
 */
export async function resolvePreview(track: Track, signal?: AbortSignal): Promise<Preview | null> {
  if (track.previewUrl) return { url: track.previewUrl, source: 'beatport', startMs: track.previewStartMs ?? 0 };
  for (const lookup of [fromDeezer, fromItunes]) {
    try {
      const hit = await lookup(track, signal);
      if (hit) return hit;
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') throw e;
    }
  }
  return null;
}
