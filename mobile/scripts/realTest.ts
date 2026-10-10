import fs from 'node:fs';
import { keyStr } from '../src/core/camelot';
import { formatLine, orderTracks, preparePool, slotsFor } from '../src/core/planner';
import { defaultSegments, GENRES } from '../src/data/genres';
import type { RawTrack, Strictness } from '../src/core/types';

const genre = GENRES.find((g) => g.id === 'progressive-house')!;
const rows = fs.readFileSync(new URL('../fixtures/progressive-house-top100.txt', import.meta.url), 'utf8').trim().split('\n');
const raw: RawTrack[] = rows.map((line) => {
  const [, artists, title, g, bpm, key] = line.split(' | ');
  return { artists: artists.split(', '), title, mix: null, genre: g, bpm: Number(bpm), key };
});

const duration = Number(process.argv[2] ?? 60);
const strictness = (process.argv[3] ?? 'energy_boost') as Strictness;
const segs = defaultSegments(genre);
const { pool, dropped } = preparePool(raw, { segments: segs, bpmMin: genre.bpmMin, bpmMax: genre.bpmMax });
const set = orderTracks(pool, segs, strictness, slotsFor(duration));

console.log(`Genre: ${genre.label} | ${duration} min | harmony: ${strictness}`);
console.log(`Chart rows: ${raw.length} | usable: ${pool.length} | dropped: ${dropped.length}`);
console.log('Curve:', segs.map((s) => `${s.name} ${s.bpmStart}-${s.bpmEnd}`).join(' | '), '\n');
set.forEach((it, i) => {
  const tr = it.transition ? `${it.transition[0]}(${it.transition[1]})` : '-';
  console.log(`${String(i + 1).padStart(2)}. [${it.point.name.padEnd(9)}] ${formatLine(it.track)}   <- ${tr}`);
});
const costs = set.slice(1).map((s) => s.transition![1]);
console.log(`\nAvg harmonic cost: ${(costs.reduce((a, b) => a + b, 0) / costs.length).toFixed(2)} | max: ${Math.max(...costs)}`);
console.log('Keys:', set.map((s) => keyStr(s.track.key)).join(' '));
console.log('BPMs:', set.map((s) => s.track.bpm).join(' '));
console.log('\nDropped:'); for (const d of dropped.slice(0, 40)) console.log(` - ${d.label}: ${d.reason}`);
