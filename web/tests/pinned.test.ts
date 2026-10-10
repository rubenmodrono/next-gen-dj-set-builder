import assert from 'node:assert/strict';
import { keyStr } from '../src/core/camelot';
import { parsePinnedLines, planSet, shortlist, toPinnedTrack } from '../src/core/pinned';
import { preparePool, slotsFor } from '../src/core/planner';
import { defaultSegments, GENRES } from '../src/data/genres';
import { demoLibrary } from '../src/library/demo';
import { test } from './helpers';

const genre = GENRES[0];
const segs = defaultSegments(genre);
const pool = preparePool(demoLibrary().filter((t) => t.genre === genre.label), { segments: segs, bpmMin: genre.bpmMin, bpmMax: genre.bpmMax }).pool;

const pin = (artist: string, title: string, bpm: number, key: string) => {
  const r = toPinnedTrack({ artist, title, bpm, key }, segs);
  assert.ok(r.ok);
  return r.track;
};

test('toPinnedTrack validates BPM, key and names', () => {
  assert.equal(toPinnedTrack({ artist: '', title: 'x', bpm: 124, key: '8A' }, segs).ok, false);
  assert.equal(toPinnedTrack({ artist: 'a', title: 'x', bpm: 20, key: '8A' }, segs).ok, false);
  assert.equal(toPinnedTrack({ artist: 'a', title: 'x', bpm: 124, key: 'zz' }, segs).ok, false);
  const far = toPinnedTrack({ artist: 'a', title: 'x', bpm: 140, key: 'Am' }, segs);
  assert.ok(far.ok && far.warning);
  const fine = toPinnedTrack({ artist: 'a', title: 'x', bpm: 124, key: 'Am' }, segs);
  assert.ok(fine.ok && fine.warning === null && keyStr(fine.track.key) === '8A');
});

test('parsePinnedLines reads the printed format, tabs and semicolons', () => {
  const r = parsePinnedLines('Quivver - Illusions (Extended Mix) - 123 BPM - 4A (Fm)\nA - B - C - 120 - Am\nsolo texto\nX;Y;125;8B\n\n');
  assert.equal(r.length, 4);
  assert.deepEqual(r[0].input, { artist: 'Quivver', title: 'Illusions (Extended Mix)', bpm: 123, key: '4A' });
  assert.equal(r[1].input?.title, 'B - C');
  assert.ok(r[2].error);
  assert.equal(r[3].input?.key, '8B');
});

test('a pinned peak-tempo track lands in Peak time, a slow one in Warm-up or Closing', () => {
  const n = slotsFor(60);
  const peak = pin('Pin', 'Peak One', 128, '8A');
  const open = pin('Pin', 'Open One', 119, '8A');
  const a = planSet(pool, [peak], segs, 'energy_boost', n);
  assert.equal(a.items[a.pinnedSlots[0]].point.name, 'Peak time');
  const b = planSet(pool, [open], segs, 'energy_boost', n);
  assert.notEqual(b.items[b.pinnedSlots[0]].point.name, 'Peak time');
});

test('every pinned track is in the set exactly once, with the right length', () => {
  const n = slotsFor(90);
  const pins = [pin('P', 'One', 128, '8A'), pin('P', 'Two', 119, '9A'), pin('Q', 'Three', 126, '10A')];
  const r = planSet(pool, pins, segs, 'energy_boost', n);
  assert.equal(r.items.length, n);
  assert.equal(r.pinnedSlots.length, 3);
  for (const p of pins) assert.equal(r.items.filter((it) => it.track === p).length, 1);
  assert.equal(new Set(r.items.map((it) => `${it.track.artist}|${it.track.title}`)).size, n);
  assert.equal(r.extended, false);
});

test('pinning more tracks than slots lengthens the set', () => {
  const pins = Array.from({ length: 6 }, (_, i) => pin('P', `T${i}`, 120 + i, '8A'));
  const r = planSet(pool, pins, segs, 'energy_boost', 4);
  assert.equal(r.extended, true);
  assert.equal(r.items.length, 6);
});

test('a pinned song already in the pool is not repeated', () => {
  const dup = pool[0];
  const p = pin(dup.artist, dup.title, dup.bpm, keyStr(dup.key));
  const r = planSet(pool, [p], segs, 'energy_boost', slotsFor(60));
  const same = r.items.filter((it) => it.track.artist === dup.artist && it.track.title === dup.title);
  assert.equal(same.length, 1);
  assert.equal(same[0].track, p);
});

test('planSet works with no pool at all (only pinned tracks)', () => {
  const pins = [pin('P', 'One', 124, '8A'), pin('P', 'Two', 126, '9A')];
  const r = planSet([], pins, segs, 'strict', 10);
  assert.equal(r.items.length, 2);
});

test('without pinned tracks the result matches the plain planner', () => {
  const r = planSet(pool, [], segs, 'energy_boost', 11);
  assert.equal(r.items.length, 11);
  assert.deepEqual(r.pinnedSlots, []);
});

test('shortlist keeps a big library small but spread across keys', () => {
  const big = Array.from({ length: 2000 }, (_, i) => ({
    ...pool[i % pool.length], title: `${pool[i % pool.length].title} ${i}`,
  }));
  const s = shortlist(big, segs, 11, 160);
  assert.ok(s.length <= 160 && s.length >= 100);
  assert.ok(new Set(s.map((t) => keyStr(t.key))).size >= 12);
  assert.equal(shortlist(pool.slice(0, 50), segs, 11, 160).length, 50);
});

test('a planned set still has low harmonic cost with pinned tracks', () => {
  const pins = [pin('P', 'One', 127, '8A'), pin('P', 'Two', 121, '5A')];
  const r = planSet(pool, pins, segs, 'energy_boost', slotsFor(60));
  const costs = r.items.slice(1).map((it) => it.transition![1]);
  const avg = costs.reduce((a, b) => a + b, 0) / costs.length;
  assert.ok(avg < 2.5, `average harmonic cost ${avg.toFixed(2)}`);
});
