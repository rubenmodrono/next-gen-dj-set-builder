export type Strictness = 'strict' | 'energy_boost' | 'permissive';

export interface CamelotKey {
  n: number; // 1..12
  l: 'A' | 'B';
}

export type TransitionType =
  | 'perfect'
  | 'adjacent'
  | 'relative'
  | 'diagonal'
  | 'boost1'
  | 'boost2'
  | 'drop'
  | 'clash';

export interface RawTrack {
  artists: string[];
  title: string;
  mix?: string | null;
  genre?: string | null;
  bpm: number | null;
  key: string | null;
  previewUrl?: string | null;
  previewStartMs?: number | null;
}

export interface Track {
  artist: string;
  title: string;
  mix: string | null;
  bpm: number;
  key: CamelotKey;
  energy: number;
  genre: string | null;
  previewUrl: string | null;
  previewStartMs: number | null;
}

export interface Segment {
  name: string;
  weight: number;
  bpmStart: number;
  bpmEnd: number;
  eMin: number;
  eMax: number;
}

export interface CurvePoint {
  seg: number;
  name: string;
  bpm: number;
  eMin: number;
  eMax: number;
}

export interface PlannedTrack {
  track: Track;
  point: CurvePoint;
  transition: [TransitionType, number] | null;
}

export interface DroppedTrack {
  label: string;
  reason: string;
}
