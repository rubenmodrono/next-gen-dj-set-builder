import { keyStandard, keyStr, parseKey, transition } from './camelot';
import { clamp, curveWindow, energyFromBpm, locate } from './curve';
import type { DroppedTrack, PlannedTrack, RawTrack, Segment, Strictness, Track } from './types';

export const AVG_TRACK_MIN = 5.5;
export const MAX_SLOTS = 44;

const norm = (s: string): string =>
  s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\(.*?\)|\[.*?\]/g, ' ')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export const fmtBpm = (n: number): string => (Math.abs(n - Math.round(n)) < 0.05 ? String(Math.round(n)) : n.toFixed(1));

export function trackLabel(t: Pick<Track, 'artist' | 'title' | 'mix'>): string {
  return `${t.artist} - ${t.title}${t.mix ? ` (${t.mix})` : ''}`;
}

/** "Artist - Title (Mix) - 124 BPM - 8A (Am)" */
export function formatLine(t: Track): string {
  return `${trackLabel(t)} - ${fmtBpm(t.bpm)} BPM - ${keyStr(t.key)} (${keyStandard(t.key)})`;
}

export interface PrepareOptions {
  segments: Segment[];
  bpmMin: number;
  bpmMax: number;
  maxPerArtist?: number;
}

/**
 * Validates and deduplicates tracks read from a chart.
 * Drops: missing/invalid BPM, BPM outside the genre window (chart data errors),
 * missing key, near-duplicate versions of one song, and artists beyond the cap.
 */
export function preparePool(raw: RawTrack[], opts: PrepareOptions): { pool: Track[]; dropped: DroppedTrack[] } {
  const { lo, hi } = curveWindow(opts.segments);
  const cap = opts.maxPerArtist ?? 2;
  const pool: Track[] = [];
  const dropped: DroppedTrack[] = [];
  const songs = new Set<string>();
  const perArtist = new Map<string, number>();

  for (const r of raw) {
    const artist = r.artists.map((a) => a.trim()).filter(Boolean).join(', ');
    const title = (r.title ?? '').trim();
    if (!artist || !title) continue;
    const mix = r.mix ? r.mix.trim() : null;
    const label = trackLabel({ artist, title, mix });
    const bpm = typeof r.bpm === 'number' ? r.bpm : Number(r.bpm);
    if (!Number.isFinite(bpm) || bpm <= 0) {
      dropped.push({ label, reason: 'sin BPM' });
      continue;
    }
    if (bpm < opts.bpmMin || bpm > opts.bpmMax) {
      dropped.push({ label, reason: `BPM fuera del rango del género (${fmtBpm(bpm)})` });
      continue;
    }
    const key = parseKey(r.key);
    if (!key) {
      dropped.push({ label, reason: 'sin tonalidad' });
      continue;
    }
    const lead = norm(r.artists[0] ?? artist);
    const songKey = `${lead}|${norm(title).split(' ').slice(0, 2).join(' ')}`;
    if (songs.has(songKey)) {
      dropped.push({ label, reason: 'otra versión del mismo tema' });
      continue;
    }
    if ((perArtist.get(lead) ?? 0) >= cap) {
      dropped.push({ label, reason: `más de ${cap} temas del mismo artista` });
      continue;
    }
    songs.add(songKey);
    perArtist.set(lead, (perArtist.get(lead) ?? 0) + 1);
    pool.push({
      artist, title, mix, bpm, key, energy: energyFromBpm(bpm, lo, hi), genre: r.genre ?? null,
      previewUrl: r.previewUrl ?? null, previewStartMs: r.previewStartMs ?? null,
    });
  }
  return { pool, dropped };
}

const W = { harm: 1.0, bpmStep: 0.5, energy: 1.4, center: 0.15, tbpm: 0.9, maxJump: 6 };
const bpmDist = (a: number, b: number): number => Math.min(Math.abs(a - b), Math.abs(a - 2 * b) + 4, Math.abs(2 * a - b) + 4);

interface BeamState {
  cost: number;
  path: number[];
  used: number[]; // bitset, 32 bits per word
}

/** Picks and orders `n` tracks so the set follows the curve with the cheapest harmonic and tempo transitions. */
export function orderTracks(
  pool: Track[],
  segs: Segment[],
  strictness: Strictness,
  n: number,
  beamWidth = 40,
): PlannedTrack[] {
  const P = pool.length;
  const count = Math.min(n, P);
  const words = Math.ceil(P / 32);
  const points = Array.from({ length: count }, (_, i) => locate(segs, (i + 0.5) / count));
  const hw = strictness === 'strict' ? W.harm * 1.5 : W.harm;

  const slotCost = points.map((pt) =>
    pool.map((t) => {
      const out = t.energy < pt.eMin ? pt.eMin - t.energy : t.energy > pt.eMax ? t.energy - pt.eMax : 0;
      const center = (pt.eMin + pt.eMax) / 2;
      return W.energy * out + W.center * Math.abs(t.energy - center) + W.tbpm * bpmDist(t.bpm, pt.bpm);
    }),
  );
  const trans: number[][] = pool.map((a, i) =>
    pool.map((b, j) => {
      if (i === j) return 0;
      const d = bpmDist(a.bpm, b.bpm);
      return hw * transition(a.key, b.key, strictness)[1] + W.bpmStep * d + (d > W.maxJump ? (d - W.maxJump) * 2 : 0);
    }),
  );

  let beam: BeamState[] = [{ cost: 0, path: [], used: new Array<number>(words).fill(0) }];
  for (let i = 0; i < count; i++) {
    const next = new Map<string, BeamState>();
    for (const st of beam) {
      const last = st.path.length ? st.path[st.path.length - 1] : -1;
      for (let j = 0; j < P; j++) {
        if ((st.used[j >> 5] >>> (j & 31)) & 1) continue;
        const cost = st.cost + slotCost[i][j] + (last >= 0 ? trans[last][j] : 0);
        const used = st.used.slice();
        used[j >> 5] |= 1 << (j & 31);
        const key = `${j}:${used.join(',')}`;
        const prev = next.get(key);
        if (!prev || cost < prev.cost) next.set(key, { cost, path: [...st.path, j], used });
      }
    }
    beam = [...next.values()]
      .sort((x, y) => x.cost - y.cost || x.path.join(',').localeCompare(y.path.join(',')))
      .slice(0, beamWidth);
  }
  const best = beam[0];
  return best.path.map((j, i) => ({
    track: pool[j],
    point: points[i],
    transition: i === 0 ? null : transition(pool[best.path[i - 1]].key, pool[j].key, strictness),
  }));
}

export function slotsFor(durationMin: number): number {
  return clamp(Math.max(Math.round(durationMin / AVG_TRACK_MIN), 4), 4, MAX_SLOTS);
}
