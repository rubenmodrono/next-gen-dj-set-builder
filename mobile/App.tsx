import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Clipboard from 'expo-clipboard';
import * as SecureStore from 'expo-secure-store';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  Platform,
  useWindowDimensions,
  View,
} from 'react-native';
import { keyStandard, keyStr } from './src/core/camelot';
import { AVG_TRACK_MIN, formatLine, fmtBpm, orderTracks, preparePool, slotsFor, trackLabel } from './src/core/planner';
import type { DroppedTrack, PlannedTrack, Segment, Strictness } from './src/core/types';
import { chartUrl, defaultSegments, GENRES, type GenreInfo } from './src/data/genres';
import { loadChart, type ChartVia } from './src/sources/chart';
import { DEFAULT_LLM, type LlmSettings, type Provider } from './src/sources/llm';
import { resolvePreview, type Preview, type PreviewSource } from './src/sources/preview';
import { Curve } from './src/ui/Curve';
import { keyColor, Wheel } from './src/ui/Wheel';

/* ---------- Theme ---------- */
interface Theme {
  bg: string; panel: string; raised: string; ink: string; muted: string; rule: string; signal: string; onSignal: string; warn: string;
}
/** Visual direction "Rueda": midnight blue, Camelot hues as the only colour. */
const THEME: Theme = {
  bg: '#0E1226', panel: '#161B36', raised: '#222849', ink: '#EEF0FA', muted: '#9AA1C8', rule: '#2A3157', signal: '#7C8CFF', onSignal: '#0E1226', warn: '#F0A06A',
};
const MONO = Platform.select({ ios: 'Menlo', default: 'monospace' });

/* ---------- Types and constants ---------- */
interface SegInput { name: string; weight: string; bpmStart: string; bpmEnd: string; eMin: string; eMax: string }
interface Result {
  items: PlannedTrack[];
  dropped: DroppedTrack[];
  warnings: string[];
  via: ChartVia;
  fetchedAt: number;
  label: string;
  segments: Segment[];
}

const CUSTOM = 'custom';
const SETTINGS_KEY = 'set-planifier-settings-v1';
const HARM: { value: Strictness; label: string; hint: string }[] = [
  { value: 'strict', label: 'Estricta', hint: 'Solo misma tonalidad, un paso en la rueda Camelot o paso a la relativa (8A a 8B).' },
  { value: 'energy_boost', label: 'Con saltos', hint: 'Además permite subir +1 o +2 semitonos y bajar de energía (8A a 10A, 8A a 6A).' },
  { value: 'permissive', label: 'Libre', hint: 'Admite cualquier salto, con un coste mayor cuanto más choque.' },
];
const FLAG_LABEL: Record<string, string> = {
  boost1: 'Subida +1', boost2: 'Subida +2', drop: 'Bajada de energía', diagonal: 'Diagonal', clash: 'Choque armónico',
};
const PREVIEW_LABEL: Record<PreviewSource, string> = {
  beatport: 'Preview de Beatport',
  deezer: 'Preview de 30 s de Deezer',
  itunes: 'Preview de 30 s de Apple Music',
};
const VIA_LABEL: Record<ChartVia, string> = {
  direct: 'leída directamente de Beatport',
  cache: 'guardada en el teléfono',
  gemini: 'interpretada con Gemini',
  claude: 'interpretada con Claude',
};

const toInputs = (segs: Segment[]): SegInput[] =>
  segs.map((s) => ({ name: s.name, weight: String(s.weight), bpmStart: String(s.bpmStart), bpmEnd: String(s.bpmEnd), eMin: String(s.eMin), eMax: String(s.eMax) }));

const num = (s: string): number => Number(s.replace(',', '.'));
const toSegments = (inputs: SegInput[]): Segment[] =>
  inputs.map((s, i) => ({
    name: s.name.trim().slice(0, 24) || `Tramo ${i + 1}`,
    weight: num(s.weight), bpmStart: num(s.bpmStart), bpmEnd: num(s.bpmEnd), eMin: num(s.eMin), eMax: num(s.eMax),
  }));

function segmentError(segs: Segment[]): string | null {
  for (const s of segs) {
    if (!(s.weight > 0)) return `El tramo ${s.name} necesita un peso mayor que 0.`;
    if (![s.bpmStart, s.bpmEnd].every((b) => b >= 60 && b <= 200)) return `El BPM del tramo ${s.name} debe estar entre 60 y 200.`;
    if (!(s.eMin >= 0 && s.eMax <= 10 && s.eMin <= s.eMax)) return `La energía del tramo ${s.name} debe ir de 0 a 10, con el mínimo por debajo del máximo.`;
  }
  return null;
}

export default function App(): React.JSX.Element {
  const t = THEME;
  const s = useMemo(() => makeStyles(t), [t]);
  const { width: winW } = useWindowDimensions();
  const plotW = Math.min(winW, 720) - 32 - 16;

  const [genreId, setGenreId] = useState<string>('progressive-house');
  const [customUrl, setCustomUrl] = useState('');
  const [duration, setDuration] = useState('60');
  const [strictness, setStrictness] = useState<Strictness>('energy_boost');
  const [segIn, setSegIn] = useState<SegInput[]>(() => toInputs(defaultSegments(GENRES[0])));
  const [llm, setLlm] = useState<LlmSettings>(DEFAULT_LLM);
  const [showSettings, setShowSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [copied, setCopied] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  /* previews */
  const player = useAudioPlayer(null);
  const pstatus = useAudioPlayerStatus(player);
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [loadingIdx, setLoadingIdx] = useState<number | null>(null);
  const [noPreview, setNoPreview] = useState<Record<number, boolean>>({});
  const [previewSrc, setPreviewSrc] = useState<Record<number, PreviewSource>>({});
  const previewCache = useRef(new Map<string, Preview | null>());

  const genre: GenreInfo | undefined = GENRES.find((g) => g.id === genreId);
  const segments = useMemo(() => toSegments(segIn), [segIn]);
  const harmHint = HARM.find((h) => h.value === strictness)?.hint ?? '';
  const slots = slotsFor(Number(duration));

  useEffect(() => {
    setAudioModeAsync({ playsInSilentMode: true }).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (pstatus.didJustFinish) setActiveIdx(null);
  }, [pstatus.didJustFinish]);

  const togglePreview = async (i: number): Promise<void> => {
    if (!result) return;
    if (activeIdx === i) {
      if (pstatus.playing) player.pause();
      else player.play();
      return;
    }
    const track = result.items[i].track;
    const key = trackLabel(track);
    setLoadingIdx(i);
    let pv = previewCache.current.get(key);
    try {
      if (pv === undefined) {
        pv = await resolvePreview(track);
        previewCache.current.set(key, pv);
      }
    } catch {
      pv = null;
    }
    setLoadingIdx(null);
    if (!pv) {
      setNoPreview((m) => ({ ...m, [i]: true }));
      return;
    }
    player.pause();
    player.replace({ uri: pv.url });
    player.play();
    setPreviewSrc((m) => ({ ...m, [i]: pv.source }));
    setActiveIdx(i);
  };

  const listenLabel = (i: number): string => {
    if (noPreview[i]) return 'Sin preview disponible';
    if (loadingIdx === i) return 'Buscando preview…';
    if (activeIdx === i) return pstatus.playing ? 'Pausar' : 'Seguir';
    return 'Escuchar';
  };

  const avgCost = result
    ? (() => {
        const c = result.items.filter((it) => it.transition).map((it) => it.transition![1]);
        return c.length ? c.reduce((a, b) => a + b, 0) / c.length : 0;
      })()
    : 0;

  /* settings persistence */
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(SETTINGS_KEY);
        const saved = raw ? (JSON.parse(raw) as Partial<LlmSettings>) : {};
        const geminiKey = (await SecureStore.getItemAsync('gemini-key')) ?? '';
        const claudeKey = (await SecureStore.getItemAsync('claude-key')) ?? '';
        setLlm({ ...DEFAULT_LLM, ...saved, geminiKey, claudeKey });
      } catch {
        /* defaults */
      }
    })();
  }, []);

  const saveLlm = useCallback(async (next: LlmSettings) => {
    setLlm(next);
    try {
      const { geminiKey, claudeKey, ...rest } = next;
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(rest));
      await SecureStore.setItemAsync('gemini-key', geminiKey);
      await SecureStore.setItemAsync('claude-key', claudeKey);
    } catch {
      /* best effort */
    }
  }, []);

  const pickGenre = (id: string): void => {
    setGenreId(id);
    const g = GENRES.find((x) => x.id === id);
    if (g) setSegIn(toInputs(defaultSegments(g)));
  };

  const setSeg = (i: number, key: keyof SegInput, value: string): void =>
    setSegIn((prev) => prev.map((row, idx) => (idx === i ? { ...row, [key]: value } : row)));

  const run = async (refresh: boolean): Promise<void> => {
    setError('');
    setCopied('');
    const dur = Number(duration);
    if (!(dur >= 20 && dur <= 240)) return setError('La duración debe estar entre 20 y 240 minutos.');
    const segErr = segmentError(segments);
    if (segErr) return setError(segErr);
    let url: string;
    if (genre) url = chartUrl(genre);
    else {
      const u = customUrl.trim();
      if (!/^https:\/\/www\.beatport\.com\/.+/i.test(u)) return setError('Pega la dirección de una lista de beatport.com, por ejemplo https://www.beatport.com/genre/progressive-house/15/top-100');
      url = u;
    }
    const bpms = segments.flatMap((x) => [x.bpmStart, x.bpmEnd]);
    const bpmMin = genre ? genre.bpmMin : Math.min(...bpms) - 10;
    const bpmMax = genre ? genre.bpmMax : Math.max(...bpms) + 10;

    player.pause();
    setActiveIdx(null);
    setNoPreview({});
    previewCache.current.clear();
    abortRef.current = new AbortController();
    setBusy(true);
    setStatus('Leyendo la lista de Beatport…');
    try {
      const chart = await loadChart(url, llm, { signal: abortRef.current.signal, refresh, onStatus: setStatus });
      const { pool, dropped } = preparePool(chart.tracks, { segments, bpmMin, bpmMax });
      if (pool.length < 3) throw new Error(`Solo ${pool.length} temas de la lista son utilizables. Revisa el rango de BPM de la curva.`);
      const n = Math.min(slotsFor(dur), pool.length);
      const items = orderTracks(pool, segments, strictness, n);
      const warnings: string[] = [];
      if (n < slotsFor(dur)) warnings.push(`La lista solo tiene ${pool.length} temas utilizables para ${slotsFor(dur)} huecos. El set queda en ${n} temas.`);
      setResult({ items, dropped, warnings, via: chart.via, fetchedAt: chart.fetchedAt, label: genre ? genre.label : 'Lista personalizada', segments });
      setStatus('');
    } catch (e) {
      const err = e as { name?: string; message?: string };
      if (err.name === 'AbortError') setStatus('Cancelado.');
      else {
        setStatus('');
        setError(err.message ?? 'No se pudo crear el set.');
      }
    } finally {
      setBusy(false);
    }
  };

  const text = result ? result.items.map((it) => formatLine(it.track)).join('\n') : '';
  const copy = async (): Promise<void> => {
    try {
      await Clipboard.setStringAsync(text);
      setCopied('Lista copiada.');
    } catch {
      setCopied('No se pudo copiar. Usa Compartir.');
    }
  };
  const share = async (): Promise<void> => {
    try {
      await Share.share({ message: text });
    } catch {
      setCopied('No se pudo abrir Compartir.');
    }
  };

  const ageH = result ? Math.max(0, Math.round((Date.now() - result.fetchedAt) / 3600000)) : 0;

  return (
    <View style={s.root}>
      <StatusBar style="light" />
      <ScrollView contentInsetAdjustmentBehavior="automatic" keyboardShouldPersistTaps="handled" contentContainerStyle={s.scroll}>
        <View style={s.wrap}>
          <View style={{ gap: 8 }}>
            <View style={s.brand}>
              <View style={s.brandDot} />
              <Text style={s.h1} accessibilityRole="header">Set Planifier</Text>
            </View>
            <Text style={s.thesis}>Un set no es una lista de buenos temas: es una curva.</Text>
          </View>

          <View style={s.plot}>
            <Curve segments={segments} items={result?.items ?? []} width={plotW} colors={t} />
            <Text style={s.caption}>
              {result
                ? 'Línea: BPM objetivo. Banda: energía objetivo. Puntos: tus temas, con el color de su tonalidad Camelot.'
                : 'La línea es el BPM objetivo y la banda es la energía objetivo de cada tramo. Cambia los tramos y la curva se actualiza.'}
            </Text>
          </View>

          <View style={s.group}>
            <Text style={s.h2} accessibilityRole="header">Parámetros</Text>
            <Text style={s.label}>Género (lista de Beatport)</Text>
            <View style={s.chips}>
              {GENRES.map((g) => (
                <Pressable key={g.id} accessibilityRole="button" accessibilityState={{ selected: genreId === g.id }} onPress={() => pickGenre(g.id)} style={[s.chip, genreId === g.id && s.chipOn]}>
                  <Text style={[s.chipText, genreId === g.id && s.chipTextOn]}>{g.label}</Text>
                </Pressable>
              ))}
              <Pressable accessibilityRole="button" accessibilityState={{ selected: genreId === CUSTOM }} onPress={() => setGenreId(CUSTOM)} style={[s.chip, genreId === CUSTOM && s.chipOn]}>
                <Text style={[s.chipText, genreId === CUSTOM && s.chipTextOn]}>Otra lista</Text>
              </Pressable>
            </View>
            {genreId === CUSTOM && (
              <View style={s.field}>
                <Text style={s.label}>Dirección de la lista en beatport.com</Text>
                <TextInput style={s.input} value={customUrl} onChangeText={setCustomUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="https://www.beatport.com/genre/…/top-100" placeholderTextColor={t.muted} />
              </View>
            )}
            {genre && <Text style={s.hint}>Cambiar de género restaura la curva por defecto de ese género.</Text>}

            <View style={s.field}>
              <Text style={s.label}>Duración (min)</Text>
              <TextInput style={[s.input, { maxWidth: 140 }]} value={duration} onChangeText={setDuration} keyboardType="number-pad" maxLength={3} />
              <Text style={s.hint}>Unos {slots} temas, a {String(AVG_TRACK_MIN).replace('.', ',')} min de media por tema.</Text>
            </View>
          </View>

          <View style={s.group}>
            <Text style={s.label}>Armonía</Text>
            <View style={s.seg}>
              {HARM.map((h, i) => (
                <Pressable key={h.value} accessibilityRole="button" accessibilityState={{ selected: strictness === h.value }} onPress={() => setStrictness(h.value)} style={[s.segBtn, i > 0 && s.segSep, strictness === h.value && s.segOn]}>
                  <Text style={[s.segText, strictness === h.value && s.segTextOn]}>{h.label}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={s.hint}>{harmHint}</Text>
          </View>

          <View style={s.group}>
            <Text style={s.label}>Curva por tramos</Text>
            {segIn.map((row, i) => (
              <View key={i} style={s.tramo}>
                <Text style={s.hint}>Tramo {i + 1}</Text>
                <TextInput style={[s.input, { fontWeight: '700' }]} value={row.name} onChangeText={(v) => setSeg(i, 'name', v)} maxLength={24} accessibilityLabel={`Nombre del tramo ${i + 1}`} />
                <View style={s.nums}>
                  {([['weight', 'Peso %'], ['bpmStart', 'BPM ini'], ['bpmEnd', 'BPM fin'], ['eMin', 'Energ. mín'], ['eMax', 'Energ. máx']] as [keyof SegInput, string][]).map(([k, lab]) => (
                    <View key={k} style={s.numCell}>
                      <Text style={s.tiny} numberOfLines={1}>{lab}</Text>
                      <TextInput style={[s.input, s.numInput]} value={row[k]} onChangeText={(v) => setSeg(i, k, v)} keyboardType="decimal-pad" maxLength={5} accessibilityLabel={`${lab}, tramo ${i + 1}`} />
                    </View>
                  ))}
                </View>
              </View>
            ))}
            {genre && (
              <Pressable accessibilityRole="button" onPress={() => setSegIn(toInputs(defaultSegments(genre)))} style={s.linkBtn}>
                <Text style={s.link}>Restaurar curva por defecto</Text>
              </Pressable>
            )}
          </View>

          <View style={s.group}>
            <View style={s.actions}>
              <Pressable accessibilityRole="button" disabled={busy} onPress={() => run(false)} style={[s.primary, busy && { opacity: 0.45 }]}>
                <Text style={s.primaryText}>Crear set</Text>
              </Pressable>
              {busy && (
                <Pressable accessibilityRole="button" onPress={() => abortRef.current?.abort()} style={s.secondary}>
                  <Text style={s.secondaryText}>Cancelar</Text>
                </Pressable>
              )}
            </View>
            {busy && <ActivityIndicator color={t.signal} style={{ alignSelf: 'flex-start' }} />}
            {!!status && <Text style={s.status} accessibilityLiveRegion="polite">{status}</Text>}
            {!!error && <Text style={[s.status, { color: t.warn, fontWeight: '600' }]} accessibilityLiveRegion="polite">{error}</Text>}
          </View>

          <View style={s.group}>
            <Pressable accessibilityRole="button" onPress={() => setShowSettings((v) => !v)} style={s.linkBtn}>
              <Text style={s.link}>{showSettings ? 'Ocultar ajustes' : 'Ajustes (opcional)'}</Text>
            </Pressable>
            {showSettings && (
              <View style={s.group}>
                <Text style={s.hint}>
                  La app lee la lista de Beatport sin ninguna clave. Si Beatport cambia su página y deja de leerse, un modelo puede interpretarla. Gemini tiene capa gratuita.
                </Text>
                <Text style={s.label}>Modelo de respaldo</Text>
                <View style={s.seg}>
                  {([['none', 'Ninguno'], ['gemini', 'Gemini'], ['claude', 'Claude']] as [Provider, string][]).map(([v, lab], i) => (
                    <Pressable key={v} accessibilityRole="button" accessibilityState={{ selected: llm.provider === v }} onPress={() => saveLlm({ ...llm, provider: v })} style={[s.segBtn, i > 0 && s.segSep, llm.provider === v && s.segOn]}>
                      <Text style={[s.segText, llm.provider === v && s.segTextOn]}>{lab}</Text>
                    </Pressable>
                  ))}
                </View>
                {llm.provider === 'gemini' && (
                  <>
                    <Text style={s.label}>Clave de Gemini (aistudio.google.com)</Text>
                    <TextInput style={s.input} value={llm.geminiKey} onChangeText={(v) => saveLlm({ ...llm, geminiKey: v.trim() })} secureTextEntry autoCapitalize="none" autoCorrect={false} />
                    <Text style={s.label}>Modelo</Text>
                    <TextInput style={s.input} value={llm.geminiModel} onChangeText={(v) => saveLlm({ ...llm, geminiModel: v.trim() })} autoCapitalize="none" autoCorrect={false} />
                  </>
                )}
                {llm.provider === 'claude' && (
                  <>
                    <Text style={s.label}>Clave de la API de Claude (console.anthropic.com)</Text>
                    <TextInput style={s.input} value={llm.claudeKey} onChangeText={(v) => saveLlm({ ...llm, claudeKey: v.trim() })} secureTextEntry autoCapitalize="none" autoCorrect={false} />
                    <Text style={s.label}>Modelo</Text>
                    <TextInput style={s.input} value={llm.claudeModel} onChangeText={(v) => saveLlm({ ...llm, claudeModel: v.trim() })} autoCapitalize="none" autoCorrect={false} />
                  </>
                )}
              </View>
            )}
          </View>

          {result && (
            <View style={s.group}>
              <Text style={s.h2} accessibilityRole="header">Tu set</Text>
              <Text style={s.hint}>
                {result.items.length} temas, unos {Math.round(result.items.length * AVG_TRACK_MIN)} minutos. {result.label}, lista {VIA_LABEL[result.via]}{result.via === 'cache' || ageH > 0 ? ` (hace ${ageH} h)` : ''}.
              </Text>
              <Text style={s.hint}>BPM y tonalidad vienen de Beatport. La energía se estima a partir del BPM dentro de tu curva, porque Beatport no la publica.</Text>
              {result.warnings.map((w) => <Text key={w} style={[s.hint, { color: t.warn }]}>{w}</Text>)}

              <View style={s.wheelCard}>
                <Wheel items={result.items} size={146} colors={t} />
                <View style={s.wheelText}>
                  <Text style={s.kicker}>CAMINO ARMÓNICO</Text>
                  <Text style={s.wheelTitle}>{keyStr(result.items[0].track.key)} → {keyStr(result.items[result.items.length - 1].track.key)}</Text>
                  <Text style={s.hint}>Coste armónico medio {avgCost.toFixed(2).replace('.', ',')}. El color de cada tema es el de su tonalidad en la rueda.</Text>
                </View>
              </View>

              <View style={s.tracks}>
                {result.items.map((it, i) => {
                  const flag = it.transition && FLAG_LABEL[it.transition[0]];
                  return (
                    <View key={`${i}-${trackLabel(it.track)}`} style={s.track}>
                      <View style={[s.bar, { backgroundColor: keyColor(it.track.key) }]} />
                      <View style={s.main}>
                        <Text style={s.title} numberOfLines={2}>{it.track.title}{it.track.mix ? ` (${it.track.mix})` : ''}</Text>
                        <Text style={s.artist} numberOfLines={1}>{it.track.artist}</Text>
                        {!!flag && <Text style={[s.flag, it.transition![1] >= 5 && { color: t.warn }]}>{flag}</Text>}
                        {activeIdx === i && (
                          <View style={{ gap: 4, marginTop: 6 }}>
                            <View style={s.progress}>
                              <View style={[s.progressFill, { width: `${pstatus.duration > 0 ? Math.min(100, (pstatus.currentTime / pstatus.duration) * 100) : 0}%` }]} />
                            </View>
                            {previewSrc[i] && <Text style={s.flag}>{PREVIEW_LABEL[previewSrc[i]]}</Text>}
                          </View>
                        )}
                        {noPreview[i] && <Text style={s.flag}>Sin preview disponible</Text>}
                      </View>
                      <View
                        style={s.meta}
                        accessible
                        accessibilityLabel={`${fmtBpm(it.track.bpm)} BPM, tonalidad ${keyStr(it.track.key)}, ${keyStandard(it.track.key)}`}
                      >
                        <Text style={s.bpm}>{fmtBpm(it.track.bpm)}</Text>
                        <Text style={[s.keyText, { color: keyColor(it.track.key) }]}>{keyStr(it.track.key)} · {keyStandard(it.track.key)}</Text>
                      </View>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`${listenLabel(i)}: ${trackLabel(it.track)}`}
                        disabled={noPreview[i] || loadingIdx === i}
                        onPress={() => togglePreview(i)}
                        style={[s.play, noPreview[i] && { opacity: 0.4 }]}
                      >
                        {loadingIdx === i ? (
                          <ActivityIndicator color={t.ink} />
                        ) : (
                          <Text style={s.playGlyph}>{activeIdx === i && pstatus.playing ? '❚❚' : '▶'}</Text>
                        )}
                      </Pressable>
                    </View>
                  );
                })}
              </View>

              <View style={s.actions}>
                <Pressable accessibilityRole="button" onPress={copy} style={s.primary}><Text style={s.primaryText}>Copiar lista</Text></Pressable>
                <Pressable accessibilityRole="button" onPress={share} style={s.secondary}><Text style={s.secondaryText}>Compartir</Text></Pressable>
                <Pressable accessibilityRole="button" disabled={busy} onPress={() => run(true)} style={s.secondary}><Text style={s.secondaryText}>Actualizar lista</Text></Pressable>
              </View>
              {!!copied && <Text style={s.status} accessibilityLiveRegion="polite">{copied}</Text>}

              {result.dropped.length > 0 && (
                <View style={s.group}>
                  <Text style={s.label}>{result.dropped.length} temas de la lista descartados</Text>
                  {result.dropped.map((d, i) => <Text key={i} style={s.hint}>{d.label}: {d.reason}</Text>)}
                </View>
              )}
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: t.bg },
    scroll: { paddingHorizontal: 16, paddingTop: 28, paddingBottom: 64 },
    wrap: { width: '100%', maxWidth: 720, alignSelf: 'center', gap: 28 },
    brand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
    brandDot: { width: 12, height: 12, borderRadius: 4, backgroundColor: t.signal },
    h1: { fontSize: 30, lineHeight: 34, fontWeight: '700', letterSpacing: -0.5, color: t.ink },
    thesis: { fontSize: 16, lineHeight: 22, color: t.muted, maxWidth: 340 },
    h2: { fontSize: 24, fontWeight: '700', letterSpacing: -0.4, color: t.ink },
    kicker: { fontFamily: MONO, fontSize: 11, letterSpacing: 0.8, color: t.muted },
    plot: { backgroundColor: t.panel, borderRadius: 14, padding: 10, gap: 8 },
    caption: { fontSize: 13, lineHeight: 18, color: t.muted, paddingHorizontal: 4, paddingBottom: 4 },
    group: { gap: 12 },
    field: { gap: 4 },
    label: { fontSize: 14, fontWeight: '600', color: t.ink },
    hint: { fontSize: 13, lineHeight: 18, color: t.muted },
    tiny: { fontSize: 12, color: t.muted },
    input: { minHeight: 44, paddingHorizontal: 12, borderWidth: 1, borderColor: t.rule, borderRadius: 10, backgroundColor: t.panel, color: t.ink, fontSize: 16 },
    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    chip: { minHeight: 44, paddingHorizontal: 16, justifyContent: 'center', borderWidth: 1, borderColor: t.rule, borderRadius: 22, backgroundColor: t.panel },
    chipOn: { backgroundColor: t.signal, borderColor: t.signal },
    chipText: { fontSize: 15, fontWeight: '600', color: t.ink },
    chipTextOn: { color: t.onSignal },
    seg: { flexDirection: 'row', borderWidth: 1, borderColor: t.rule, borderRadius: 12, overflow: 'hidden', backgroundColor: t.panel },
    segBtn: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
    segSep: { borderLeftWidth: 1, borderLeftColor: t.rule },
    segOn: { backgroundColor: t.signal },
    segText: { fontSize: 15, fontWeight: '600', color: t.ink },
    segTextOn: { color: t.onSignal },
    tramo: { gap: 8, padding: 12, borderRadius: 14, backgroundColor: t.panel },
    nums: { flexDirection: 'row', gap: 6 },
    numCell: { flex: 1, minWidth: 0, gap: 4 },
    numInput: { paddingHorizontal: 6, textAlign: 'center', backgroundColor: t.bg, fontFamily: MONO },
    linkBtn: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
    link: { fontSize: 14, fontWeight: '600', color: t.signal },
    actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, alignItems: 'center' },
    primary: { minHeight: 52, paddingHorizontal: 28, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: t.signal },
    primaryText: { fontSize: 17, fontWeight: '700', color: t.onSignal },
    secondary: { minHeight: 44, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center', borderRadius: 12, borderWidth: 1, borderColor: t.rule, backgroundColor: t.panel },
    secondaryText: { fontSize: 15, fontWeight: '600', color: t.ink },
    status: { fontSize: 14, color: t.muted },
    wheelCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: 14, backgroundColor: t.panel },
    wheelText: { flex: 1, minWidth: 0, gap: 6 },
    wheelTitle: { fontSize: 22, fontWeight: '700', letterSpacing: -0.3, color: t.ink },
    tracks: { gap: 8 },
    track: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 64, paddingRight: 8, borderRadius: 12, backgroundColor: t.panel, overflow: 'hidden' },
    bar: { width: 5, alignSelf: 'stretch' },
    main: { flex: 1, minWidth: 0, paddingVertical: 10, gap: 1 },
    title: { fontSize: 15, fontWeight: '600', color: t.ink },
    artist: { fontSize: 13, color: t.muted },
    flag: { marginTop: 2, fontSize: 12, fontWeight: '600', color: t.muted },
    meta: { alignItems: 'flex-end', gap: 2 },
    bpm: { fontFamily: MONO, fontSize: 17, fontWeight: '700', color: t.ink },
    keyText: { fontFamily: MONO, fontSize: 12, fontWeight: '700' },
    play: { width: 44, height: 44, borderRadius: 22, backgroundColor: t.raised, alignItems: 'center', justifyContent: 'center' },
    playGlyph: { fontSize: 14, color: t.ink },
    progress: { height: 3, backgroundColor: t.rule, borderRadius: 2, overflow: 'hidden' },
    progressFill: { height: 3, backgroundColor: t.signal },
  });
}
