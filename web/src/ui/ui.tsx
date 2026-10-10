import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

export const Icon = {
  play: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l13-7.5z" /></svg>
  ),
  pause: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></svg>
  ),
  close: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
  ),
  sun: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
  ),
  moon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>
  ),
  pin: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M14 3l7 7-2 1-3-1-4 4 1 5-2 1-3-5-5 2 8-8-1-3z" /></svg>
  ),
  search: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="M16 16l5 5" /></svg>
  ),
};

/** Square icon button with a real tooltip on hover and keyboard focus. The tooltip text is also the accessible name. */
export function IconButton(props: {
  label: string;
  shortcut?: string;
  onClick: () => void;
  children: ReactNode;
  busy?: boolean;
  pressed?: boolean;
  className?: string;
}): React.JSX.Element {
  const id = useId();
  return (
    <span className={`tipwrap ${props.className ?? ''}`}>
      <button type="button" className="iconbtn" aria-label={props.label} aria-describedby={id} aria-busy={props.busy || undefined} aria-pressed={props.pressed} onClick={props.onClick}>
        {props.children}
      </button>
      <span id={id} role="tooltip" className="tip">
        {props.label}
        {props.shortcut && <kbd>{props.shortcut}</kbd>}
      </span>
    </span>
  );
}

/** Single-choice group with roving focus: arrows move and select, Tab leaves the group. */
export function Segmented<T extends string>(props: {
  legend: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (v: T) => void;
  hideLegend?: boolean;
  className?: string;
}): React.JSX.Element {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const idx = Math.max(0, props.options.findIndex((o) => o.value === props.value));
  const onKey = (e: KeyboardEvent): void => {
    const n = props.options.length;
    let next = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % n;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + n) % n;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = n - 1;
    if (next >= 0) {
      e.preventDefault();
      props.onChange(props.options[next].value);
      refs.current[next]?.focus();
    }
  };
  return (
    <div className={`seggroup ${props.className ?? ''}`}>
      <span className={props.hideLegend ? 'sr-only' : 'label'} id={`${props.legend}-lg`}>{props.legend}</span>
      <div className="segmented" role="radiogroup" aria-label={props.legend} onKeyDown={onKey}>
        {props.options.map((o, i) => (
          <button
            key={o.value}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="radio"
            aria-checked={o.value === props.value}
            tabIndex={o.value === props.value ? 0 : -1}
            className="seg"
            onClick={() => props.onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Field(props: {
  id: string;
  label: string;
  hint?: string;
  error?: string | null;
  children: (a: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
  className?: string;
}): React.JSX.Element {
  const hintId = `${props.id}-hint`;
  const errId = `${props.id}-err`;
  const describedBy = [props.error ? errId : null, props.hint && !props.error ? hintId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`field ${props.className ?? ''}`}>
      <label htmlFor={props.id}>{props.label}</label>
      {props.children({ id: props.id, describedBy, invalid: !!props.error })}
      {props.error ? (
        <p id={errId} className="msg error" role="alert">{props.error}</p>
      ) : props.hint ? (
        <p id={hintId} className="msg hint">{props.hint}</p>
      ) : null}
    </div>
  );
}

/** Error with a recovery step and, for technical failures, a way to copy details for support. */
export function ErrorBox(props: { message: string; details?: string; onRetry?: () => void; onCopy?: (t: string) => void }): React.JSX.Element {
  return (
    <div className="errorbox" role="alert">
      <p>{props.message}</p>
      <div className="row-actions">
        {props.onRetry && <button type="button" className="btn" onClick={props.onRetry}>Intentar de nuevo</button>}
        {props.details && props.onCopy && (
          <button type="button" className="btn ghost" onClick={() => props.onCopy?.(props.details ?? '')}>Copiar detalles del error</button>
        )}
      </div>
    </div>
  );
}

/** Collapsible block whose open state lives in React, so re-renders never close it. */
export function Fold(props: { title: string; defaultOpen?: boolean; children: ReactNode }): React.JSX.Element {
  const [open, setOpen] = useState(!!props.defaultOpen);
  return (
    <details className="block fold" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary><h2>{props.title}</h2></summary>
      {props.children}
    </details>
  );
}
