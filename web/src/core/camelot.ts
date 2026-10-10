import type { CamelotKey, Strictness, TransitionType } from './types';

const NOTE_PC: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const MAJ_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
const MIN_NAMES = ['Cm', 'C#m', 'Dm', 'Ebm', 'Em', 'Fm', 'F#m', 'Gm', 'G#m', 'Am', 'Bbm', 'Bm'];

/** Camelot number of the major key whose root has pitch class `pc` (C = 0 -> 8B). */
const majorNumber = (pc: number): number => ((((pc * 7) % 12) + 7) % 12) + 1;

/**
 * Parses Camelot ("8A"), Open Key ("1m"), or standard notation
 * ("Am", "F#m", "Bb", "C Major", "Db Minor"). Returns null if unrecognised.
 */
export function parseKey(raw: unknown): CamelotKey | null {
  if (raw == null) return null;
  const s = String(raw).trim();
  if (!s) return null;

  let m = /^(1[0-2]|[1-9])\s*([ABab])$/.exec(s);
  if (m) return { n: Number(m[1]), l: m[2].toUpperCase() as 'A' | 'B' };

  m = /^(1[0-2]|[1-9])\s*([dm])$/.exec(s); // Open Key (Traktor)
  if (m) return { n: ((Number(m[1]) + 6) % 12) + 1, l: m[2] === 'd' ? 'B' : 'A' };

  m = /^([A-Ga-g])\s*([#♯♭b♭]?)\s*(.*)$/.exec(s);
  if (!m) return null;
  let pc = NOTE_PC[m[1].toUpperCase()];
  const acc = m[2];
  if (acc === '#' || acc === '♯') pc += 1;
  else if (acc === 'b' || acc === '♭') pc -= 1;
  pc = ((pc % 12) + 12) % 12;
  const rest = m[3].trim();
  let minor: boolean;
  if (rest === '' || rest === 'M' || /^(maj|major|dur)$/i.test(rest)) minor = false;
  else if (/^(m|min|minor|moll)$/i.test(rest)) minor = true;
  else return null;
  return minor ? { n: majorNumber((pc + 3) % 12), l: 'A' } : { n: majorNumber(pc), l: 'B' };
}

export const keyStr = (k: CamelotKey): string => `${k.n}${k.l}`;

export function keyStandard(k: CamelotKey): string {
  let pc = 0;
  for (let p = 0; p < 12; p++) if (majorNumber(p) === k.n) pc = p;
  return k.l === 'B' ? MAJ_NAMES[pc] : MIN_NAMES[(((pc - 3) % 12) + 12) % 12];
}

/**
 * Harmonic transition type and cost (0 = perfect, 10 = clash).
 * Same scale as harmonic_engine.py of the project.
 */
export function transition(a: CamelotKey, b: CamelotKey, strictness: Strictness): [TransitionType, number] {
  if (a.n === b.n && a.l === b.l) return ['perfect', 0];
  const same = a.l === b.l;
  const diff = (((b.n - a.n) % 12) + 12) % 12;
  const d = Math.min(diff, 12 - diff);
  if (d === 0 && !same) return ['relative', 0.5];
  if (d === 1 && same) return ['adjacent', 0.2];
  if (d === 1 && !same) return ['diagonal', 1.5];
  if (diff === 2 && same) return ['boost2', strictness === 'strict' ? 4 : 1];
  if (diff === 7 && same) return ['boost1', strictness === 'strict' ? 6 : 2];
  if (diff === 10 && same) return ['drop', strictness === 'permissive' ? 2.5 : 5];
  let c = 5 + d * 1.2;
  if (strictness === 'strict') c += 3;
  return ['clash', Math.min(c, 10)];
}

/** Hue (0..330) used to colour a key chip, one hue per Camelot number. */
export const keyHue = (k: CamelotKey): number => (k.n - 1) * 30;
