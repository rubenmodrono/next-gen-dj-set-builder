"""
Interfaz web (Streamlit) del set builder.

Arranque:  python -m streamlit run app.py

Dos modos:
- Con colección (Rekordbox, Engine DJ, Traktor, VirtualDJ, CSV o la BD local de
  Rekordbox 6): elige temas reales siguiendo la curva y las reglas armónicas.
- Sin colección: genera una propuesta slot a slot (BPM, energía, clave Camelot)
  a partir solo de los parámetros.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, Sequence, cast

import altair as alt
import streamlit as st

from src.app.presenters import curve_frames, phase_label, set_table
from src.core.genres import DEFAULT_BPM_RANGE, genre_bpm_range, known_genres
from src.core.models import (
    EnergyCurveProfile,
    HarmonicStrictness,
    PhaseSpec,
    SetConstraint,
    UniversalTrack,
)
from src.core.timeline import ENERGY_PROFILES, estimate_track_count
from src.enrichment.common import SuggestionReport
from src.enrichment.lastfm import suggest_tracks_for_proposal_lastfm
from src.enrichment.llm_agent import DEFAULT_MODEL as DEFAULT_LLM_MODEL, suggest_tracks_for_proposal_llm
from src.enrichment.spotify import EnrichmentReport, enrich_with_spotify, suggest_tracks_for_proposal
from src.exporters import set_rows, to_csv, to_m3u8, to_rekordbox_xml
from src.graph.builder import SetGraph, build_set_graph
from src.graph.nodes import parse_collection_node
from src.graph.state import SetGraphState, initial_state
from src.parsers import SUPPORTED_EXTENSIONS, ParseResult, Rekordbox6DatabaseReader, parse_file

SourceMode = Literal["proposal", "upload", "rekordbox_db", "demo"]

SOURCE_OPTIONS: Final[dict[SourceMode, str]] = {
    "proposal": "Sin colección · propuesta",
    "upload": "Subir colección",
    "rekordbox_db": "Rekordbox 6 · BD local",
    "demo": "Demo sintética",
}
STRICTNESS_OPTIONS: Final[dict[HarmonicStrictness, str]] = {
    "strict": "Estricto",
    "energy_boost": "Energy boost",
    "permissive": "Permisivo",
}
STRICTNESS_HELP: Final[dict[HarmonicStrictness, str]] = {
    "strict": "Solo misma clave, ±1 y relativa A↔B. Pitch máx. 4 %.",
    "energy_boost": "Añade diagonal y saltos de energía +2 / +7. Pitch máx. 6 %.",
    "permissive": "Todo salvo saltos disonantes (incluye energy drop −2). Pitch máx. 8 %.",
}
PROFILE_OPTIONS: Final[dict[EnergyCurveProfile, str]] = {
    "warmup_to_peak": "Warmup → Peak → Closing",
    "rollercoaster": "Montaña rusa",
    "constant": "Constante",
}
CAMELOT_KEYS: Final[list[str]] = [f"{n}{m}" for n in range(1, 13) for m in ("A", "B")]
SPOTIFY_MAX_TRACKS: Final[int] = 500

SuggestionProvider = Literal["none", "spotify", "lastfm", "llm"]

SUGGESTION_PROVIDER_OPTIONS: Final[dict[SuggestionProvider, str]] = {
    "none": "Sin sugerencias (solo BPM/clave/energía)",
    "spotify": "Spotify (búsqueda por género)",
    "lastfm": "Last.fm (tags de género)",
    "llm": "Agente IA con búsqueda web (tu API key)",
}

COLOR_SET: Final[str] = "#2a78d6"  # categórico slot 1 (válido en claro y oscuro)
COLOR_TARGET: Final[str] = "#8a8984"  # referencia neutra
COLOR_BAND: Final[str] = "#8a8984"


@dataclass(slots=True)
class LoadedCollection:
    label: str
    result: ParseResult
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SuggestionConfig:
    """Fuente de canciones reales elegida para el modo propuesta, y sus credenciales."""

    provider: SuggestionProvider = "none"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    lastfm_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = DEFAULT_LLM_MODEL


# --------------------------------------------------------------------------- #
# Carga de datos (cacheada)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def get_graph() -> SetGraph:
    return build_set_graph()


@st.cache_data(show_spinner="Leyendo colección…", max_entries=4)
def cached_parse(filename: str, data: bytes, digest: str) -> ParseResult:
    del digest  # solo forma parte de la clave de caché
    return parse_file(filename, data)


def demo_collection() -> ParseResult:
    from src.app.__main__ import synthetic_collection

    tracks = synthetic_collection(size=160)
    return ParseResult(source=tracks[0].raw_source.system, tracks=tracks, energy_estimated=len(tracks))


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar_source() -> tuple[SourceMode, LoadedCollection | None]:
    st.sidebar.header("1 · Fuente")
    mode: SourceMode = st.sidebar.radio(
        "¿De dónde salen los temas?",
        options=list(SOURCE_OPTIONS),
        format_func=lambda m: SOURCE_OPTIONS[m],
        key="source_mode",
    )

    loaded: LoadedCollection | None = None
    if mode == "proposal":
        st.sidebar.caption(
            "Sin colección se genera el set ideal slot a slot: BPM, energía y clave Camelot "
            "de cada tema, listo para buscar en tu tienda o crate."
        )
    elif mode == "upload":
        st.sidebar.caption(
            "Formatos: XML de colección de **Rekordbox** · `m.db` de **Engine DJ** · "
            "`collection.nml` de **Traktor** · `database.xml` de **VirtualDJ** · **CSV** "
            "(Serato y cualquier otra app vía exportación)."
        )
        upload = st.sidebar.file_uploader(
            "Archivo de colección", type=list(SUPPORTED_EXTENSIONS), key="collection_file"
        )
        if upload is not None:
            data = upload.getvalue()
            try:
                result = cached_parse(upload.name, data, hashlib.sha256(data).hexdigest())
                loaded = LoadedCollection(label=upload.name, result=result)
            except ValueError as exc:
                st.sidebar.error(str(exc))
    elif mode == "rekordbox_db":
        st.sidebar.warning("Rekordbox tiene que estar **completamente cerrado**: bloquea su base de datos.")
        db_dir = st.sidebar.text_input("Carpeta de la BD (vacío = ubicación por defecto)", key="rb_db_dir")
        if st.sidebar.button("Leer base de datos", key="rb_read"):
            try:
                with st.spinner("Leyendo Rekordbox…"):
                    reader = Rekordbox6DatabaseReader(Path(db_dir) if db_dir.strip() else None)
                    st.session_state["rb_db_result"] = reader.read()
            except RuntimeError as exc:
                st.sidebar.error(str(exc))
        if "rb_db_result" in st.session_state:
            loaded = LoadedCollection(label="Rekordbox 6", result=st.session_state["rb_db_result"])
    else:
        loaded = LoadedCollection(label="Demo sintética (160 temas Tech House)", result=demo_collection())

    if loaded is not None:
        result = loaded.result
        st.sidebar.success(f"{loaded.label}: {len(result.tracks)} temas válidos")
        details = []
        if result.skipped:
            details.append(f"{result.skipped} descartados")
        if result.energy_estimated:
            details.append(f"{result.energy_estimated} con energía estimada por BPM")
        if details:
            st.sidebar.caption(" · ".join(details))
        for warning in result.warnings:
            st.sidebar.caption(f"⚠️ {warning}")
    return mode, loaded


def sidebar_playlist(loaded: LoadedCollection | None) -> list[UniversalTrack]:
    if loaded is None:
        return []
    tracks = loaded.result.tracks
    playlists = {name: ids for name, ids in loaded.result.playlists.items() if ids}
    if not playlists:
        return tracks
    choice = st.sidebar.selectbox(
        "Limitar a una playlist",
        options=["Toda la colección", *sorted(playlists)],
        key="playlist_choice",
    )
    if choice == "Toda la colección":
        return tracks
    wanted = set(playlists[choice])
    return [t for t in tracks if t.id in wanted]


def sidebar_spotify() -> tuple[str, str]:
    """Credenciales de Spotify para el enriquecimiento de una colección (audio-features)."""
    with st.sidebar.expander("🔑 Spotify (opcional)"):
        st.caption(
            "Con credenciales, se sustituye la energía y la clave estimadas por las reales "
            "de Spotify (audio-features)."
        )
        st.caption(
            "Spotify retiró `audio-features` el 27-11-2024: solo responden apps con cuota "
            "ampliada anterior a esa fecha; el resto recibe 403. Si no es tu caso, déjalo "
            "vacío: la app funciona igual con la energía estimada por BPM. Si falla, te "
            "avisará de cuántos temas se quedan sin datos reales."
        )
        client_id = st.text_input("Client ID", type="password", key="spotify_client_id")
        client_secret = st.text_input("Client Secret", type="password", key="spotify_client_secret")
    return client_id.strip(), client_secret.strip()


def sidebar_suggestions() -> SuggestionConfig:
    """
    Elige, para el modo propuesta, de dónde sale el tema real y distinto que se añade a
    cada slot. Nunca toca BPM/clave/energía -esos siguen siendo los del slot, calculados
    por la curva y la ruta armónica-, solo aporta título, artista y enlace reales.
    """
    st.sidebar.header("🎵 Canciones reales (opcional)")
    st.sidebar.caption(
        "Sin elegir fuente, la propuesta se queda con la búsqueda por parámetros de cada "
        "slot (BPM, clave, energía). Con una fuente, además se sugiere un tema real."
    )
    provider: SuggestionProvider = st.sidebar.radio(
        "Fuente de sugerencias",
        options=list(SUGGESTION_PROVIDER_OPTIONS),
        format_func=lambda p: SUGGESTION_PROVIDER_OPTIONS[p],
        key="suggestion_provider",
    )
    cfg = SuggestionConfig(provider=provider)
    if provider == "spotify":
        with st.sidebar.expander("🔑 Spotify", expanded=True):
            st.caption(
                "Búsqueda normal de Spotify, abierta para cualquier app -no hace falta una app "
                "antigua con cuota ampliada-: solo un Client ID y Secret gratis en el "
                "[dashboard de Spotify for Developers](https://developer.spotify.com/dashboard)."
            )
            cfg.spotify_client_id = st.text_input(
                "Client ID", type="password", key="spotify_client_id_proposal"
            ).strip()
            cfg.spotify_client_secret = st.text_input(
                "Client Secret", type="password", key="spotify_client_secret_proposal"
            ).strip()
    elif provider == "lastfm":
        with st.sidebar.expander("🔑 Last.fm", expanded=True):
            st.caption(
                "Alternativa a Spotify: la API key se obtiene al instante y gratis en "
                "[last.fm/api/account/create](https://www.last.fm/api/account/create), sin "
                "aprobación ni cuota especial."
            )
            cfg.lastfm_api_key = st.text_input("API key", type="password", key="lastfm_api_key").strip()
    elif provider == "llm":
        with st.sidebar.expander("🔑 Agente IA (Anthropic)", expanded=True):
            st.caption(
                "Un agente de Claude con búsqueda web real lee la curva completa del set -BPM, "
                "clave, energía y tramo de cada slot- y busca un tema real y coherente para cada "
                "uno en Beatport, 1001Tracklists, Resident Advisor, Spotify y SoundCloud."
            )
            st.caption(
                "Tiene coste por uso (tokens del modelo + ~10 USD por cada 1000 búsquedas web). "
                "Necesitas tu propia API key de "
                "[console.anthropic.com](https://console.anthropic.com/)."
            )
            cfg.llm_api_key = st.text_input(
                "API key de Anthropic", type="password", key="llm_api_key"
            ).strip()
            cfg.llm_model = (
                st.text_input("Modelo", value=DEFAULT_LLM_MODEL, key="llm_model").strip()
                or DEFAULT_LLM_MODEL
            )
    return cfg


# --------------------------------------------------------------------------- #
# Parámetros
# --------------------------------------------------------------------------- #
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())


def phase_editor(profile: EnergyCurveProfile) -> tuple[PhaseSpec, ...]:
    """Un control por tramo: peso en % y rango de energía. Se reinicia al cambiar de perfil."""
    defaults = ENERGY_PROFILES[profile]
    columns = st.columns(len(defaults))
    phases: list[PhaseSpec] = []
    for column, phase in zip(columns, defaults):
        with column:
            st.markdown(f"**{phase_label(phase.name)}**")
            weight = st.number_input(
                "Peso (%)",
                min_value=1,
                max_value=100,
                value=round(phase.weight * 100),
                step=5,
                key=f"w_{profile}_{_slug(phase.name)}",
            )
            low, high = st.slider(
                "Energía",
                min_value=0.0,
                max_value=10.0,
                value=(phase.energy_min, phase.energy_max),
                step=0.5,
                key=f"e_{profile}_{_slug(phase.name)}",
            )
        phases.append(PhaseSpec(name=phase.name, weight=float(weight), energy_min=low, energy_max=high))
    return tuple(phases)


def parameters(mode: SourceMode, pool: Sequence[UniversalTrack]) -> SetConstraint:
    st.subheader("2 · Parámetros del set")

    c1, c2, c3 = st.columns(3)
    with c1:
        duration = st.number_input("Duración (min)", min_value=15, max_value=720, value=60, step=15, key="duration")
    with c2:
        collection_genres = sorted({t.genre for t in pool if t.genre}, key=str.lower)
        options = collection_genres or known_genres()
        genres = st.multiselect(
            "Género(s)",
            options=options,
            default=[],
            accept_new_options=True,
            placeholder="Cualquiera" if pool else "Elige o escribe un género",
            key="genres",
        )
    with c3:
        auto_len = st.toggle("Minutos por tema automáticos", value=bool(pool), key=f"auto_len_{bool(pool)}",
                             help="Automático = mediana de duración de la colección. "
                                  "Manual = tiempo efectivo por tema, descontando solapes de mezcla.")
        avg_len: float | None = None
        if not auto_len:
            avg_len = st.number_input("Minutos por tema", min_value=2.0, max_value=12.0, value=5.0, step=0.5, key=f"avg_len_{bool(pool)}")

    genre_range = genre_bpm_range(genres)
    if pool:
        default_range = (float(min(t.bpm for t in pool)), float(max(t.bpm for t in pool)))
    else:
        default_range = genre_range or DEFAULT_BPM_RANGE

    c4, c5 = st.columns([1, 2])
    with c4:
        limit_bpm = st.toggle("Fijar rango de BPM", value=False, key="limit_bpm",
                              help="Sin fijar se usa el rango de la colección o, sin colección, el típico del género.")
    with c5:
        bpm_min: float | None = None
        bpm_max: float | None = None
        if limit_bpm:
            lo, hi = st.slider(
                "BPM",
                min_value=60.0,
                max_value=200.0,
                # Streamlit exige que min_value/max_value/value/step compartan tipo:
                # round() sin ndigits devuelve int, así que hay que forzarlo a float
                # o el slider lanza StreamlitAPIException al activar el toggle.
                value=(float(round(default_range[0])), float(round(default_range[1]))),
                step=1.0,
                key="bpm_range",
            )
            bpm_min, bpm_max = float(lo), float(hi)
        else:
            source = "colección" if pool else ("género" if genre_range else "por defecto")
            st.caption(f"Rango de BPM ({source}): {default_range[0]:g}–{default_range[1]:g}")

    st.markdown("**Mezcla armónica (rueda Camelot)**")
    c6, c7 = st.columns([2, 1])
    with c6:
        strictness: HarmonicStrictness = st.segmented_control(
            "Rigor armónico",
            options=list(STRICTNESS_OPTIONS),
            format_func=lambda s: STRICTNESS_OPTIONS[s],
            default="energy_boost",
            key="strictness",
            label_visibility="collapsed",
        ) or "energy_boost"
        st.caption(STRICTNESS_HELP[strictness])
    with c7:
        start_key: str | None = None
        if mode == "proposal":
            start_key = st.selectbox("Clave de inicio", CAMELOT_KEYS, index=CAMELOT_KEYS.index("8A"), key="start_key")

    st.markdown("**Curva de energía**")
    profile: EnergyCurveProfile = st.selectbox(
        "Perfil",
        options=list(PROFILE_OPTIONS),
        format_func=lambda p: PROFILE_OPTIONS[p],
        key="profile",
    )
    phases = phase_editor(profile)

    constraints = SetConstraint(
        total_duration_min=int(duration),
        target_genres=list(genres),
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        harmonic_strictness=strictness,
        energy_curve_profile=profile,
        energy_phases=phases,
        start_key=start_key,
        avg_track_duration_min=avg_len,
    )

    candidates = [t for t in pool if t.matches_genres(constraints.target_genres)]
    n_tracks = estimate_track_count(
        constraints.total_duration_sec, candidates, avg_len * 60 if avg_len else None
    )
    if pool:
        st.info(f"⏱️ {duration} min → **{n_tracks} temas**. Candidatos tras filtrar por género: {len(candidates)}.")
    else:
        st.info(f"⏱️ {duration} min → **{n_tracks} slots** en la propuesta.")
    return constraints


# --------------------------------------------------------------------------- #
# Ejecución y resultados
# --------------------------------------------------------------------------- #
def _progress_callback(progress: Any) -> Any:
    def on_progress(done: int, total: int, text: str) -> None:
        progress.progress(done / total, text=text)

    return on_progress


def run_build(
    constraints: SetConstraint,
    pool: Sequence[UniversalTrack],
    spotify: tuple[str, str],
    suggestion: SuggestionConfig | None,
) -> tuple[SetGraphState, EnrichmentReport | SuggestionReport | None]:
    tracks = list(pool)
    report: EnrichmentReport | SuggestionReport | None = None
    client_id, client_secret = spotify

    if tracks and client_id and client_secret:
        candidates = parse_collection_node(initial_state(constraints, tracks))["available_tracks"]
        if len(candidates) > SPOTIFY_MAX_TRACKS:
            st.warning(
                f"Spotify: solo se consultan los primeros {SPOTIFY_MAX_TRACKS} de "
                f"{len(candidates)} candidatos para no agotar la cuota."
            )
            candidates = candidates[:SPOTIFY_MAX_TRACKS]
        progress = st.progress(0.0, text="Consultando Spotify…")
        try:
            enriched, report = enrich_with_spotify(
                candidates, client_id, client_secret, _progress_callback(progress)
            )
            by_id = {t.id: t for t in enriched}
            tracks = [by_id.get(t.id, t) for t in tracks]
        except RuntimeError as exc:
            st.error(str(exc))
        finally:
            progress.empty()

    state = cast(SetGraphState, get_graph().invoke(initial_state(constraints, tracks)))

    if not tracks and suggestion is not None and suggestion.provider != "none" and state.get("selected_set"):
        progress = st.progress(0.0, text="Buscando canciones reales…")
        try:
            if suggestion.provider == "spotify" and suggestion.spotify_client_id and suggestion.spotify_client_secret:
                suggested, report = suggest_tracks_for_proposal(
                    state["selected_set"],
                    constraints.target_genres,
                    suggestion.spotify_client_id,
                    suggestion.spotify_client_secret,
                    _progress_callback(progress),
                )
                state["selected_set"] = suggested
            elif suggestion.provider == "lastfm" and suggestion.lastfm_api_key:
                suggested, report = suggest_tracks_for_proposal_lastfm(
                    state["selected_set"],
                    constraints.target_genres,
                    suggestion.lastfm_api_key,
                    _progress_callback(progress),
                )
                state["selected_set"] = suggested
            elif suggestion.provider == "llm" and suggestion.llm_api_key:
                suggested, report = suggest_tracks_for_proposal_llm(
                    state["selected_set"],
                    suggestion.llm_api_key,
                    suggestion.llm_model,
                    _progress_callback(progress),
                )
                state["selected_set"] = suggested
            else:
                st.warning(
                    "Falta la clave de la fuente de sugerencias elegida: la propuesta se queda "
                    "solo con la búsqueda por parámetros (BPM/clave/energía)."
                )
        except RuntimeError as exc:
            st.error(str(exc))
        finally:
            progress.empty()

    return state, report


def energy_chart(state: SetGraphState) -> alt.LayerChart:
    band, series = curve_frames(state.get("selected_set", []), state.get("target_slots", []))
    x = alt.X("Posición:Q", title="Posición en el set", axis=alt.Axis(tickMinStep=1, grid=False))
    band_layer = (
        alt.Chart(band)
        .mark_area(opacity=0.14, color=COLOR_BAND, interpolate="step-after")
        .encode(x=x, y=alt.Y("Mín:Q", title="Energía", scale=alt.Scale(domain=[0, 10])), y2="Máx:Q")
    )
    color = alt.Color(
        "Serie:N",
        scale=alt.Scale(domain=["Objetivo", "Set"], range=[COLOR_TARGET, COLOR_SET]),
        legend=alt.Legend(orient="top", title=None, symbolType="stroke", symbolStrokeWidth=3),
    )
    tooltip = [
        alt.Tooltip("Posición:Q", title="#"),
        alt.Tooltip("Tramo:N"),
        alt.Tooltip("Serie:N"),
        alt.Tooltip("Energía:Q", format=".1f"),
        alt.Tooltip("BPM:Q", format=".1f"),
        alt.Tooltip("Camelot:N"),
        alt.Tooltip("Tema:N"),
    ]
    lines = (
        alt.Chart(series)
        .mark_line(strokeWidth=2)
        .encode(
            x=x,
            y=alt.Y("Energía:Q", scale=alt.Scale(domain=[0, 10])),
            color=color,
            strokeDash=alt.StrokeDash(
                "Serie:N", scale=alt.Scale(domain=["Objetivo", "Set"], range=[[5, 4], [1, 0]]), legend=None
            ),
        )
    )
    hover = alt.selection_point(fields=["Posición"], nearest=True, on="pointerover", empty=False)
    points = (
        alt.Chart(series)
        .mark_point(filled=True, size=80)
        .encode(
            x=x,
            y="Energía:Q",
            color=color,
            opacity=alt.condition(hover, alt.value(1.0), alt.value(0.75)),
            tooltip=tooltip,
        )
        .add_params(hover)
    )
    rule = (
        alt.Chart(series)
        .mark_rule(color=COLOR_TARGET, strokeWidth=1)
        .encode(x=x, opacity=alt.condition(hover, alt.value(0.5), alt.value(0.0)))
    )
    return cast(alt.LayerChart, (band_layer + lines + rule + points).properties(height=280))


def bpm_chart(state: SetGraphState) -> alt.Chart:
    _, series = curve_frames(state.get("selected_set", []), state.get("target_slots", []))
    data = series[series["Serie"] == "Set"]
    return cast(alt.Chart, (
        alt.Chart(data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=60), strokeWidth=2, color=COLOR_SET)
        .encode(
            x=alt.X("Posición:Q", title="Posición en el set", axis=alt.Axis(tickMinStep=1, grid=False)),
            y=alt.Y("BPM:Q", title="BPM", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Posición:Q", title="#"), "Tramo:N", alt.Tooltip("BPM:Q", format=".1f"), "Camelot:N", "Tema:N"],
        )
        .properties(height=180)
    ))


def results(state: SetGraphState, report: EnrichmentReport | SuggestionReport | None) -> None:
    selected = state.get("selected_set", [])
    slots = state.get("target_slots", [])
    transitions = state.get("transitions", [])
    violations = state.get("violations", [])
    proposal = state.get("mode") == "proposal"

    st.subheader("3 · Resultado")
    if report is not None:
        (st.warning if report.fell_back else st.success)(report.summary())
    if not selected:
        st.error("No se ha podido construir el set.")
        return

    total_sec = sum(t.duration_sec for t in selected)
    valid = sum(1 for tr in transitions if tr.is_valid)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Modo", "Propuesta" if proposal else "Colección")
    m2.metric("Temas", len(selected))
    m3.metric("Duración", f"{total_sec / 60:.0f} min")
    m4.metric("Transiciones OK", f"{valid}/{len(transitions)}")

    if proposal:
        st.info(
            "Propuesta sin colección: cada fila es el tema **ideal** para ese momento del set. "
            "Úsala como guía de búsqueda (BPM, clave y energía) en tu tienda o en tus crates."
        )

    tab_curve, tab_table, tab_notes = st.tabs(["📈 Curva", "📋 Tracklist", "📝 Notas y avisos"])
    with tab_curve:
        st.altair_chart(energy_chart(state), width="stretch")
        st.caption("Área gris: rango de energía permitido en cada tramo. Línea discontinua: objetivo. Línea azul: el set.")
        st.altair_chart(bpm_chart(state), width="stretch")
    with tab_table:
        table = set_table(selected, slots, transitions, proposal)
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                "BPM": st.column_config.NumberColumn(format="%.1f"),
                "Energía": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.1f"),
                "Objetivo": st.column_config.NumberColumn(format="%.1f"),
                "Pitch %": st.column_config.NumberColumn(format="%.1f"),
                "Enlace": st.column_config.LinkColumn(display_text="Abrir ↗"),
            },
        )
    with tab_notes:
        st.text(state.get("curator_notes", ""))
        if violations:
            st.markdown("**Avisos**")
            for violation in violations:
                st.markdown(f"- {violation}")
        else:
            st.success("Sin avisos: todas las reglas se cumplen.")

    downloads(selected, slots, transitions, proposal)


def downloads(
    selected: Sequence[UniversalTrack],
    slots: Sequence[Any],
    transitions: Sequence[Any],
    proposal: bool,
) -> None:
    st.markdown("**Exportar**")
    name = st.text_input("Nombre de la playlist", value="SetBuilder", key="export_name")
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⬇️ CSV",
        data=to_csv(set_rows(selected, slots, transitions)),
        file_name=f"{name}.csv",
        mime="text/csv",
        width="stretch",
    )
    if proposal:
        c2.caption("M3U8 y XML de Rekordbox necesitan temas reales con ruta de archivo.")
        return
    m3u, missing_m3u = to_m3u8(selected, name)
    xml, missing_xml = to_rekordbox_xml(selected, name)
    exportable = len(selected) - missing_m3u
    c2.download_button(
        "⬇️ M3U8 (cualquier software)",
        data=m3u,
        file_name=f"{name}.m3u8",
        mime="audio/x-mpegurl",
        disabled=exportable == 0,
        width="stretch",
    )
    c3.download_button(
        "⬇️ Rekordbox XML",
        data=xml,
        file_name=f"{name}.xml",
        mime="application/xml",
        disabled=len(selected) - missing_xml == 0,
        width="stretch",
    )
    if missing_m3u:
        st.caption(f"{missing_m3u} temas no tienen ruta de archivo y no se incluyen en M3U8/XML.")


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Next-Gen DJ SetBuilder", page_icon="🎧", layout="wide")
    st.title("🎧 Next-Gen DJ SetBuilder")
    st.caption("Un set no es una lista de buenos temas: es una curva. Esta app la construye.")

    mode, loaded = sidebar_source()
    pool = sidebar_playlist(loaded)
    spotify = ("", "")
    suggestion: SuggestionConfig | None = None
    if mode == "proposal":
        suggestion = sidebar_suggestions()
    else:
        spotify = sidebar_spotify()

    if mode != "proposal" and not pool:
        st.info("Carga una colección en la barra lateral, o elige **Sin colección · propuesta**.")
        return

    constraints = parameters(mode, pool)

    if st.button("🚀 Construir set", type="primary", key="build"):
        with st.spinner("Construyendo la curva…"):
            state, report = run_build(constraints, pool, spotify, suggestion)
        st.session_state["last_result"] = (mode, state, report)

    last = st.session_state.get("last_result")
    if last is not None and last[0] == mode:
        _, state, report = last
        results(state, report)


if __name__ == "__main__":
    main()
