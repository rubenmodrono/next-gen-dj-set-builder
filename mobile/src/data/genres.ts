import type { Segment } from '../core/types';

export interface GenreInfo {
  id: string;
  label: string;
  slug: string;
  beatportId: number;
  /** BPM outside this window is treated as a data error on the chart and dropped. */
  bpmMin: number;
  bpmMax: number;
  /** BPM window used to build the default curve. */
  curveLo: number;
  curveHi: number;
}

/** Beatport genre pages checked to exist: /genre/<slug>/<id>/top-100 */
export const GENRES: GenreInfo[] = [
  { id: 'progressive-house', label: 'Progressive House', slug: 'progressive-house', beatportId: 15, bpmMin: 116, bpmMax: 132, curveLo: 118, curveHi: 128 },
  { id: 'tech-house', label: 'Tech House', slug: 'tech-house', beatportId: 11, bpmMin: 120, bpmMax: 136, curveLo: 124, curveHi: 132 },
  { id: 'melodic-house-techno', label: 'Melodic House & Techno', slug: 'melodic-house-and-techno', beatportId: 90, bpmMin: 114, bpmMax: 130, curveLo: 118, curveHi: 126 },
  { id: 'house', label: 'House', slug: 'house', beatportId: 5, bpmMin: 116, bpmMax: 132, curveLo: 120, curveHi: 128 },
  { id: 'deep-house', label: 'Deep House', slug: 'deep-house', beatportId: 12, bpmMin: 110, bpmMax: 128, curveLo: 116, curveHi: 124 },
  { id: 'afro-house', label: 'Afro House', slug: 'afro-house', beatportId: 89, bpmMin: 110, bpmMax: 130, curveLo: 116, curveHi: 124 },
  { id: 'techno-peak', label: 'Techno (Peak Time)', slug: 'techno-peak-time-driving', beatportId: 6, bpmMin: 124, bpmMax: 146, curveLo: 130, curveHi: 140 },
  { id: 'trance', label: 'Trance (Main Floor)', slug: 'trance-main-floor', beatportId: 7, bpmMin: 126, bpmMax: 146, curveLo: 130, curveHi: 140 },
];

export const chartUrl = (g: GenreInfo): string =>
  `https://www.beatport.com/genre/${g.slug}/${g.beatportId}/top-100`;

/** Warm-up 25 %, Peak time 50 %, Closing 25 %, energy windows from the project spec. */
export function defaultSegments(g: GenreInfo): Segment[] {
  const r = g.curveHi - g.curveLo;
  const at = (f: number): number => Math.round(g.curveLo + f * r);
  return [
    { name: 'Warm-up', weight: 25, bpmStart: at(0.1), bpmEnd: at(0.3), eMin: 2, eMax: 5 },
    { name: 'Peak time', weight: 50, bpmStart: at(0.6), bpmEnd: g.curveHi, eMin: 7, eMax: 10 },
    { name: 'Closing', weight: 25, bpmStart: at(0.6), bpmEnd: at(0.3), eMin: 4, eMax: 6.5 },
  ];
}
