import { parseKey } from './camelot';
import { energyFromBpm, curveWindow } from './curve';
import { curvePoints, fitCost, orderTracksDetailed, songKeyOf } from './planner';
import type { PlannedTrack, Segment, Strictness, Track } from './types';

export interface PinnedInput {
  artist: string;
  title: string;
  mix?: string | null;
  bpm: number;
  key: string;
}

export type PinnedResult = { ok: true; track: Track; warning: string | null } | { ok: false; error: string };

/** Validates a track the user wants in the set. Unlike chart tracks, it is never dropped for being outside the genre window. */
export function toPinnedTrack(input: PinnedInput, segs: Segment[]): PinnedResult {
  const artist = input.artist.trim();
  const title = input.title.trim();
  if (!artist || !title) return { ok: false, error: 'Falta el artista o el título.' };
  const bpm = Number(input.bpm);
  if (!Number.isFinite(bpm) || bpm < 60 || bpm > 200) return { ok: false, error: 'El BPM debe estar entre 60 y 200.' };
  const key = parseKey(input.key);
  if (!key) return { ok: false, error: 'No reconozco la tonalidad. Usa Camelot (8A), Open Key (1m) o notación (Am, F#m).' };
  const { lo, hi } = curveWindow(segs);
  const warning =
    bpm < lo - 6 || bpm > hi + 6
      ? `${bpm} BPM queda lejos de la curva (${lo}–${hi}). Se colocará en el extremo más cercano.`
      : null;
  return {
    ok: true,
    warning,
    track: {
      artist, title, mix: input.mix?.trim() || null, bpm, key, energy: energyFromBpm(bpm, lo, hi),
      genre: null, previewUrl: null, previewStartMs: null,
    },
  };
}

/**
 * Reads "Artista - Título - BPM - tonalidad" lines (the same shape the app prints).
 * Also accepts tab- or semicolon-separated values. Returns one result per non-empty line.
 */
export function parsePinnedLines(text: string): { line: string; input?: PinnedInput; error?: string }[] {
  const out: { line: string; input?: PinnedInput; error?: string }[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.includes('\t') ? line.split('\t') : line.includes(';') ? line.split(';') : line.split(/\s+[-–—]\s+/);
    const cells = parts.map((c) => c.trim()).filter(Boolean);
    if (cells.length < 4) {
      out.push({ line, error: 'Usa el formato Artista - Título - BPM - tonalidad.' });
      continue;
    }
    // Last two cells are BPM and key; everything before is artist and title (a title may contain " - ").
    const key = cells[cells.length - 1].replace(/\s*\(.*\)\s*$/, '');
    const bpm = Number(cells[cells.length - 2].replace(/\s*bpm$/i, '').replace(',', '.'));
    const head = cells.slice(0, cells.length - 2);
    const artist = head[0];
    const title = head.slice(1).join(' - ');
    if (!Number.isFinite(bpm)) {
      out.push({ line, error: 'El BPM no es un número.' });
      continue;
    }
    out.push({ line, input: { artist, title, bpm, key } });
  }
  return out;
}

export interface PlanOutcome {
  items: PlannedTrack[];
  /** Positions (0-based) of the pinned tracks inside `items`. */
  pinnedSlots: number[];
  /** True when more tracks were pinned than the duration has slots, so the set was lengthened. */
  extended: boolean;
  slots: number;
  cost: number;
}

/**
 * Builds the set with the pinned tracks inside it.
 * 1. Every pinned track gets candidate slots ranked by how well it fits the curve there (BPM and energy).
 * 2. The best few combinations of slots are tried; for each, the rest of the set is ordered around the fixed anchors.
 * 3. The combination with the lowest total cost (curve fit + harmonic and tempo transitions) wins.
 */
export function planSet(
  pool: Track[],
  pinned: Track[],
  segs: Segment[],
  strictness: Strictness,
  n: number,
  beamWidth = 40,
): PlanOutcome {
  const seen = new Set(pinned.map((p) => songKeyOf(p.artist, p.title)));
  const rest = pool.filter((t) => !seen.has(songKeyOf(t.artist, t.title)));
  const m = pinned.length;
  const want = Math.max(n, m);
  const extended = m > n;
  if (m === 0) {
    const r = orderTracksDetailed(rest, segs, strictness, want, beamWidth);
    return { items: r.items, pinnedSlots: [], extended: false, slots: r.items.length, cost: r.cost };
  }

  const all = [...rest, ...pinned];
  const base = rest.length;
  const count = Math.min(want, all.length);
  const points = curvePoints(segs, count);

  // Candidate slots per pinned track, best fit first.
  const ranked = pinned.map((t) =>
    points
      .map((pt, i) => ({ slot: i, cost: fitCost(t, pt) }))
      .sort((a, b) => a.cost - b.cost || a.slot - b.slot)
      .slice(0, 8),
  );

  // Beam over assignments: keep the 24 cheapest partial assignments, then take the 6 best complete ones.
  let states: { cost: number; slots: number[] }[] = [{ cost: 0, slots: [] }];
  for (let k = 0; k < m; k++) {
    const next: { cost: number; slots: number[] }[] = [];
    for (const st of states) {
      for (const c of ranked[k]) {
        if (st.slots.includes(c.slot)) continue;
        next.push({ cost: st.cost + c.cost, slots: [...st.slots, c.slot] });
      }
    }
    states = next.sort((a, b) => a.cost - b.cost).slice(0, 24);
    if (!states.length) break;
  }

  let best: { items: PlannedTrack[]; cost: number; slots: number[] } | null = null;
  for (const st of states.slice(0, 6)) {
    const fixed = new Map<number, number>();
    st.slots.forEach((slot, k) => fixed.set(slot, base + k));
    const r = orderTracksDetailed(all, segs, strictness, want, beamWidth, { fixed });
    if (r.items.length && (!best || r.cost < best.cost)) best = { ...r, slots: st.slots };
  }
  if (!best) {
    const r = orderTracksDetailed(all, segs, strictness, want, beamWidth);
    return { items: r.items, pinnedSlots: [], extended, slots: r.items.length, cost: r.cost };
  }
  const pinnedSet = new Set(pinned);
  const pinnedSlots = best.items.flatMap((it, i) => (pinnedSet.has(it.track) ? [i] : []));
  return { items: best.items, pinnedSlots, extended, slots: best.items.length, cost: best.cost };
}

/**
 * Cuts a big library down to a pool the ordering can handle (about `cap` tracks).
 * Keeps the tracks that fit the curve best, spread over all 24 keys so the harmonic search has room to move.
 */
export function shortlist(tracks: Track[], segs: Segment[], n: number, cap = 160): Track[] {
  if (tracks.length <= cap) return tracks;
  const points = curvePoints(segs, Math.max(n, 4));
  const scored = tracks
    .map((t) => ({ t, score: Math.min(...points.map((pt) => fitCost(t, pt))) }))
    .sort((a, b) => a.score - b.score);
  const perKey = Math.max(3, Math.floor(cap / 24));
  const counts = new Map<string, number>();
  const picked = new Set<Track>();
  for (const s of scored) {
    const k = `${s.t.key.n}${s.t.key.l}`;
    const c = counts.get(k) ?? 0;
    if (c < perKey) {
      counts.set(k, c + 1);
      picked.add(s.t);
    }
  }
  for (const s of scored) {
    if (picked.size >= cap) break;
    picked.add(s.t);
  }
  return [...picked].slice(0, cap);
}
