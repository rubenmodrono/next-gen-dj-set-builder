import { useEffect, useRef, useState } from 'react';
import { keyStr } from '../core/camelot';
import { fmtBpm } from '../core/planner';
import type { PlannedTrack, Segment } from '../core/types';
import { keyFill } from './Wheel';

const ML = 40;
const MR = 12;
const MT = 12;
const H = 176;
const MB = 12;

function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(320);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(240, Math.floor(el.clientWidth))));
    ro.observe(el);
    setW(Math.max(240, Math.floor(el.clientWidth)));
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** BPM along the set: the target curve (dashed) and the chosen tracks (solid, one dot per track coloured by key). */
export function Curve({ items, segments, pinnedSlots }: { items: PlannedTrack[]; segments: Segment[]; pinnedSlots: number[] }): React.JSX.Element {
  const [ref, W] = useWidth();
  const n = items.length;
  const bpms = [...items.map((i) => i.track.bpm), ...items.map((i) => i.point.bpm)];
  const lo = Math.floor(Math.min(...bpms) - 1);
  const hi = Math.ceil(Math.max(...bpms) + 1);
  const x = (i: number): number => ML + (n <= 1 ? 0.5 : i / (n - 1)) * (W - ML - MR);
  const y = (b: number): number => MT + (1 - (b - lo) / Math.max(1, hi - lo)) * (H - MT - MB);
  const line = (vals: number[]): string => vals.map((b, i) => `${x(i).toFixed(1)},${y(b).toFixed(1)}`).join(' ');
  const total = segments.reduce((a, s) => a + s.weight, 0);
  const pinned = new Set(pinnedSlots);
  const r = n > 24 ? 3.5 : 5;

  // Segment bands: boundaries at cumulative weight.
  let acc = 0;
  const bands = segments.map((s, i) => {
    const a = acc / total;
    acc += s.weight;
    return { s, i, a, b: acc / total };
  });
  const px = (f: number): number => ML + f * (W - ML - MR);

  return (
    <div ref={ref} className="curve">
      <svg width={W} height={H} role="img" aria-label={`Curva de BPM: empieza en ${fmtBpm(items[0].track.bpm)}, termina en ${fmtBpm(items[n - 1].track.bpm)}, máximo ${fmtBpm(Math.max(...items.map((i) => i.track.bpm)))}.`}>
        {bands.map((bd) => (
          <rect key={bd.i} x={px(bd.a)} y={MT} width={px(bd.b) - px(bd.a)} height={H - MT - MB} style={{ fill: 'var(--ink)' }} opacity={bd.i % 2 ? 0.05 : 0} />
        ))}
        {[lo, Math.round((lo + hi) / 2), hi].map((b) => (
          <g key={b}>
            <line x1={ML} x2={W - MR} y1={y(b)} y2={y(b)} style={{ stroke: 'var(--border)' }} strokeWidth={1} />
            <text x={ML - 8} y={y(b) + 4} textAnchor="end" className="axis">{b}</text>
          </g>
        ))}
        <polyline points={line(items.map((i) => i.point.bpm))} fill="none" style={{ stroke: 'var(--muted)' }} strokeWidth={1.5} strokeDasharray="4 4" />
        <polyline points={line(items.map((i) => i.track.bpm))} fill="none" style={{ stroke: 'var(--accent-text)' }} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {items.map((it, i) => (
          <g key={i}>
            {pinned.has(i) && <circle cx={x(i)} cy={y(it.track.bpm)} r={r + 4} fill="none" style={{ stroke: 'var(--accent-text)' }} strokeWidth={2} />}
            <circle cx={x(i)} cy={y(it.track.bpm)} r={r} style={{ fill: keyFill(it.track.key), stroke: 'var(--surface)' }} strokeWidth={1.5}>
              <title>{`${i + 1}. ${it.track.artist} - ${it.track.title} · ${fmtBpm(it.track.bpm)} BPM · ${keyStr(it.track.key)}`}</title>
            </circle>
          </g>
        ))}
      </svg>
      <div className="segbar" style={{ marginLeft: ML, marginRight: MR }}>
        {segments.map((s, i) => (
          <span key={i} style={{ flexBasis: `${(s.weight / total) * 100}%` }} title={`${s.name} ${Math.round((s.weight / total) * 100)} %`}>{s.name}</span>
        ))}
      </div>
      <p className="legend"><span className="lg dashed" aria-hidden="true" />Curva objetivo <span className="lg solid" aria-hidden="true" />Temas elegidos</p>
    </div>
  );
}
