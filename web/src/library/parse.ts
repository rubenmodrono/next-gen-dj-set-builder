import type { RawTrack } from '../core/types';

export type LibraryFormat = 'rekordbox' | 'traktor' | 'csv';

export interface ParsedLibrary {
  format: LibraryFormat;
  tracks: RawTrack[];
  /** Entries found but unusable (no artist/title). Entries without BPM or key are kept; the planner reports them. */
  skipped: number;
}

export type XmlParser = (text: string) => Document;
const browserXml: XmlParser = (text) => new DOMParser().parseFromString(text, 'text/xml');

/** Decodes a file's bytes: UTF-8 (with or without BOM) or UTF-16 (rekordbox .txt exports). */
export function decodeText(buf: ArrayBuffer): string {
  const b = new Uint8Array(buf);
  if (b.length >= 2 && b[0] === 0xff && b[1] === 0xfe) return new TextDecoder('utf-16le').decode(b.subarray(2));
  if (b.length >= 2 && b[0] === 0xfe && b[1] === 0xff) return new TextDecoder('utf-16be').decode(b.subarray(2));
  return new TextDecoder('utf-8').decode(b).replace(/^﻿/, '');
}

const ENT: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
/** Browsers already decode entities in attributes; some XML parsers do not, so decode what is left. */
const unent = (v: string): string =>
  v.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e: string) =>
    e[0] === '#' ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : Number(e.slice(1))) : ENT[e.toLowerCase()] ?? m);
const attr = (el: Element | undefined, name: string): string => unent((el?.getAttribute(name) ?? '').trim());

const num = (v: string | null | undefined): number | null => {
  if (v == null) return null;
  const n = Number(String(v).trim().replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? n : null;
};

/** rekordbox: File > Export Collection in xml format. Tracks live under <COLLECTION>; playlists only reference them. */
export function parseRekordboxXml(text: string, xml: XmlParser = browserXml): ParsedLibrary {
  const doc = xml(text);
  const col = doc.getElementsByTagName('COLLECTION')[0];
  const tracks: RawTrack[] = [];
  let skipped = 0;
  if (col) {
    for (const el of Array.from(col.getElementsByTagName('TRACK'))) {
      const title = attr(el, 'Name');
      const artist = attr(el, 'Artist');
      if (!title || !artist) {
        skipped++;
        continue;
      }
      const mix = attr(el, 'Mix');
      tracks.push({
        artists: [artist], title, mix: mix || null, genre: attr(el, 'Genre') || null,
        bpm: num(el.getAttribute('AverageBpm')), key: attr(el, 'Tonality') || null,
      });
    }
  }
  return { format: 'rekordbox', tracks, skipped };
}

// Traktor stores the key as an index: 0-11 major from C, 12-23 minor from C.
const TRAKTOR_NOTES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
const traktorIndexKey = (v: number): string | null =>
  Number.isInteger(v) && v >= 0 && v <= 23 ? `${TRAKTOR_NOTES[v % 12]}${v >= 12 ? 'm' : ''}` : null;

/** Traktor: collection.nml. Key comes from INFO@KEY (Open Key) or, failing that, MUSICAL_KEY@VALUE. */
export function parseTraktorNml(text: string, xml: XmlParser = browserXml): ParsedLibrary {
  const doc = xml(text);
  const col = doc.getElementsByTagName('COLLECTION')[0];
  const tracks: RawTrack[] = [];
  let skipped = 0;
  if (col) {
    for (const el of Array.from(col.getElementsByTagName('ENTRY'))) {
      const title = attr(el, 'TITLE');
      const artist = attr(el, 'ARTIST');
      if (!title || !artist) {
        skipped++;
        continue;
      }
      const info = el.getElementsByTagName('INFO')[0];
      const tempo = el.getElementsByTagName('TEMPO')[0];
      const mk = el.getElementsByTagName('MUSICAL_KEY')[0];
      let key = attr(info, 'KEY') || null;
      if (!key && mk) key = traktorIndexKey(Number(mk.getAttribute('VALUE')));
      tracks.push({
        artists: [artist], title, mix: null, genre: attr(info, 'GENRE') || null,
        bpm: num(tempo?.getAttribute('BPM')), key,
      });
    }
  }
  return { format: 'traktor', tracks, skipped };
}

/** Splits CSV text into rows. Handles quotes, escaped quotes and newlines inside quotes. */
export function splitCsv(text: string, delim: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else q = false;
      } else cell += c;
    } else if (c === '"') q = true;
    else if (c === delim) {
      row.push(cell);
      cell = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(cell);
      cell = '';
      if (row.some((x) => x.trim() !== '')) rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell);
  if (row.some((x) => x.trim() !== '')) rows.push(row);
  return rows;
}

const fold = (s: string): string =>
  s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();

const HEADERS = {
  artist: ['artist', 'artists', 'artista', 'artistas', 'interprete', 'track artist'],
  title: ['title', 'track', 'track title', 'track name', 'name', 'titulo', 'nombre', 'tema', 'song', 'song name'],
  bpm: ['bpm', 'tempo', 'average bpm', 'averagebpm'],
  key: ['key', 'tonality', 'initial key', 'initialkey', 'camelot', 'camelot key', 'tonalidad', 'musical key', 'open key', 'key camelot'],
  genre: ['genre', 'genero', 'style', 'estilo'],
  mix: ['mix', 'mix name', 'version', 'versions'],
} as const;

function detectDelimiter(firstLine: string): string {
  const counts = [',', ';', '\t'].map((d) => [d, firstLine.split(d).length - 1] as const);
  counts.sort((a, b) => b[1] - a[1]);
  return counts[0][1] > 0 ? counts[0][0] : ',';
}

/** CSV/TSV with a header row. Column names are matched by common English and Spanish synonyms. */
export function parseCsv(text: string): ParsedLibrary {
  const clean = text.replace(/^﻿/, '');
  const delim = detectDelimiter(clean.split(/\r?\n/, 1)[0] ?? '');
  const rows = splitCsv(clean, delim);
  const head = (rows[0] ?? []).map(fold);
  const col = (names: readonly string[]): number => head.findIndex((h) => names.includes(h));
  const idx = {
    artist: col(HEADERS.artist), title: col(HEADERS.title), bpm: col(HEADERS.bpm),
    key: col(HEADERS.key), genre: col(HEADERS.genre), mix: col(HEADERS.mix),
  };
  if (idx.artist < 0 || idx.title < 0) {
    throw new Error('No encuentro las columnas de artista y título en la primera fila.');
  }
  const tracks: RawTrack[] = [];
  let skipped = 0;
  for (const r of rows.slice(1)) {
    const artist = (r[idx.artist] ?? '').trim();
    const title = (r[idx.title] ?? '').trim();
    if (!artist || !title) {
      skipped++;
      continue;
    }
    tracks.push({
      artists: [artist], title,
      mix: idx.mix >= 0 ? (r[idx.mix] ?? '').trim() || null : null,
      genre: idx.genre >= 0 ? (r[idx.genre] ?? '').trim() || null : null,
      bpm: idx.bpm >= 0 ? num(r[idx.bpm]) : null,
      key: idx.key >= 0 ? (r[idx.key] ?? '').trim() || null : null,
    });
  }
  return { format: 'csv', tracks, skipped };
}

/** Detects the format from the content and parses it. */
export function parseLibraryText(text: string, xml: XmlParser = browserXml): ParsedLibrary {
  const head = text.slice(0, 4000);
  let lib: ParsedLibrary;
  if (/<DJ_PLAYLISTS[\s>]/i.test(head)) lib = parseRekordboxXml(text, xml);
  else if (/<NML[\s>]/i.test(head)) lib = parseTraktorNml(text, xml);
  else if (/^\s*</.test(head)) throw new Error('Es un XML, pero no reconozco el formato. Exporta desde rekordbox (XML) o Traktor (NML).');
  else lib = parseCsv(text);
  if (!lib.tracks.length) throw new Error('El archivo no contiene temas con artista y título.');
  return lib;
}

export const FORMAT_LABEL: Record<LibraryFormat, string> = { rekordbox: 'rekordbox XML', traktor: 'Traktor NML', csv: 'CSV' };
