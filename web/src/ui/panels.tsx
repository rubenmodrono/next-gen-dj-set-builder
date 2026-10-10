import { useMemo, useRef, useState, type DragEvent } from 'react';
import { keyStr, parseKey } from '../core/camelot';
import { norm } from '../core/planner';
import { parsePinnedLines, toPinnedTrack, type PinnedInput } from '../core/pinned';
import type { Segment } from '../core/types';
import { FORMAT_LABEL } from '../library/parse';
import type { StoredLibrary } from '../library/store';
import type { LlmSettings } from '../sources/llm';
import type { SegInput } from '../state';
import { Field, IconButton, Icon, Segmented } from './ui';

/* ───────────────────────── Biblioteca ───────────────────────── */

export function LibraryPanel(props: {
  library: StoredLibrary | null;
  usable: number;
  busy: boolean;
  error: string | null;
  onFile: (f: File) => void;
  onDemo: () => void;
  onClear: () => void;
}): React.JSX.Element {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const drop = (e: DragEvent): void => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) props.onFile(f);
  };
  const lib = props.library;
  return (
    <div className="stack">
      <input
        ref={input} type="file" accept=".xml,.nml,.csv,.tsv,.txt,text/csv,text/xml" className="sr-only" tabIndex={-1}
        aria-label="Archivo de biblioteca"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) props.onFile(f); e.target.value = ''; }}
      />
      {lib ? (
        <div className="libcard">
          <p className="libname">{lib.name}</p>
          <p className="muted">
            {lib.format === 'demo' ? 'Datos ficticios de ejemplo' : FORMAT_LABEL[lib.format]} · {lib.tracks.length.toLocaleString('es-ES')} temas · {props.usable.toLocaleString('es-ES')} con BPM y tonalidad
          </p>
          <div className="row-actions">
            <button type="button" className="btn" onClick={() => input.current?.click()}>Cambiar biblioteca</button>
            <button type="button" className="btn ghost" onClick={props.onClear}>Quitar biblioteca</button>
          </div>
        </div>
      ) : (
        <div
          className={`dropzone ${over ? 'over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
        >
          <p className="dz-title">Arrastra aquí tu biblioteca</p>
          <p className="muted">rekordbox (XML), Traktor (NML) o un CSV con artista, título, BPM y tonalidad.</p>
          <div className="row-actions">
            <button type="button" className="btn primary" aria-busy={props.busy || undefined} onClick={() => input.current?.click()}>
              {props.busy ? 'Leyendo…' : 'Importar biblioteca'}
            </button>
            <button type="button" className="btn" onClick={props.onDemo}>Usar biblioteca de ejemplo</button>
          </div>
        </div>
      )}
      {props.error && <p className="msg error" role="alert">{props.error}</p>}
      <p className="msg hint">Tu biblioteca se lee en este navegador y se guarda solo en este dispositivo. No se sube a ningún servidor.</p>
      <details className="help">
        <summary>Cómo exportar desde mi programa</summary>
        <ul>
          <li><strong>rekordbox:</strong> Archivo › Exportar colección en formato xml.</li>
          <li><strong>Traktor:</strong> abre <code>collection.nml</code> en la carpeta Native Instruments › Traktor de tus Documentos.</li>
          <li><strong>Otros (Serato, Engine DJ, VirtualDJ, Mixed In Key):</strong> exporta una lista a CSV. Se reconocen las columnas Artist, Title, BPM y Key, en español o en inglés.</li>
        </ul>
      </details>
    </div>
  );
}

/* ───────────────────────── Temas fijados ───────────────────────── */

export interface PinnedItem { id: string; input: PinnedInput }

type Tab = 'search' | 'manual' | 'paste';
const MAX_PINNED = 20;

/** The whole page is one form, so these sub-forms are plain groups: Enter in a text field adds the track. */
const enterSubmits = (submit: () => void) => (e: React.KeyboardEvent): void => {
  if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') {
    e.preventDefault();
    submit();
  }
};

export function PinnedPanel(props: {
  library: StoredLibrary | null;
  pinned: PinnedItem[];
  segments: Segment[];
  onAdd: (inputs: PinnedInput[]) => string | null;
  onRemove: (id: string) => void;
}): React.JSX.Element {
  const [tab, setTab] = useState<Tab>(props.library ? 'search' : 'manual');
  return (
    <div className="stack">
      <Segmented
        legend="Cómo añadir temas" value={tab} onChange={setTab} hideLegend
        options={[{ value: 'search', label: 'Buscar' }, { value: 'manual', label: 'A mano' }, { value: 'paste', label: 'Pegar lista' }]}
      />
      {tab === 'search' && <SearchTab library={props.library} onAdd={props.onAdd} />}
      {tab === 'manual' && <ManualTab onAdd={props.onAdd} />}
      {tab === 'paste' && <PasteTab onAdd={props.onAdd} />}

      {props.pinned.length === 0 ? (
        <p className="msg hint">Los temas que fijes entrarán en el set seguro. La app los coloca donde mejor encajan en la curva y en la mezcla armónica.</p>
      ) : (
        <ul className="pinlist" aria-label="Temas fijados">
          {props.pinned.map((p) => {
            const r = toPinnedTrack(p.input, props.segments);
            const k = parseKey(p.input.key);
            return (
              <li key={p.id}>
                <div className="pin-main">
                  <p className="pin-title">{p.input.artist} - {p.input.title}</p>
                  <p className="muted mono">{p.input.bpm} BPM · {k ? keyStr(k) : p.input.key}</p>
                  {r.ok && r.warning && <p className="msg warn">{r.warning}</p>}
                </div>
                <IconButton label={`Quitar ${p.input.title}`} onClick={() => props.onRemove(p.id)}>{Icon.close}</IconButton>
              </li>
            );
          })}
        </ul>
      )}
      {props.pinned.length >= MAX_PINNED && <p className="msg warn">Has llegado al máximo de {MAX_PINNED} temas fijados.</p>}
    </div>
  );
}

function SearchTab(props: { library: StoredLibrary | null; onAdd: (i: PinnedInput[]) => string | null }): React.JSX.Element {
  const [q, setQ] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const index = useMemo(
    () => (props.library?.tracks ?? [])
      .filter((t) => t.bpm && t.key && parseKey(t.key))
      .map((t) => ({ t, hay: norm(`${t.artists.join(' ')} ${t.title}`) })),
    [props.library],
  );
  const words = norm(q).split(' ').filter(Boolean);
  const hits = words.length && norm(q).length >= 2 ? index.filter((x) => words.every((w) => x.hay.includes(w))).slice(0, 8) : [];
  if (!props.library) {
    return <p className="msg hint">Importa tu biblioteca para buscar en ella, o añade el tema a mano.</p>;
  }
  return (
    <div className="stack">
      <Field id="pin-q" label="Buscar en tu biblioteca" hint="Escribe parte del artista o del título.">
        {(a) => (
          <input
            id={a.id} aria-describedby={a.describedBy} type="search" autoComplete="off" value={q}
            onChange={(e) => { setQ(e.target.value); setMsg(null); }}
          />
        )}
      </Field>
      {hits.length > 0 && (
        <ul className="hits" aria-label="Resultados">
          {hits.map(({ t }, i) => (
            <li key={i}>
              <button
                type="button" className="hit"
                onClick={() => {
                  const err = props.onAdd([{ artist: t.artists.join(', '), title: t.title, mix: t.mix, bpm: t.bpm as number, key: t.key as string }]);
                  setMsg(err);
                  if (!err) setQ('');
                }}
              >
                <span className="hit-title">{t.artists.join(', ')} - {t.title}</span>
                <span className="muted mono">{t.bpm} · {keyStr(parseKey(t.key)!)}</span>
                <span className="hit-act">Fijar tema</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {words.length > 0 && hits.length === 0 && <p className="msg hint">No hay temas con BPM y tonalidad que coincidan. Prueba con menos palabras.</p>}
      {msg && <p className="msg error" role="alert">{msg}</p>}
    </div>
  );
}

function ManualTab(props: { onAdd: (i: PinnedInput[]) => string | null }): React.JSX.Element {
  const [v, setV] = useState({ artist: '', title: '', bpm: '', key: '' });
  const [touched, setTouched] = useState({ artist: false, title: false, bpm: false, key: false });
  const [msg, setMsg] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const errors = {
    artist: v.artist.trim() ? null : 'Escribe el artista.',
    title: v.title.trim() ? null : 'Escribe el título.',
    bpm: Number(v.bpm.replace(',', '.')) >= 60 && Number(v.bpm.replace(',', '.')) <= 200 ? null : 'Escribe un BPM entre 60 y 200.',
    key: parseKey(v.key) ? null : 'Usa Camelot (8A), Open Key (1m) o notación (Am, F#m).',
  };
  // An empty form is not an error: messages appear once the person has typed something or tried to add.
  const dirty = Object.values(v).some((x) => x.trim() !== '');
  const show = (f: keyof typeof errors): string | null => (touched[f] && (dirty || attempted) ? errors[f] : null);
  const set = (f: keyof typeof v, val: string): void => { setV({ ...v, [f]: val }); setMsg(null); };
  const blur = (f: keyof typeof v): void => setTouched((t) => ({ ...t, [f]: true }));
  const submit = (): void => {
    setAttempted(true);
    setTouched({ artist: true, title: true, bpm: true, key: true });
    const first = (Object.keys(errors) as (keyof typeof errors)[]).find((f) => errors[f]);
    if (first) {
      document.getElementById(`pin-${first}`)?.focus();
      return;
    }
    const err = props.onAdd([{ artist: v.artist, title: v.title, bpm: Number(v.bpm.replace(',', '.')), key: v.key }]);
    setMsg(err);
    if (!err) {
      setV({ artist: '', title: '', bpm: '', key: '' });
      setTouched({ artist: false, title: false, bpm: false, key: false });
      setAttempted(false);
      document.getElementById('pin-artist')?.focus();
    }
  };
  return (
    <div className="stack" role="group" aria-label="Añadir un tema a mano" onKeyDown={enterSubmits(submit)}>
      <Field id="pin-artist" label="Artista" error={show('artist')}>
        {(a) => <input id={a.id} aria-invalid={a.invalid || undefined} aria-describedby={a.describedBy} value={v.artist} autoComplete="off" onChange={(e) => set('artist', e.target.value)} onBlur={() => blur('artist')} />}
      </Field>
      <Field id="pin-title" label="Título" error={show('title')}>
        {(a) => <input id={a.id} aria-invalid={a.invalid || undefined} aria-describedby={a.describedBy} value={v.title} autoComplete="off" onChange={(e) => set('title', e.target.value)} onBlur={() => blur('title')} />}
      </Field>
      <div className="two">
        <Field id="pin-bpm" label="BPM" error={show('bpm')}>
          {(a) => <input id={a.id} aria-invalid={a.invalid || undefined} aria-describedby={a.describedBy} inputMode="decimal" placeholder="124" value={v.bpm} onChange={(e) => set('bpm', e.target.value)} onBlur={() => blur('bpm')} />}
        </Field>
        <Field id="pin-key" label="Tonalidad" error={show('key')}>
          {(a) => <input id={a.id} aria-invalid={a.invalid || undefined} aria-describedby={a.describedBy} placeholder="8A, 1m, Am" autoCapitalize="off" value={v.key} onChange={(e) => set('key', e.target.value)} onBlur={() => blur('key')} />}
        </Field>
      </div>
      {msg && <p className="msg error" role="alert">{msg}</p>}
      <button type="button" className="btn" onClick={submit}>Fijar tema</button>
    </div>
  );
}

function PasteTab(props: { onAdd: (i: PinnedInput[]) => string | null }): React.JSX.Element {
  const [text, setText] = useState('');
  const [problems, setProblems] = useState<string[]>([]);
  const submit = (): void => {
    const rows = parsePinnedLines(text);
    if (!rows.length) {
      setProblems(['Pega al menos un tema, uno por línea.']);
      return;
    }
    const good = rows.flatMap((r) => (r.input ? [r.input] : []));
    const bad = rows.flatMap((r, i) => (r.error ? [`Línea ${i + 1}: ${r.error}`] : []));
    const err = good.length ? props.onAdd(good) : null;
    setProblems(err ? [...bad, err] : bad);
    if (!bad.length && !err) setText('');
  };
  return (
    <div className="stack" role="group" aria-label="Pegar una lista de temas">
      <Field id="pin-paste" label="Temas, uno por línea" hint="Formato: Artista - Título - BPM - tonalidad">
        {(a) => <textarea id={a.id} aria-describedby={a.describedBy} rows={4} value={text} spellCheck={false} onChange={(e) => { setText(e.target.value); setProblems([]); }} />}
      </Field>
      {problems.length > 0 && (
        <ul className="msg error plain" role="alert">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
      )}
      <button type="button" className="btn" onClick={submit}>Fijar temas</button>
    </div>
  );
}

/* ───────────────────────── Curva por tramos ───────────────────────── */

export function CurveEditor(props: {
  inputs: SegInput[];
  onChange: (i: SegInput[]) => void;
  onReset: () => void;
}): React.JSX.Element {
  const upd = (i: number, f: keyof SegInput, v: string): void => props.onChange(props.inputs.map((s, j) => (j === i ? { ...s, [f]: v } : s)));
  const F: { f: keyof SegInput; label: string }[] = [
    { f: 'weight', label: 'Peso (%)' }, { f: 'bpmStart', label: 'BPM inicio' }, { f: 'bpmEnd', label: 'BPM final' },
    { f: 'eMin', label: 'Energía mín.' }, { f: 'eMax', label: 'Energía máx.' },
  ];
  return (
    <div className="stack">
      {props.inputs.map((s, i) => (
        <fieldset key={i} className="seg-set">
          <legend>{s.name}</legend>
          <div className="grid5">
            {F.map(({ f, label }) => (
              <Field key={f} id={`seg-${i}-${f}`} label={label}>
                {(a) => <input id={a.id} inputMode="decimal" value={s[f]} onChange={(e) => upd(i, f, e.target.value)} />}
              </Field>
            ))}
          </div>
        </fieldset>
      ))}
      <button type="button" className="btn ghost start" onClick={props.onReset}>Restablecer curva</button>
    </div>
  );
}

/* ───────────────────────── Avanzado ───────────────────────── */

export function AdvancedPanel(props: {
  maxPerArtist: string;
  onMaxPerArtist: (v: string) => void;
  proxyUrl: string;
  onProxy: (v: string) => void;
  llm: LlmSettings;
  onLlm: (l: LlmSettings) => void;
  remember: boolean;
  onRemember: (b: boolean) => void;
}): React.JSX.Element {
  const l = props.llm;
  return (
    <div className="stack">
      <Field id="adv-max" label="Máximo de temas por artista" hint="Evita que un solo artista llene el set.">
        {(a) => <input id={a.id} aria-describedby={a.describedBy} inputMode="numeric" value={props.maxPerArtist} onChange={(e) => props.onMaxPerArtist(e.target.value)} />}
      </Field>
      <fieldset className="seg-set">
        <legend>Lista de Beatport (uso personal)</legend>
        <p className="msg hint">Un navegador no puede leer Beatport directamente. Necesitas tu propio proxy (ver README) y revisar los términos de uso de Beatport.</p>
        <Field id="adv-proxy" label="Dirección de tu proxy" hint="Por ejemplo https://beatport-proxy.tu-cuenta.workers.dev">
          {(a) => <input id={a.id} aria-describedby={a.describedBy} type="url" inputMode="url" autoCapitalize="off" value={props.proxyUrl} onChange={(e) => props.onProxy(e.target.value)} />}
        </Field>
        <Segmented
          legend="Modelo de respaldo" value={l.provider}
          onChange={(provider) => props.onLlm({ ...l, provider })}
          options={[{ value: 'none', label: 'Ninguno' }, { value: 'gemini', label: 'Gemini' }, { value: 'claude', label: 'Claude' }]}
        />
        {l.provider === 'gemini' && (
          <>
            <Field id="adv-gk" label="Clave de Gemini" hint="Se crea en aistudio.google.com">
              {(a) => <input id={a.id} aria-describedby={a.describedBy} type="password" autoComplete="off" value={l.geminiKey} onChange={(e) => props.onLlm({ ...l, geminiKey: e.target.value })} />}
            </Field>
            <Field id="adv-gm" label="Modelo de Gemini">
              {(a) => <input id={a.id} autoCapitalize="off" value={l.geminiModel} onChange={(e) => props.onLlm({ ...l, geminiModel: e.target.value })} />}
            </Field>
          </>
        )}
        {l.provider === 'claude' && (
          <>
            <Field id="adv-ck" label="Clave de la API de Claude" hint="Se crea en console.anthropic.com">
              {(a) => <input id={a.id} aria-describedby={a.describedBy} type="password" autoComplete="off" value={l.claudeKey} onChange={(e) => props.onLlm({ ...l, claudeKey: e.target.value })} />}
            </Field>
            <Field id="adv-cm" label="Modelo de Claude">
              {(a) => <input id={a.id} autoCapitalize="off" value={l.claudeModel} onChange={(e) => props.onLlm({ ...l, claudeModel: e.target.value })} />}
            </Field>
          </>
        )}
        {l.provider !== 'none' && (
          <label className="check">
            <input type="checkbox" checked={props.remember} onChange={(e) => props.onRemember(e.target.checked)} />
            <span>Recordar las claves en este navegador</span>
          </label>
        )}
        {l.provider !== 'none' && <p className="msg hint">Las claves se envían solo al proveedor que elijas. Si no marcas la casilla, se borran al cerrar la pestaña.</p>}
      </fieldset>
    </div>
  );
}

