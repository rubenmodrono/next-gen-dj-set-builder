import { useCallback, useEffect, useRef, useState } from 'react';
import type { Track } from '../core/types';
import { resolvePreview, type Preview, type PreviewSource } from '../sources/preview';

export type PreviewState = 'idle' | 'loading' | 'playing' | 'paused';

const cacheKey = (t: Track): string => `${t.artist}|${t.title}|${t.mix ?? ''}`;

/** One shared audio element: starting a track stops the previous one. */
export function usePreview() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const cache = useRef(new Map<string, Preview | null>());
  const abort = useRef<AbortController | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [state, setState] = useState<PreviewState>('idle');
  const [progress, setProgress] = useState(0);
  const [none, setNone] = useState<Record<number, boolean>>({});
  const [source, setSource] = useState<Record<number, PreviewSource>>({});

  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (audio.current) return audio.current;
    const a = new Audio();
    a.preload = 'none';
    a.addEventListener('timeupdate', () => setProgress(a.duration > 0 ? Math.min(1, a.currentTime / a.duration) : 0));
    a.addEventListener('ended', () => { setState('idle'); setProgress(0); setActive(null); });
    a.addEventListener('pause', () => setState((s) => (s === 'playing' ? 'paused' : s)));
    a.addEventListener('playing', () => setState('playing'));
    audio.current = a;
    return a;
  }, []);

  const stop = useCallback(() => {
    abort.current?.abort();
    audio.current?.pause();
    setState('idle');
    setProgress(0);
    setActive(null);
  }, []);

  const reset = useCallback(() => {
    stop();
    setNone({});
    setSource({});
  }, [stop]);

  const toggle = useCallback(async (idx: number, track: Track) => {
    const a = ensureAudio();
    if (active === idx && (state === 'playing' || state === 'loading')) {
      a.pause();
      abort.current?.abort();
      setState('paused');
      return;
    }
    if (active === idx && state === 'paused' && a.src) {
      void a.play().catch(() => setState('idle'));
      return;
    }
    abort.current?.abort();
    a.pause();
    setActive(idx);
    setState('loading');
    setProgress(0);
    const ctl = new AbortController();
    abort.current = ctl;
    try {
      const key = cacheKey(track);
      let p = cache.current.get(key);
      if (p === undefined) {
        p = await resolvePreview(track, ctl.signal);
        cache.current.set(key, p);
      }
      if (ctl.signal.aborted) return;
      if (!p) {
        setNone((m) => ({ ...m, [idx]: true }));
        setState('idle');
        setActive(null);
        return;
      }
      setSource((m) => ({ ...m, [idx]: p.source }));
      a.src = p.url;
      if (p.startMs > 0) a.addEventListener('loadedmetadata', () => { a.currentTime = p.startMs / 1000; }, { once: true });
      await a.play();
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') return;
      setNone((m) => ({ ...m, [idx]: true }));
      setState('idle');
      setActive(null);
    }
  }, [active, ensureAudio, state]);

  useEffect(() => () => { abort.current?.abort(); audio.current?.pause(); }, []);

  return { active, state, progress, none, source, toggle, stop, reset };
}
