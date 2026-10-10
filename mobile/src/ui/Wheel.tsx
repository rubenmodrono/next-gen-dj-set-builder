import React from 'react';
import Svg, { Circle, G, Polyline, Text as SvgText } from 'react-native-svg';
import { keyHue, keyStr } from '../core/camelot';
import type { CamelotKey, PlannedTrack } from '../core/types';

export interface WheelColors {
  panel: string;
  muted: string;
  rule: string;
  ink: string;
  bg: string;
}

const C = 100;
const R_OUT = 74;
const R_IN = 45;

/** Colour used for a Camelot key everywhere in the UI. */
export const keyColor = (k: CamelotKey, light = 66): string => `hsl(${keyHue(k)}, 66%, ${light}%)`;

/** Position of a key on the wheel: 12 at the top, clockwise. B on the outer ring, A on the inner one. */
export function wheelPos(k: CamelotKey): { x: number; y: number } {
  const theta = ((k.n % 12) * 30 * Math.PI) / 180;
  const r = k.l === 'B' ? R_OUT : R_IN;
  return { x: C + r * Math.sin(theta), y: C - r * Math.cos(theta) };
}

interface Props {
  items: PlannedTrack[];
  size: number;
  colors: WheelColors;
}

export function Wheel({ items, size, colors }: Props): React.JSX.Element {
  const all: CamelotKey[] = [];
  for (const l of ['B', 'A'] as const) for (let n = 1; n <= 12; n++) all.push({ n, l });
  const used = new Map<string, CamelotKey>();
  for (const it of items) used.set(keyStr(it.track.key), it.track.key);

  const path = items
    .map((it) => it.track.key)
    .filter((k, i, arr) => i === 0 || keyStr(k) !== keyStr(arr[i - 1]))
    .map(wheelPos);
  const label = items.map((it) => keyStr(it.track.key)).join(', ');

  return (
    <Svg width={size} height={size} viewBox="0 0 200 200" accessibilityLabel={`Rueda de Camelot con las tonalidades del set: ${label}`}>
      <Circle cx={C} cy={C} r={R_OUT} fill="none" stroke={colors.rule} strokeWidth={1} />
      <Circle cx={C} cy={C} r={R_IN} fill="none" stroke={colors.rule} strokeWidth={1} />
      {path.length > 1 && (
        <Polyline
          points={path.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}
          fill="none"
          stroke={colors.ink}
          strokeOpacity={0.8}
          strokeWidth={1.6}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
      {all.map((k) => {
        const id = keyStr(k);
        const p = wheelPos(k);
        const on = used.has(id);
        const r = on ? (k.l === 'B' ? 12 : 10) : 4;
        return (
          <G key={id}>
            <Circle
              cx={p.x}
              cy={p.y}
              r={r}
              fill={on ? keyColor(k) : colors.bg}
              stroke={on ? colors.bg : colors.rule}
              strokeWidth={on ? 2 : 1.2}
            />
            {on && (
              <SvgText x={p.x} y={p.y + 3.2} fontSize={k.l === 'B' ? 9 : 8} fontWeight="700" fill={colors.bg} textAnchor="middle">
                {id}
              </SvgText>
            )}
          </G>
        );
      })}
    </Svg>
  );
}
