import type { CurvePoint, Segment } from './types';

export const clamp = (v: number, lo: number, hi: number): number => Math.min(Math.max(v, lo), hi);

/** Target BPM and energy window at position t (0..1) of the set. */
export function locate(segs: Segment[], t: number): CurvePoint {
  const total = segs.reduce((a, s) => a + s.weight, 0);
  const pos = clamp(t, 0, 1);
  let acc = 0;
  for (let i = 0; i < segs.length; i++) {
    const s = segs[i];
    const a = acc / total;
    acc += s.weight;
    const b = acc / total;
    if (pos <= b || i === segs.length - 1) {
      const u = b > a ? clamp((pos - a) / (b - a), 0, 1) : 0;
      return {
        seg: i,
        name: s.name,
        bpm: s.bpmStart + (s.bpmEnd - s.bpmStart) * u,
        eMin: s.eMin,
        eMax: s.eMax,
      };
    }
  }
  throw new Error('locate: empty segment list');
}

/** Energy has no field in Beatport. It is estimated from BPM, relative to the curve's own BPM window. */
export function energyFromBpm(bpm: number, lo: number, hi: number): number {
  if (hi <= lo) return 5;
  return clamp(1 + (9 * (bpm - lo)) / (hi - lo), 1, 10);
}

export function curveWindow(segs: Segment[]): { lo: number; hi: number } {
  const all = segs.flatMap((s) => [s.bpmStart, s.bpmEnd]);
  return { lo: Math.min(...all), hi: Math.max(...all) };
}
