import { keyHue, keyStr } from '../core/camelot';
import type { CamelotKey, PlannedTrack } from '../core/types';

/** Fill for a key, one hue per Camelot number. Lightness follows the theme through --key-l. */
export const keyFill = (k: CamelotKey): string => `hsl(${keyHue(k)} 62% var(--key-l))`;

interface Props {
  items: PlannedTrack[];
  size: number;
}

/** Camelot wheel with the keys used by the set filled in and the path between them drawn as a line. */
export function Wheel({ items, size }: Props): React.JSX.Element {
  const c = size / 2;
  const rOut = size * 0.37;
  const rIn = size * 0.225;
  const pos = (k: CamelotKey): { x: number; y: number } => {
    const theta = ((k.n % 12) * 30 * Math.PI) / 180;
    const r = k.l === 'B' ? rOut : rIn;
    return { x: c + r * Math.sin(theta), y: c - r * Math.cos(theta) };
  };
  const all: CamelotKey[] = [];
  for (const l of ['B', 'A'] as const) for (let n = 1; n <= 12; n++) all.push({ n, l });
  const used = new Map<string, CamelotKey>();
  for (const it of items) used.set(keyStr(it.track.key), it.track.key);
  const path = items
    .map((it) => it.track.key)
    .filter((k, i, a) => i === 0 || keyStr(k) !== keyStr(a[i - 1]))
    .map(pos);
  const label = [...used.keys()].join(', ');

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Rueda de Camelot con las tonalidades del set: ${label}`} className="wheel">
      <circle cx={c} cy={c} r={rOut} fill="none" style={{ stroke: 'var(--border)' }} strokeWidth={1} />
      <circle cx={c} cy={c} r={rIn} fill="none" style={{ stroke: 'var(--border)' }} strokeWidth={1} />
      {path.length > 1 && (
        <polyline
          points={path.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}
          fill="none" style={{ stroke: 'var(--ink)' }} strokeOpacity={0.7} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round"
        />
      )}
      {all.map((k) => {
        const id = keyStr(k);
        const p = pos(k);
        const on = used.has(id);
        return (
          <g key={id}>
            <circle
              cx={p.x} cy={p.y} r={on ? (k.l === 'B' ? 15 : 13) : 3.5}
              style={on ? { fill: keyFill(k), stroke: 'var(--surface)' } : { fill: 'var(--surface)', stroke: 'var(--border-strong)' }}
              strokeWidth={on ? 2 : 1}
            />
            {on && (
              <text x={p.x} y={p.y + 4} textAnchor="middle" className="wheel-label" style={{ fill: 'var(--key-ink)' }}>{id}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
