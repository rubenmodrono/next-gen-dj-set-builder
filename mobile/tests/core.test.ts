import assert from 'node:assert/strict';
import { keyHue, keyStandard, keyStr, parseKey, transition } from '../src/core/camelot';
import { locate } from '../src/core/curve';
import { formatLine, orderTracks, preparePool } from '../src/core/planner';
import { defaultSegments, GENRES } from '../src/data/genres';
import { artistMatches, similarity } from '../src/core/match';
import { htmlToText, parseNextData } from '../src/sources/beatport';
import { parseTracksJson } from '../src/sources/llm';

let passed = 0;
const test = (name: string, fn: () => void): void => {
  fn();
  passed++;
  console.log('ok  ', name);
};

test('parseKey: standard, Beatport style, Camelot, Open Key', () => {
  const cases: [string, string][] = [
    ['Am', '8A'], ['C', '8B'], ['A Minor', '8A'], ['C Major', '8B'], ['Db Minor', '12A'],
    ['Gb Major', '2B'], ['Eb Major', '5B'], ['Bb Minor', '3A'], ['F# minor', '11A'], ['G#', '4B'],
    ['A#m', '3A'], ['A', '11B'], ['B', '1B'], ['Ab Major', '4B'], ['8a', '8A'], ['12B', '12B'],
    ['1d', '8B'], ['1m', '8A'], ['6d', '1B'], ['12m', '7A'], ['C♯m', '12A'], ['B♭', '6B'],
  ];
  for (const [input, expected] of cases) {
    const k = parseKey(input);
    assert.ok(k, `parse ${input}`);
    assert.equal(keyStr(k), expected, `${input} -> ${expected}`);
  }
  for (const bad of ['', 'H', 'Xm', '13A', '0B', 'C Dorian', null, undefined]) assert.equal(parseKey(bad), null);
});

test('keyStandard round-trips every Camelot key', () => {
  for (let n = 1; n <= 12; n++) {
    for (const l of ['A', 'B'] as const) {
      const k = { n, l };
      const back = parseKey(keyStandard(k));
      assert.ok(back);
      assert.equal(keyStr(back), keyStr(k));
    }
  }
  assert.equal(keyStandard({ n: 8, l: 'A' }), 'Am');
  assert.equal(keyStandard({ n: 8, l: 'B' }), 'C');
});

test('transition costs', () => {
  const k = (s: string) => parseKey(s)!;
  assert.deepEqual(transition(k('8A'), k('8A'), 'strict'), ['perfect', 0]);
  assert.equal(transition(k('8A'), k('9A'), 'strict')[0], 'adjacent');
  assert.equal(transition(k('8A'), k('7A'), 'strict')[0], 'adjacent');
  assert.equal(transition(k('12A'), k('1A'), 'strict')[0], 'adjacent');
  assert.equal(transition(k('8A'), k('8B'), 'strict')[0], 'relative');
  assert.equal(transition(k('8A'), k('9B'), 'strict')[0], 'diagonal');
  assert.deepEqual(transition(k('8A'), k('10A'), 'energy_boost'), ['boost2', 1]);
  assert.deepEqual(transition(k('8A'), k('10A'), 'strict'), ['boost2', 4]);
  assert.deepEqual(transition(k('8A'), k('3A'), 'energy_boost'), ['boost1', 2]);
  assert.deepEqual(transition(k('8A'), k('6A'), 'energy_boost'), ['drop', 5]);
  assert.deepEqual(transition(k('8A'), k('6A'), 'permissive'), ['drop', 2.5]);
  const clash = transition(k('8A'), k('2B'), 'strict');
  assert.equal(clash[0], 'clash');
  assert.ok(clash[1] <= 10);
  assert.ok(keyHue(k('8A')) === 210);
});

test('curve: weights and interpolation', () => {
  const segs = defaultSegments(GENRES[0]);
  assert.equal(locate(segs, 0).name, 'Warm-up');
  assert.equal(locate(segs, 0.5).name, 'Peak time');
  assert.equal(locate(segs, 1).name, 'Closing');
  assert.ok(Math.abs(locate(segs, 0.2499).bpm - segs[0].bpmEnd) < 0.05);
  assert.ok(Math.abs(locate(segs, 0.7501).bpm - segs[2].bpmStart) < 0.05);
});

test('Progressive House default curve is coherent', () => {
  const s = defaultSegments(GENRES[0]);
  assert.deepEqual(s.map((x) => [x.bpmStart, x.bpmEnd]), [[119, 121], [124, 128], [124, 121]]);
});

test('parseNextData finds tracks anywhere in the JSON', () => {
  const next = {
    props: { pageProps: { dehydratedState: { queries: [{ state: { data: { results: [
      { id: 1, name: 'Illusions', mix_name: 'Extended Mix', artists: [{ name: 'Quivver' }], genre: { name: 'Progressive House' }, bpm: 123, key: { name: 'F Minor', camelot_number: 4, camelot_letter: 'A' } },
      { id: 2, name: 'Hivemind', mix_name: 'Extended Mix', artists: [{ name: 'Jamie Stevens' }, { name: 'Christian Smith' }], genre: { name: 'Progressive House' }, bpm: '124', key: { name: 'G Minor' } },
      { id: 1, name: 'Illusions', mix_name: 'Extended Mix', artists: [{ name: 'Quivver' }], bpm: 123, key: 'F Minor' },
      { id: 3, name: 'No bpm', artists: [{ name: 'X' }] },
    ] } } }] } } },
  };
  const html = `<html><script id="__NEXT_DATA__" type="application/json">${JSON.stringify(next)}</script></html>`;
  const t = parseNextData(html);
  assert.equal(t.length, 2);
  assert.equal(t[0].key, '4A');
  assert.deepEqual(t[1].artists, ['Jamie Stevens', 'Christian Smith']);
  assert.equal(t[1].bpm, 124);
  assert.deepEqual(parseNextData('<html></html>'), []);
  assert.deepEqual(parseNextData('<script id="__NEXT_DATA__">{broken</script>'), []);
});

test('htmlToText strips scripts and keeps rows', () => {
  const t = htmlToText('<style>x{}</style><div>Row &amp; one</div><script>var a=1</script><div>Row two &#39;x&#39;</div>');
  assert.equal(t, "Row & one\nRow two 'x'");
});

test('parseTracksJson accepts plain, fenced and wrapped replies', () => {
  const arr = '[{"artists":["A"],"title":"T","mix":"Original Mix","genre":"G","bpm":"124","key":"A Minor"},{"title":"bad"}]';
  assert.equal(parseTracksJson(arr).length, 1);
  assert.equal(parseTracksJson('```json\n' + arr + '\n```')[0].bpm, 124);
  assert.equal(parseTracksJson('Here you go: ' + arr + ' done')[0].artists[0], 'A');
  assert.throws(() => parseTracksJson('no json here'));
});

test('preparePool drops bad BPM, duplicates versions and caps artists', () => {
  const segs = defaultSegments(GENRES[0]);
  const raw = [
    { artists: ['A'], title: 'Song One', mix: 'Original Mix', bpm: 122, key: 'A Minor' },
    { artists: ['A'], title: 'Song One', mix: 'Remix', bpm: 122, key: 'A Minor' },
    { artists: ['A'], title: 'Other', mix: null, bpm: 123, key: 'C' },
    { artists: ['A'], title: 'Third thing', mix: null, bpm: 123, key: 'C' },
    { artists: ['B'], title: 'Slow', mix: null, bpm: 78, key: 'F' },
    { artists: ['B'], title: 'No key', mix: null, bpm: 124, key: null },
    { artists: ['B'], title: 'Fine', mix: null, bpm: 125, key: 'Db Minor' },
  ];
  const { pool, dropped } = preparePool(raw, { segments: segs, bpmMin: 116, bpmMax: 132 });
  assert.deepEqual(pool.map((t) => t.title), ['Song One', 'Other', 'Fine']);
  assert.equal(dropped.length, 4);
  assert.ok(dropped.some((d) => d.reason.includes('78')));
  assert.equal(formatLine(pool[2]), 'B - Fine - 125 BPM - 12A (C#m)');
});

test('orderTracks follows the curve and avoids repeats', () => {
  const segs = defaultSegments(GENRES[0]);
  const raw = Array.from({ length: 30 }, (_, i) => ({
    artists: [`Artist ${i}`], title: `Track ${i}`, mix: null, bpm: 119 + (i % 10), key: ['8A', '9A', '10A', '8B', '7A'][i % 5],
  }));
  const { pool } = preparePool(raw, { segments: segs, bpmMin: 116, bpmMax: 132 });
  const set = orderTracks(pool, segs, 'energy_boost', 11);
  assert.equal(set.length, 11);
  assert.equal(new Set(set.map((s) => s.track.title)).size, 11);
  const first = set[0].track.bpm, mid = set[5].track.bpm;
  assert.ok(mid > first, `peak (${mid}) should be above warm-up (${first})`);
  assert.equal(set[0].transition, null);
});

test('similarity and artist matching for previews', () => {
  assert.equal(similarity('I Got You', 'I Got You (Extended Mix)'), 1);
  assert.ok(similarity('Self CNTRL', 'Self Control') < 0.9);
  assert.ok(similarity('Tonka', 'Completely Different') < 0.5);
  assert.ok(artistMatches('Tim Green', 'Tim Green'));
  assert.ok(artistMatches('Dosem', 'DOSEM'));
  assert.ok(!artistMatches('Dosem', 'Dolly Parton'));
});

test('parseNextData keeps Beatport preview URL and start', () => {
  const next = { a: [{ id: 9, name: 'X', mix_name: 'Original Mix', artists: [{ name: 'Y' }], bpm: 124, key: 'A Minor', sample_url: 'https://geo-samples.beatport.com/track/abc.LOFI.mp3', sample_start_ms: 90000 },
    { id: 10, name: 'Z', artists: [{ name: 'Y' }], bpm: 124, key: 'A Minor', sample_url: 'http://insecure/x.mp3' }] };
  const t = parseNextData(`<script id="__NEXT_DATA__">${JSON.stringify(next)}</script>`);
  assert.equal(t[0].previewUrl, 'https://geo-samples.beatport.com/track/abc.LOFI.mp3');
  assert.equal(t[0].previewStartMs, 90000);
  assert.equal(t[1].previewUrl, null);
});

console.log(`\n${passed} tests passed`);
