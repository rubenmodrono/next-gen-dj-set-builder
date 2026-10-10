import type { RawTrack } from '../core/types';

/** Small deterministic generator, so the demo library is the same on every load. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const A1 = ['Lumen', 'Orbit', 'Halcyon', 'Nocturne', 'Vesper', 'Kilo', 'Mirage', 'Tidal', 'Aster', 'Borealis', 'Cobalt', 'Delta', 'Echo', 'Fathom', 'Gossamer', 'Helix'];
const A2 = ['Arc', 'Field', 'Room', 'Signal', 'Drift', 'Parade', 'Club', 'Theory', 'Lines', 'Harbor', 'Cartel', 'Union'];
const T1 = ['Midnight', 'Glass', 'Slow', 'Paper', 'Neon', 'Quiet', 'Golden', 'Lost', 'Velvet', 'Distant', 'Open', 'Hollow', 'Last', 'Silver', 'Wild', 'Blue'];
const T2 = ['Horizon', 'Echoes', 'Garden', 'Pulse', 'Letters', 'Tide', 'Skyline', 'Machine', 'Signals', 'Rooftop', 'Static', 'Harbour', 'Orbit', 'Season', 'Bloom', 'Weather'];
const MIX = ['Original Mix', 'Extended Mix', 'Club Mix'];
const KEYS = ['1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A', '1B', '2B', '3B', '4B', '5B', '6B', '7B', '8B', '9B', '10B', '11B', '12B'];

const GENRES: { name: string; lo: number; hi: number; count: number }[] = [
  { name: 'Progressive House', lo: 118, hi: 128, count: 110 },
  { name: 'Tech House', lo: 124, hi: 132, count: 90 },
  { name: 'Melodic House & Techno', lo: 118, hi: 126, count: 80 },
  { name: 'Deep House', lo: 116, hi: 124, count: 70 },
];

/** Fictional tracks (invented artist and title names) to try the app without importing a library. */
export function demoLibrary(): RawTrack[] {
  const r = rng(20261010);
  const pick = <T,>(a: readonly T[]): T => a[Math.floor(r() * a.length)];
  const out: RawTrack[] = [];
  const seen = new Set<string>();
  for (const g of GENRES) {
    for (let i = 0; i < g.count; i++) {
      let artist = '';
      let title = '';
      do {
        artist = `${pick(A1)} ${pick(A2)}`;
        title = `${pick(T1)} ${pick(T2)}`;
      } while (seen.has(`${artist}|${title}`));
      seen.add(`${artist}|${title}`);
      // Triangular distribution, so most tracks sit in the middle of the genre's tempo range.
      const bpm = Math.round(g.lo + (g.hi - g.lo) * ((r() + r()) / 2));
      // Most DJ libraries cluster in a handful of keys; weight the first half of the wheel.
      const key = r() < 0.55 ? pick(KEYS.slice(0, 12)) : pick(KEYS);
      out.push({ artists: [artist], title, mix: pick(MIX), genre: g.name, bpm, key });
    }
  }
  return out;
}
