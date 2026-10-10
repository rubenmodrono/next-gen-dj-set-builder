import React from 'react';
import Svg, { Circle, G, Line, Polygon, Polyline, Text as SvgText } from 'react-native-svg';
import { keyColor } from './Wheel';
import { clamp, locate } from '../core/curve';
import type { PlannedTrack, Segment } from '../core/types';

export interface CurveColors {
  panel: string;
  ink: string;
  muted: string;
  rule: string;
  signal: string;
}

const VB_W = 360;
const VB_H = 240;
const X0 = 34;
const X1 = 352;
const PW = X1 - X0;
const BPM_TOP = 20;
const BPM_H = 102;
const EN_TOP = 152;
const EN_H = 58;
const LABEL_Y = 232;

interface Props {
  segments: Segment[];
  items: PlannedTrack[];
  width: number;
  colors: CurveColors;
}

export function Curve({ segments, items, width, colors }: Props): React.JSX.Element | null {
  const valid = segments.every(
    (s) => s.weight > 0 && [s.bpmStart, s.bpmEnd, s.eMin, s.eMax].every((v) => Number.isFinite(v)),
  );
  if (!valid || width <= 0) return null;

  const SAMPLES = 90;
  const curve = Array.from({ length: SAMPLES + 1 }, (_, i) => ({ t: i / SAMPLES, ...locate(segments, i / SAMPLES) }));
  const bpms = curve.map((c) => c.bpm).concat(items.map((it) => it.track.bpm));
  const lo = Math.floor(Math.min(...bpms) - 3);
  const hi = Math.ceil(Math.max(...bpms) + 3);
  const xs = (t: number): number => X0 + t * PW;
  const yb = (b: number): number => BPM_TOP + BPM_H - ((b - lo) / (hi - lo || 1)) * BPM_H;
  const ye = (e: number): number => EN_TOP + EN_H - (clamp(e, 0, 10) / 10) * EN_H;
  const pts = (list: [number, number][]): string => list.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

  const total = segments.reduce((a, s) => a + s.weight, 0);
  let acc = 0;
  const spans = segments.map((s) => {
    const a = acc / total;
    acc += s.weight;
    return { s, a, b: acc / total };
  });

  const top = curve.map((c): [number, number] => [xs(c.t), ye(c.eMax)]);
  const bottom = curve.slice().reverse().map((c): [number, number] => [xs(c.t), ye(c.eMin)]);
  const n = items.length;

  return (
    <Svg width={width} height={(width * VB_H) / VB_W} viewBox={`0 0 ${VB_W} ${VB_H}`}>
      {[lo, Math.round((lo + hi) / 2), hi].map((b) => (
        <G key={`b${b}`}>
          <Line x1={X0} x2={X1} y1={yb(b)} y2={yb(b)} stroke={colors.rule} strokeWidth={0.8} />
          <SvgText x={X0 - 5} y={yb(b) + 3} fontSize={9.5} fill={colors.muted} textAnchor="end">{String(b)}</SvgText>
        </G>
      ))}
      {[0, 5, 10].map((e) => (
        <G key={`e${e}`}>
          <Line x1={X0} x2={X1} y1={ye(e)} y2={ye(e)} stroke={colors.rule} strokeWidth={0.8} />
          <SvgText x={X0 - 5} y={ye(e) + 3} fontSize={9.5} fill={colors.muted} textAnchor="end">{String(e)}</SvgText>
        </G>
      ))}
      <SvgText x={X0} y={BPM_TOP - 8} fontSize={9.5} fill={colors.muted}>BPM</SvgText>
      <SvgText x={X0} y={EN_TOP - 8} fontSize={9.5} fill={colors.muted}>Energía (1-10)</SvgText>

      {spans.map(({ s, a, b }, i) => {
        const maxChars = Math.max(3, Math.floor(((b - a) * PW) / 6.2));
        const label = s.name.length > maxChars ? `${s.name.slice(0, maxChars - 1)}…` : s.name;
        return (
          <G key={`s${i}`}>
            {i > 0 && (
              <Line x1={xs(a)} x2={xs(a)} y1={BPM_TOP} y2={EN_TOP + EN_H} stroke={colors.rule} strokeWidth={1} strokeDasharray="3 3" />
            )}
            <SvgText x={(xs(a) + xs(b)) / 2} y={LABEL_Y} fontSize={10.5} fontWeight="700" fill={colors.ink} textAnchor="middle">{label}</SvgText>
          </G>
        );
      })}

      <Polygon points={pts(top.concat(bottom))} fill={colors.signal} fillOpacity={0.16} />
      <Polyline points={pts(curve.map((c): [number, number] => [xs(c.t), yb(c.bpm)]))} fill="none" stroke={colors.signal} strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" />

      {n > 0 && (
        <Polyline
          points={pts(items.map((it, i): [number, number] => [xs((i + 0.5) / n), ye(it.track.energy)]))}
          fill="none"
          stroke={colors.muted}
          strokeWidth={1.25}
        />
      )}
      {items.map((it, i) => {
        const fill = keyColor(it.track.key);
        const x = xs((i + 0.5) / n);
        return (
          <G key={`d${i}`}>
            <Circle cx={x} cy={yb(it.track.bpm)} r={4.6} fill={fill} stroke={colors.panel} strokeWidth={1.5} />
            <Circle cx={x} cy={ye(it.track.energy)} r={3.2} fill={fill} stroke={colors.panel} strokeWidth={1.5} />
          </G>
        );
      })}
    </Svg>
  );
}
