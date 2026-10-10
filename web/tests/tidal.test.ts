import assert from 'node:assert/strict';
import { parseKey } from '../src/core/camelot';
import { parseTidalResponse, tidalKeyToString } from '../src/sources/tidal';
import { test } from './helpers';

// Forma JSON:API SUPUESTA a partir de la especificación de Tidal; hay que contrastarla con una respuesta real.
const SEARCH = {
  data: [{ id: 'q', type: 'searchResults', relationships: { tracks: { data: [{ id: '1', type: 'tracks' }, { id: '2', type: 'tracks' }, { id: '3', type: 'tracks' }], links: { next: '/searchResults/q/relationships/tracks?page[cursor]=abc123' } } } }],
  included: [
    { id: '1', type: 'tracks', attributes: { title: 'Hivemind', version: 'Extended Mix', bpm: 124.0, key: 'G', keyScale: 'MINOR' }, relationships: { artists: { data: [{ id: '10', type: 'artists' }, { id: '11', type: 'artists' }] } } },
    { id: '2', type: 'tracks', attributes: { title: 'Sin datos', bpm: 0, key: 'FSharp', keyScale: 'MAJOR' }, relationships: { artists: { data: [{ id: '10', type: 'artists' }] } } },
    { id: '3', type: 'tracks', attributes: { title: 'Sin artista', bpm: 126.5, key: 'Ab', keyScale: 'MINOR' }, relationships: { artists: { data: [] } } },
    { id: '10', type: 'artists', attributes: { name: 'Jamie Stevens' } },
    { id: '11', type: 'artists', attributes: { name: 'Eelke Kleijn' } },
  ],
};

test('tidal: la tonalidad se traduce a notación que entiende el motor', () => {
  assert.equal(tidalKeyToString('G', 'MINOR'), 'G Minor');
  assert.equal(tidalKeyToString('CSharp', 'MAJOR'), 'C# Major');
  assert.equal(tidalKeyToString('Ab', 'MINOR'), 'Ab Minor');
  assert.equal(tidalKeyToString('Bb', 'minor'), 'Bb Minor');
  assert.equal(tidalKeyToString('H', 'MAJOR'), null);
  assert.equal(tidalKeyToString('C', 'UNKNOWN'), null);
  assert.deepEqual(parseKey(tidalKeyToString('G', 'MINOR')), { n: 6, l: 'A' });
  assert.deepEqual(parseKey(tidalKeyToString('FSharp', 'MAJOR')), { n: 2, l: 'B' });
  assert.deepEqual(parseKey(tidalKeyToString('Ab', 'MINOR')), { n: 1, l: 'A' });
});

test('tidal: lee pistas, artistas, BPM y tonalidad de una respuesta de búsqueda', () => {
  const r = parseTidalResponse(SEARCH);
  assert.equal(r.tracks.length, 3);
  assert.deepEqual(r.tracks[0], { tidalId: '1', artists: ['Jamie Stevens', 'Eelke Kleijn'], title: 'Hivemind', mix: 'Extended Mix', genre: null, bpm: 124, key: 'G Minor' });
  assert.equal(r.tracks[1].bpm, null);
  assert.equal(r.tracks[1].key, 'F# Major');
  assert.deepEqual(r.needArtists, ['3']);
  assert.equal(r.next, 'abc123');
});

test('tidal: respuestas vacías o con otra forma no rompen nada', () => {
  assert.deepEqual(parseTidalResponse(null), { tracks: [], needArtists: [], next: null });
  assert.deepEqual(parseTidalResponse({ data: [], included: 'x' }), { tracks: [], needArtists: [], next: null });
  const byIds = parseTidalResponse({ data: [{ id: '5', type: 'tracks', attributes: { title: 'A', bpm: 120, key: 'C', keyScale: 'MAJOR' }, relationships: { artists: { data: [{ id: '9', type: 'artists' }] } } }], included: [{ id: '9', type: 'artists', attributes: { name: 'X' } }], links: { next: 'https://openapi.tidal.com/v2/tracks?page%5Bcursor%5D=zz' } });
  assert.equal(byIds.tracks[0].artists[0], 'X');
  assert.equal(byIds.next, 'zz');
});
