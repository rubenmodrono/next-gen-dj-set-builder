import assert from 'node:assert/strict';
import { DOMParser } from 'linkedom';
import { demoLibrary } from '../src/library/demo';
import { decodeText, parseCsv, parseLibraryText, parseRekordboxXml, parseTraktorNml, splitCsv } from '../src/library/parse';
import { test } from './helpers';

const xml = (t: string) => new DOMParser().parseFromString(t, 'text/xml') as unknown as Document;

const REKORDBOX = `<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0"><PRODUCT Name="rekordbox" Version="6.7.0" Company="AlphaTheta"/>
<COLLECTION Entries="3">
<TRACK TrackID="1" Name="Hivemind" Artist="Jamie Stevens" Genre="Progressive House" AverageBpm="124.00" Tonality="Gm" Mix="Extended Mix"><TEMPO Inizio="0.0" Bpm="124.00" Metro="4/4" Battito="1"/></TRACK>
<TRACK TrackID="2" Name="Night &amp; Day" Artist="A, B" Genre="Tech House" AverageBpm="126.00" Tonality="8A"/>
<TRACK TrackID="3" Name="" Artist="X" AverageBpm="120.00" Tonality="C"/>
</COLLECTION>
<PLAYLISTS><NODE Type="0" Name="ROOT" Count="1"><NODE Name="Set" Type="1" KeyType="0" Entries="1"><TRACK Key="1"/></NODE></NODE></PLAYLISTS>
</DJ_PLAYLISTS>`;

test('rekordbox XML: reads COLLECTION only, decodes entities, counts unusable entries', () => {
  const lib = parseRekordboxXml(REKORDBOX, xml);
  assert.equal(lib.format, 'rekordbox');
  assert.equal(lib.tracks.length, 2);
  assert.equal(lib.skipped, 1);
  assert.deepEqual(lib.tracks[0], { artists: ['Jamie Stevens'], title: 'Hivemind', mix: 'Extended Mix', genre: 'Progressive House', bpm: 124, key: 'Gm' });
  assert.equal(lib.tracks[1].title, 'Night & Day');
  assert.equal(lib.tracks[1].key, '8A');
});

const NML = `<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19"><HEAD COMPANY="www.native-instruments.com" PROGRAM="Traktor"/>
<COLLECTION ENTRIES="2">
<ENTRY TITLE="Illusions" ARTIST="Quivver"><INFO GENRE="Progressive House" KEY="11m"/><TEMPO BPM="123.000000" BPM_QUALITY="100"/></ENTRY>
<ENTRY TITLE="Without key" ARTIST="Z"><INFO GENRE="House"/><TEMPO BPM="125.5"/><MUSICAL_KEY VALUE="21"/></ENTRY>
</COLLECTION></NML>`;

test('Traktor NML: Open Key from INFO, index fallback from MUSICAL_KEY', () => {
  const lib = parseTraktorNml(NML, xml);
  assert.equal(lib.tracks.length, 2);
  assert.equal(lib.tracks[0].key, '11m');
  assert.equal(lib.tracks[0].bpm, 123);
  assert.equal(lib.tracks[1].key, 'Am'); // index 21 = minor, 21-12 = 9 -> A
  assert.equal(lib.tracks[1].bpm, 125.5);
});

test('CSV: delimiter detection, Spanish headers, quotes, BOM', () => {
  const csv = '﻿Artista;Título;BPM;Tonalidad;Género\n"Quivver";"Illusions (Extended Mix)";123,5;4A;Progressive House\nA;B;;;\n;sin artista;120;8A;\n';
  const lib = parseCsv(csv);
  assert.equal(lib.tracks.length, 2);
  assert.equal(lib.skipped, 1);
  assert.equal(lib.tracks[0].bpm, 123.5);
  assert.equal(lib.tracks[0].key, '4A');
  assert.equal(lib.tracks[1].bpm, null);
  assert.deepEqual(splitCsv('a,"b ""q"", c",d\n1,2,3', ','), [['a', 'b "q", c', 'd'], ['1', '2', '3']]);
  assert.throws(() => parseCsv('foo,bar\n1,2'), /artista y título/);
});

test('CSV: Mixed In Key / Serato style English headers with tabs', () => {
  const lib = parseCsv('Track Title\tArtist\tTempo\tInitial Key\nHivemind\tJamie\t124\tGm\n');
  assert.equal(lib.tracks[0].title, 'Hivemind');
  assert.equal(lib.tracks[0].key, 'Gm');
});

test('parseLibraryText detects the format and rejects the rest', () => {
  assert.equal(parseLibraryText(REKORDBOX, xml).format, 'rekordbox');
  assert.equal(parseLibraryText(NML, xml).format, 'traktor');
  assert.equal(parseLibraryText('Artist,Title,BPM,Key\nA,B,120,8A', xml).format, 'csv');
  assert.throws(() => parseLibraryText('<foo/>', xml), /no reconozco/);
  assert.throws(() => parseLibraryText('Artist,Title\n', xml), /no contiene/);
});

test('decodeText: UTF-8 BOM and UTF-16 LE', () => {
  const u8 = new Uint8Array([0xef, 0xbb, 0xbf, 0x41, 0xc3, 0xb1]).buffer;
  assert.equal(decodeText(u8), 'Añ');
  const u16 = new Uint8Array([0xff, 0xfe, 0x41, 0x00, 0xf1, 0x00]).buffer;
  assert.equal(decodeText(u16), 'Añ');
});

test('demo library is deterministic, unique and has valid data', () => {
  const a = demoLibrary();
  const b = demoLibrary();
  assert.equal(a.length, 350);
  assert.deepEqual(a, b);
  assert.equal(new Set(a.map((t) => `${t.artists[0]}|${t.title}`)).size, a.length);
  assert.ok(a.every((t) => t.bpm! >= 116 && t.bpm! <= 132 && t.key));
});
