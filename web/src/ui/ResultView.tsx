import { Fragment } from 'react';
import { keyStandard, keyStr } from '../core/camelot';
import { fmtBpm, formatLine, trackLabel } from '../core/planner';
import type { DroppedTrack, PlannedTrack, Segment } from '../core/types';
import type { ChartVia } from '../sources/chart';
import type { PreviewSource } from '../sources/preview';
import { TRANSITION_LABEL } from '../state';
import { Curve } from './Curve';
import { Icon, IconButton } from './ui';
import type { usePreview } from './usePreview';
import { keyFill, Wheel } from './Wheel';

export interface Result {
  items: PlannedTrack[];
  dropped: DroppedTrack[];
  warnings: string[];
  segments: Segment[];
  pinnedSlots: number[];
  title: string;
  sourceNote: string;
  via: ChartVia | 'library';
  fetchedAt: number;
}

const PREVIEW_LABEL: Record<PreviewSource, string> = {
  beatport: 'Preview de Beatport',
  deezer: 'Preview de 30 s de Deezer',
  itunes: 'Preview de 30 s de Apple Music',
};

const avg = (xs: number[]): number => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

export function resultText(r: Result): string {
  return r.items.map((it, i) => `${i + 1}. ${formatLine(it.track)}`).join('\n');
}

export function resultCsv(r: Result): string {
  const q = (s: string): string => `"${s.replace(/"/g, '""')}"`;
  const pin = new Set(r.pinnedSlots);
  const rows = r.items.map((it, i) =>
    [i + 1, q(it.track.artist), q(it.track.title), q(it.track.mix ?? ''), fmtBpm(it.track.bpm), keyStr(it.track.key), keyStandard(it.track.key), q(it.point.name), pin.has(i) ? 'si' : 'no'].join(','),
  );
  return ['posicion,artista,titulo,mezcla,bpm,camelot,tonalidad,tramo,fijado', ...rows].join('\n');
}

export function ResultView(props: {
  result: Result;
  preview: ReturnType<typeof usePreview>;
  copied: string;
  onCopy: () => void;
  onDownload: (kind: 'txt' | 'csv') => void;
}): React.JSX.Element {
  const { result: r, preview: pv } = props;
  const costs = r.items.slice(1).map((it) => it.transition?.[1] ?? 0);
  const pinned = new Set(r.pinnedSlots);
  const first = r.items[0].track.key;
  const last = r.items[r.items.length - 1].track.key;

  let prevSeg = -1;
  return (
    <div className="stack-lg">
      <header className="result-head">
        <div>
          <h2 className="h-result">{r.title}</h2>
          <p className="muted">{r.items.length} temas · {keyStr(first)} → {keyStr(last)} · coste armónico medio {avg(costs).toFixed(2).replace('.', ',')}</p>
        </div>
        <div className="row-actions">
          <button type="button" className="btn" onClick={props.onCopy}>Copiar lista</button>
          <button type="button" className="btn" onClick={() => props.onDownload('txt')}>Descargar TXT</button>
          <button type="button" className="btn" onClick={() => props.onDownload('csv')}>Descargar CSV</button>
        </div>
        <p className="msg hint" role="status" aria-live="polite">{props.copied}</p>
      </header>

      {r.warnings.length > 0 && (
        <ul className="notice" aria-label="Avisos">{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}

      <div className="charts">
        <section className="card" aria-labelledby="h-wheel">
          <h3 id="h-wheel" className="kicker">Camino armónico</h3>
          <Wheel items={r.items} size={232} />
        </section>
        <section className="card grow" aria-labelledby="h-curve">
          <h3 id="h-curve" className="kicker">Curva de BPM</h3>
          <Curve items={r.items} segments={r.segments} pinnedSlots={r.pinnedSlots} />
        </section>
      </div>

      <section aria-labelledby="h-list">
        <h3 id="h-list" className="kicker">Artista - Título - BPM - Tonalidad</h3>
        <ol className="tracklist">
          {r.items.map((it, i) => {
            const t = it.track;
            const head = it.point.seg !== prevSeg;
            prevSeg = it.point.seg;
            const active = pv.active === i;
            const playing = active && pv.state === 'playing';
            const loading = active && pv.state === 'loading';
            const trans = it.transition;
            return (
              <Fragment key={i}>
              {head && <li className="seghead">{it.point.name}</li>}
              <li className="trow" data-pinned={pinned.has(i) || undefined}>
                <div className="row" style={{ '--kc': keyFill(t.key) } as React.CSSProperties}>
                  <span className="bar" aria-hidden="true" />
                  <span className="idx mono" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
                  <div className="main">
                    <p className="title">{t.title}{t.mix ? <span className="mix"> ({t.mix})</span> : null}</p>
                    <p className="artist">{t.artist}</p>
                    <p className="sub">
                      {pinned.has(i) && <span className="pinmark">{Icon.pin}Fijado · </span>}
                      {trans ? (
                        <span className={trans[0] === 'clash' || trans[0] === 'drop' ? 'flag' : undefined}>{TRANSITION_LABEL[trans[0]]}</span>
                      ) : 'Apertura'}
                      {active && pv.state !== 'idle' && pv.source[i] ? ` · ${PREVIEW_LABEL[pv.source[i]]}` : ''}
                      {pv.none[i] ? ' · Sin preview disponible' : ''}
                    </p>
                    {active && pv.state !== 'idle' && (
                      <div className="prog" role="progressbar" aria-label="Progreso del preview" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pv.progress * 100)}>
                        <i style={{ width: `${pv.progress * 100}%` }} />
                      </div>
                    )}
                  </div>
                  <p className="bpm mono">{fmtBpm(t.bpm)}</p>
                  <p className="key mono"><span className="keyname">{keyStr(t.key)}</span><span className="keystd">{keyStandard(t.key)}</span></p>
                  <IconButton
                    className="playwrap" busy={loading}
                    label={`${playing ? 'Pausar' : 'Escuchar'} ${trackLabel(t)}`}
                    onClick={() => { void pv.toggle(i, t); }}
                  >
                    {loading ? <span className="spinner" aria-hidden="true" /> : playing ? Icon.pause : Icon.play}
                  </IconButton>
                </div>
              </li>
              </Fragment>
            );
          })}
        </ol>
        <p className="msg hint">{r.sourceNote}</p>
      </section>

      {r.dropped.length > 0 && (
        <details className="help">
          <summary>{r.dropped.length} temas de la fuente descartados</summary>
          <ul>{r.dropped.slice(0, 60).map((d, i) => <li key={i}>{d.label}: {d.reason}</li>)}</ul>
          {r.dropped.length > 60 && <p className="msg hint">Se muestran los 60 primeros.</p>}
        </details>
      )}
    </div>
  );
}
