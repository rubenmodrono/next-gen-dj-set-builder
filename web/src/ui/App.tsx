import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { parseKey } from '../core/camelot';
import { planSet, shortlist, toPinnedTrack, type PinnedInput } from '../core/pinned';
import { preparePool, slotsFor, songKeyOf } from '../core/planner';
import type { RawTrack, Strictness } from '../core/types';
import { defaultSegments, chartUrl, GENRES } from '../data/genres';
import { demoLibrary } from '../library/demo';
import { decodeText, parseLibraryText } from '../library/parse';
import { clearLibrary, loadLibrary, saveLibrary, type StoredLibrary } from '../library/store';
import { probeBuiltinProxy } from '../sources/beatport';
import { loadChart } from '../sources/chart';
import { DEFAULT_LLM, type LlmSettings } from '../sources/llm';
import { genreForLibrary, HARM, libraryGenres, read, segmentError, toInputs, toSegments, write, type SegInput } from '../state';
import { AdvancedPanel, CurveEditor, LibraryPanel, PinnedPanel, type PinnedItem } from './panels';
import { ResultView, resultCsv, resultText, type Result } from './ResultView';
import { ErrorBox, Field, Fold, Icon, Segmented } from './ui';
import { usePreview } from './usePreview';

type StyleId = 'console' | 'editorial' | 'wheel';
type Mode = 'light' | 'dark';
type Source = 'library' | 'beatport';

const STYLES = [
  { value: 'wheel', label: 'Rueda' },
  { value: 'console', label: 'Consola' },
  { value: 'editorial', label: 'Editorial' },
] as const;

const LLM_KEY = 'sp-llm';
const NO_TRACKS: RawTrack[] = [];
const hasWindow = typeof document !== 'undefined';

function loadLlm(): { llm: LlmSettings; remember: boolean } {
  for (const [store, remember] of [[localStorage, true], [sessionStorage, false]] as const) {
    try {
      const raw = store.getItem(LLM_KEY);
      if (raw) return { llm: { ...DEFAULT_LLM, ...(JSON.parse(raw) as Partial<LlmSettings>) }, remember };
    } catch { /* storage unavailable */ }
  }
  return { llm: DEFAULT_LLM, remember: false };
}

export default function App(): React.JSX.Element {
  /* ── apariencia ── */
  const [style, setStyle] = useState<StyleId>(() => (hasWindow ? (document.documentElement.dataset.style as StyleId) : 'wheel') || 'wheel');
  const [mode, setMode] = useState<Mode>(() => (hasWindow ? (document.documentElement.dataset.mode as Mode) : 'dark') || 'dark');
  useEffect(() => {
    document.documentElement.dataset.style = style;
    document.documentElement.dataset.mode = mode;
    write('sp-style', style);
    write('sp-mode', mode);
  }, [style, mode]);

  /* ── parámetros ── */
  const [source, setSource] = useState<Source>(() => (read('sp-source') === 'beatport' ? 'beatport' : 'library'));
  const [library, setLibrary] = useState<StoredLibrary | null>(null);
  const [libBusy, setLibBusy] = useState(false);
  const [libError, setLibError] = useState<string | null>(null);
  const [libGenre, setLibGenre] = useState('all');
  const [genreId, setGenreId] = useState(read('sp-genre') ?? 'progressive-house');
  const [duration, setDuration] = useState(read('sp-duration') ?? '60');
  const [durTouched, setDurTouched] = useState(false);
  const [strictness, setStrictness] = useState<Strictness>((read('sp-harm') as Strictness | null) ?? 'energy_boost');
  const [segIn, setSegIn] = useState<SegInput[]>(() => toInputs(defaultSegments(GENRES[0])));
  const [pinned, setPinned] = useState<PinnedItem[]>([]);
  const [maxPerArtist, setMaxPerArtist] = useState('2');
  const [proxyUrl, setProxyUrl] = useState(read('sp-proxy') ?? '');
  const [builtinProxy, setBuiltinProxy] = useState(false);
  const initial = useMemo(loadLlm, []);
  const [llm, setLlm] = useState<LlmSettings>(initial.llm);
  const [remember, setRemember] = useState(initial.remember);

  /* ── resultado ── */
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState<{ message: string; details?: string } | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [copied, setCopied] = useState('');
  const resultRef = useRef<HTMLElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const preview = usePreview();

  /* ── biblioteca guardada ── */
  useEffect(() => { void loadLibrary().then((l) => { if (l) setLibrary(l); }); }, []);

  const libTracks = library?.tracks ?? NO_TRACKS;
  const usable = useMemo(() => libTracks.filter((t) => t.bpm && parseKey(t.key)).length, [libTracks]);
  const genres = useMemo(() => libraryGenres(libTracks), [libTracks]);
  useEffect(() => { if (libGenre !== 'all' && !genres.some((g) => g.name === libGenre)) setLibGenre('all'); }, [genres, libGenre]);

  const genre = useMemo(
    () => (source === 'library' ? genreForLibrary(libGenre, libGenre === 'all' ? libTracks : libTracks.filter((t) => t.genre === libGenre)) : (GENRES.find((g) => g.id === genreId) ?? GENRES[0])),
    [source, libGenre, libTracks, genreId],
  );
  // Each genre (or library selection) has its own default curve.
  useEffect(() => { setSegIn(toInputs(defaultSegments(genre))); }, [genre]);

  const segments = useMemo(() => toSegments(segIn), [segIn]);
  const slots = slotsFor(Number(duration));
  const durNum = Number(duration.replace(',', '.'));
  const durError = durNum >= 10 && durNum <= 360 ? null : 'Escribe una duración entre 10 y 360 minutos.';
  const harmHint = HARM.find((h) => h.value === strictness)?.hint ?? '';

  useEffect(() => { write('sp-source', source); }, [source]);
  useEffect(() => { write('sp-genre', genreId); }, [genreId]);
  useEffect(() => { write('sp-duration', duration); }, [duration]);
  useEffect(() => { write('sp-harm', strictness); }, [strictness]);
  useEffect(() => { write('sp-proxy', proxyUrl); }, [proxyUrl]);
  useEffect(() => {
    const ctl = new AbortController();
    void probeBuiltinProxy(ctl.signal).then(setBuiltinProxy);
    return () => ctl.abort();
  }, []);
  useEffect(() => {
    const json = JSON.stringify(llm);
    try {
      (remember ? sessionStorage : localStorage).removeItem(LLM_KEY);
      (remember ? localStorage : sessionStorage).setItem(LLM_KEY, json);
    } catch { /* storage unavailable */ }
  }, [llm, remember]);

  /* ── biblioteca: importar ── */
  const importFile = useCallback(async (f: File) => {
    setLibBusy(true);
    setLibError(null);
    try {
      const text = decodeText(await f.arrayBuffer());
      await new Promise((r) => setTimeout(r, 0)); // let the "Leyendo…" state paint before the heavy parse
      const parsed = parseLibraryText(text);
      const lib: StoredLibrary = { name: f.name, format: parsed.format, importedAt: Date.now(), tracks: parsed.tracks, skipped: parsed.skipped };
      setLibrary(lib);
      setSource('library');
      setLibGenre('all');
      const saved = await saveLibrary(lib);
      if (!saved) setLibError('No pude guardar la biblioteca en este navegador. Funcionará hasta que cierres la pestaña.');
    } catch (e) {
      setLibError(`${(e as Error).message} Revisa el archivo e inténtalo de nuevo.`);
    } finally {
      setLibBusy(false);
    }
  }, []);

  const useDemo = useCallback(async () => {
    const lib: StoredLibrary = { name: 'Biblioteca de ejemplo', format: 'demo', importedAt: Date.now(), tracks: demoLibrary(), skipped: 0 };
    setLibrary(lib);
    setSource('library');
    setLibGenre('Progressive House');
    setLibError(null);
    await saveLibrary(lib);
  }, []);

  const removeLibrary = useCallback(async () => {
    setLibrary(null);
    setLibGenre('all');
    await clearLibrary();
  }, []);

  /* ── fijados ── */
  const addPinned = useCallback((inputs: PinnedInput[]): string | null => {
    let msg: string | null = null;
    setPinned((cur) => {
      const next = [...cur];
      for (const input of inputs) {
        const r = toPinnedTrack(input, segments);
        if (!r.ok) { msg = r.error; continue; }
        if (next.some((p) => songKeyOf(p.input.artist, p.input.title) === songKeyOf(input.artist, input.title))) { msg = 'Ese tema ya está fijado.'; continue; }
        if (next.length >= 20) { msg = 'Has llegado al máximo de 20 temas fijados.'; break; }
        next.push({ id: `${Date.now()}-${next.length}-${Math.random().toString(36).slice(2, 6)}`, input });
      }
      return next;
    });
    return msg;
  }, [segments]);

  /* ── generar ── */
  const run = useCallback(async () => {
    if (busy) return;
    setError(null);
    setDurTouched(true);
    if (durError) { document.getElementById('duration')?.focus(); return; }
    const sErr = segmentError(segments);
    if (sErr) { setError({ message: sErr.message }); document.getElementById(sErr.field)?.focus(); return; }
    const perArtist = Math.max(1, Math.min(10, Math.round(Number(maxPerArtist)) || 2));

    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    setBusy(true);
    setStatus('');
    preview.reset();
    try {
      let raw: RawTrack[];
      let via: Result['via'] = 'library';
      let fetchedAt = Date.now();
      let sourceNote: string;
      if (source === 'library') {
        if (!library) { setError({ message: 'Importa tu biblioteca, o usa la de ejemplo, para generar un set.' }); return; }
        raw = libGenre === 'all' ? library.tracks : library.tracks.filter((t) => t.genre === libGenre);
        if (!raw.length) { setError({ message: 'No hay temas de ese género en tu biblioteca. Elige otro género o «Todos los géneros».' }); return; }
        sourceNote = `Temas de tu biblioteca (${library.name}). Los previews se buscan en Deezer y Apple Music, y solo se reproducen si coinciden con el tema.`;
      } else {
        const g = GENRES.find((x) => x.id === genreId) ?? GENRES[0];
        const chart = await loadChart(chartUrl(g), proxyUrl, llm, { signal: ctl.signal, onStatus: setStatus });
        raw = chart.tracks;
        via = chart.via;
        fetchedAt = chart.fetchedAt;
        sourceNote = `Lista Top 100 de Beatport (${g.label}). Los previews vienen de Beatport cuando están disponibles.`;
      }
      setStatus('Ordenando los temas…');
      const { pool, dropped } = preparePool(raw, { segments, bpmMin: genre.bpmMin, bpmMax: genre.bpmMax, maxPerArtist: perArtist });

      const pins: ReturnType<typeof toPinnedTrack>[] = pinned.map((p) => toPinnedTrack(p.input, segments));
      const pinnedTracks = pins.flatMap((p) => (p.ok ? [p.track] : []));
      const warnings = pins.flatMap((p) => (p.ok && p.warning ? [p.warning] : []));
      if (!pool.length && !pinnedTracks.length) {
        setError({ message: `Ningún tema tiene BPM y tonalidad dentro de ${genre.bpmMin}–${genre.bpmMax} BPM. Cambia el género o amplía la curva.` });
        return;
      }
      const planned = planSet(shortlist(pool, segments, slots), pinnedTracks, segments, strictness, slots);
      if (planned.extended) warnings.push(`Has fijado más temas (${pinnedTracks.length}) que huecos tiene el set (${slots}). El set pasa a ${planned.slots} temas.`);
      else if (planned.slots < slots) warnings.push(`Solo hay ${planned.slots} temas útiles para ${slots} huecos. Prueba con otro género, más biblioteca o menos duración.`);
      if (dropped.length) warnings.push(`${dropped.length} temas se han descartado por falta de datos o por salirse del rango de BPM.`);

      const next: Result = {
        items: planned.items, dropped, warnings, segments, pinnedSlots: planned.pinnedSlots,
        title: `${genre.label} · ${Math.round(durNum)} min`, sourceNote, via, fetchedAt,
      };
      setResult(next);
      requestAnimationFrame(() => {
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (window.matchMedia('(max-width: 767px)').matches) resultRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
        resultRef.current?.focus({ preventScroll: true });
      });
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') return;
      setError({ message: `No pude generar el set. ${(e as Error).message}`, details: String((e as Error).stack ?? e) });
    } finally {
      setBusy(false);
      setStatus('');
    }
  }, [busy, durError, segments, maxPerArtist, source, library, libGenre, genreId, proxyUrl, llm, pinned, genre, slots, strictness, durNum, preview]);

  /* Ctrl/Cmd + Enter genera el set; Esc detiene el preview. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void run(); }
      else if (e.key === 'Escape') preview.stop();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [run, preview]);

  const copyText = useCallback(async (text: string, ok: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(ok); }
    catch { setCopied('No pude copiar. Selecciona el texto y cópialo a mano.'); }
    setTimeout(() => setCopied(''), 4000);
  }, []);

  const download = useCallback((kind: 'txt' | 'csv') => {
    if (!result) return;
    const body = kind === 'txt' ? resultText(result) : resultCsv(result);
    const blob = new Blob([body], { type: kind === 'txt' ? 'text/plain;charset=utf-8' : 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `set-planifier.${kind}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }, [result]);

  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  const genreOptions = [{ value: 'all', label: `Todos los géneros (${libTracks.length.toLocaleString('es-ES')})` }, ...genres.map((g) => ({ value: g.name, label: `${g.name} (${g.count})` }))];

  return (
    <div className="app">
      <a className="skip" href="#resultado">Saltar al resultado</a>
      <header className="topbar">
        <div className="topbar-in">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <div>
              <h1>Set Planifier</h1>
              <p className="tagline">Un set no es una lista de buenos temas: es una curva.</p>
            </div>
          </div>
          <div className="topbar-tools">
            <Segmented legend="Estilo" value={style} onChange={setStyle} options={STYLES} className="style-seg" />
            <div className="modesw">
              <span className="label" id="mode-lbl">Modo</span>
              <button
                type="button" role="switch" aria-checked={mode === 'dark'} aria-labelledby="mode-lbl" className="switch"
                onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')}
              >
                <span className="switch-knob" aria-hidden="true">{mode === 'dark' ? Icon.moon : Icon.sun}</span>
                <span className="sr-only">{mode === 'dark' ? 'Oscuro' : 'Claro'}</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="page">
        <section className="panel-left" aria-label="Parámetros del set">
          <form className="stack-lg" noValidate onSubmit={(e) => { e.preventDefault(); void run(); }}>
            <div className="block">
              <h2>Fuente de temas</h2>
              <Segmented
                legend="Fuente" hideLegend value={source} onChange={setSource}
                options={[{ value: 'library', label: 'Mi biblioteca' }, { value: 'beatport', label: 'Lista de Beatport' }]}
              />
              {source === 'library' ? (
                <>
                  <LibraryPanel library={library} usable={usable} busy={libBusy} error={libError} onFile={(f) => void importFile(f)} onDemo={() => void useDemo()} onClear={() => void removeLibrary()} />
                  {library && (
                    <Field id="lib-genre" label="Género">
                      {(a) => (
                        <select id={a.id} value={libGenre} onChange={(e) => setLibGenre(e.target.value)}>
                          {genreOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      )}
                    </Field>
                  )}
                </>
              ) : (
                <>
                  <Field id="bp-genre" label="Género (lista Top 100)" hint="Los temas, el BPM y la tonalidad salen de la lista de Beatport de ese género.">
                    {(a) => (
                      <select id={a.id} aria-describedby={a.describedBy} value={genreId} onChange={(e) => setGenreId(e.target.value)}>
                        {GENRES.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
                      </select>
                    )}
                  </Field>
                  {!proxyUrl.trim() && !builtinProxy && llm.provider === 'none' && (
                    <p className="msg warn">Esta web no incluye el lector de Beatport (solo en Cloudflare Pages). Configura tu propio proxy en «Avanzado» o usa tu biblioteca.</p>
                  )}
                </>
              )}
            </div>

            <div className="block">
              <h2>Set</h2>
              <Field id="duration" label="Duración (min)" hint={`Aproximadamente ${slots} temas.`} error={durTouched ? durError : null}>
                {(a) => (
                  <input
                    id={a.id} aria-describedby={a.describedBy} aria-invalid={a.invalid || undefined} className="narrow"
                    type="text" inputMode="numeric" maxLength={3} value={duration}
                    onChange={(e) => setDuration(e.target.value.replace(/[^\d]/g, ''))} onBlur={() => setDurTouched(true)}
                  />
                )}
              </Field>
              <div>
                <Segmented legend="Armonía" value={strictness} onChange={setStrictness} options={HARM.map((h) => ({ value: h.value, label: h.label }))} />
                <p className="msg hint">{harmHint}</p>
              </div>
            </div>

            <Fold title="Curva por tramos" defaultOpen>
              <CurveEditor inputs={segIn} onChange={setSegIn} onReset={() => setSegIn(toInputs(defaultSegments(genre)))} />
            </Fold>

            <Fold title={`Temas fijados${pinned.length ? ` (${pinned.length})` : ''}`}>
              <PinnedPanel
                library={library} pinned={pinned} segments={segments}
                onAdd={addPinned} onRemove={(id) => setPinned((c) => c.filter((p) => p.id !== id))}
              />
            </Fold>

            <Fold title="Avanzado">
              <AdvancedPanel
                maxPerArtist={maxPerArtist} onMaxPerArtist={setMaxPerArtist} proxyUrl={proxyUrl} onProxy={setProxyUrl} builtinProxy={builtinProxy}
                llm={llm} onLlm={setLlm} remember={remember} onRemember={setRemember}
              />
            </Fold>

            <div className="feedback">
              {status && <p className="msg hint" role="status" aria-live="polite">{status}</p>}
              {error && (
                <ErrorBox message={error.message} details={error.details} onRetry={() => void run()} onCopy={(t) => void copyText(t, 'Detalles copiados.')} />
              )}
            </div>
            <div className="actions">
              <button type="submit" className="btn primary wide" aria-busy={busy || undefined}>
                {busy ? <><span className="spinner" aria-hidden="true" />Generando…</> : 'Generar set'}
              </button>
              <p className="msg hint kbdhint">o pulsa <kbd>{isMac ? '⌘' : 'Ctrl'}</kbd> <kbd>Enter</kbd></p>
            </div>
          </form>
        </section>

        <section className="panel-right" id="resultado" ref={resultRef} tabIndex={-1} aria-label="Set generado">
          {result ? (
            <ResultView
              result={result} preview={preview} copied={copied}
              onCopy={() => void copyText(resultText(result), 'Lista copiada.')} onDownload={download}
            />
          ) : (
            <div className="empty card">
              <h2>Aún no hay un set</h2>
              <p className="muted">
                {source === 'library' && !library
                  ? 'Importa tu biblioteca y genera un set que siga tu curva de BPM y energía con mezcla armónica.'
                  : 'Genera un set que siga tu curva de BPM y energía, con mezcla armónica por la rueda Camelot.'}
              </p>
              <div className="row-actions">
                <button type="button" className="btn primary" onClick={() => void run()}>Generar set</button>
                {source === 'library' && !library && <button type="button" className="btn" onClick={() => void useDemo()}>Usar biblioteca de ejemplo</button>}
              </div>
            </div>
          )}
        </section>
      </main>
      <footer className="foot">
        <p>Set Planifier calcula en tu navegador. Los previews de 30 s se buscan en Deezer y Apple Music, y el audio pertenece a sus titulares.</p>
      </footer>
    </div>
  );
}
