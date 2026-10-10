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

async function getJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const res = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function fromDeezer(track: Track, signal?: AbortSignal): Promise<Preview | null> {
  const lead = track.artist.split(',')[0].trim().replace(/"/g, '');
  const title = track.title.replace(/"/g, '');
  const q = encodeURIComponent(`artist:"${lead}" track:"${title}"`);
  const body = (await getJson(`https://api.deezer.com/search?q=${q}&limit=8`, signal)) as {
    data?: { title?: string; artist?: { name?: string }; preview?: string }[];
  };
  const list: Candidate[] = (body.data ?? []).map((d) => ({ artist: d.artist?.name ?? '', title: d.title ?? '', url: d.preview ?? '' }));
  const hit = best(track, list);
  return hit ? { url: hit.url, source: 'deezer', startMs: 0 } : null;
}

async function fromItunes(track: Track, signal?: AbortSignal): Promise<Preview | null> {
  const term = encodeURIComponent(`${track.artist.split(',')[0]} ${track.title}`);
  const body = (await getJson(`https://itunes.apple.com/search?term=${term}&media=music&entity=song&limit=10`, signal)) as {
    results?: { artistName?: string; trackName?: string; previewUrl?: string }[];
  };
  const list: Candidate[] = (body.results ?? []).map((r) => ({ artist: r.artistName ?? '', title: r.trackName ?? '', url: r.previewUrl ?? '' }));
  const hit = best(track, list);
  return hit ? { url: hit.url, source: 'itunes', startMs: 0 } : null;
}

/**
 * Finds a short audio preview for a track.
 * 1. The preview Beatport itself lists for the track (same audio and mix as on beatport.com).
 * 2. Deezer's public search (30 s).
 * 3. iTunes Search (30 s).
 * Returns null when none has a close match, so the app never plays the wrong song.
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
