import { norm } from './core/planner';
import type { RawTrack, Segment } from './core/types';
import { GENRES, type GenreInfo } from './data/genres';

export interface SegInput { name: string; weight: string; bpmStart: string; bpmEnd: string; eMin: string; eMax: string }

export const toInputs = (segs: Segment[]): SegInput[] =>
  segs.map((s) => ({ name: s.name, weight: String(s.weight), bpmStart: String(s.bpmStart), bpmEnd: String(s.bpmEnd), eMin: String(s.eMin), eMax: String(s.eMax) }));

const num = (s: string): number => Number(s.replace(',', '.'));

export const toSegments = (inputs: SegInput[]): Segment[] =>
  inputs.map((s, i) => ({
    name: s.name.trim().slice(0, 24) || `Tramo ${i + 1}`,
    weight: num(s.weight), bpmStart: num(s.bpmStart), bpmEnd: num(s.bpmEnd), eMin: num(s.eMin), eMax: num(s.eMax),
  }));

/** Returns the first problem found, phrased as what to change. */
export function segmentError(segs: Segment[]): { message: string; field: string } | null {
  for (let i = 0; i < segs.length; i++) {
    const s = segs[i];
    if (!(s.weight > 0)) return { message: `Pon un peso mayor que 0 en el tramo ${s.name}.`, field: `seg-${i}-weight` };
    if (!(s.bpmStart >= 60 && s.bpmStart <= 200)) return { message: `Pon un BPM de inicio entre 60 y 200 en el tramo ${s.name}.`, field: `seg-${i}-bpmStart` };
    if (!(s.bpmEnd >= 60 && s.bpmEnd <= 200)) return { message: `Pon un BPM final entre 60 y 200 en el tramo ${s.name}.`, field: `seg-${i}-bpmEnd` };
    if (!(s.eMin >= 0 && s.eMax <= 10 && s.eMin <= s.eMax)) {
      return { message: `La energía del tramo ${s.name} va de 0 a 10, con el mínimo por debajo del máximo.`, field: `seg-${i}-eMin` };
    }
  }
  return null;
}

const slug = (s: string): string => norm(s).replace(/ and /g, ' ').replace(/[^a-z0-9]/g, '');

/** Genres in a library, most frequent first. */
export function libraryGenres(tracks: RawTrack[]): { name: string; count: number }[] {
  const m = new Map<string, number>();
  for (const t of tracks) {
    const g = (t.genre ?? '').trim();
    if (g) m.set(g, (m.get(g) ?? 0) + 1);
  }
  return [...m.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/**
 * BPM window for a library selection. Known genres use the built-in windows;
 * anything else is derived from the tracks themselves (10th to 90th percentile).
 */
export function genreForLibrary(label: string, tracks: RawTrack[]): GenreInfo {
  const known = label === 'all' ? undefined : GENRES.find((g) => slug(g.label) === slug(label) || slug(g.slug) === slug(label));
  if (known) return known;
  const bpms = tracks.map((t) => t.bpm).filter((b): b is number => typeof b === 'number' && b >= 60 && b <= 200).sort((a, b) => a - b);
  let lo = 120;
  let hi = 128;
  if (bpms.length >= 5) {
    lo = Math.round(bpms[Math.floor(bpms.length * 0.1)]);
    hi = Math.round(bpms[Math.min(bpms.length - 1, Math.ceil(bpms.length * 0.9) - 1)]);
  } else if (bpms.length) {
    lo = Math.round(bpms[0]);
    hi = Math.round(bpms[bpms.length - 1]);
  }
  if (hi - lo < 6) {
    lo -= 3;
    hi += 3;
  }
  return {
    id: `lib:${label}`, label: label === 'all' ? 'Toda la biblioteca' : label, slug: '', beatportId: 0,
    bpmMin: Math.max(60, lo - 8), bpmMax: Math.min(200, hi + 8), curveLo: lo, curveHi: hi,
  };
}

export const HARM = [
  { value: 'strict', label: 'Estricta', hint: 'Solo misma tonalidad, un paso en la rueda Camelot o paso a la relativa (8A a 8B).' },
  { value: 'energy_boost', label: 'Con saltos', hint: 'Además permite subir +1 o +2 semitonos y bajar de energía (8A a 10A, 8A a 6A).' },
  { value: 'permissive', label: 'Libre', hint: 'Admite cualquier salto, con un coste mayor cuanto más choque.' },
] as const;

export const TRANSITION_LABEL: Record<string, string> = {
  perfect: 'Misma tonalidad',
  adjacent: 'Paso en la rueda',
  relative: 'Relativa',
  diagonal: 'Diagonal',
  boost1: 'Subida +1',
  boost2: 'Subida +2',
  drop: 'Bajada de energía',
  clash: 'Choque armónico',
};

export const read = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
export const write = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the setting simply isn't remembered */
  }
};
