"""
Transformaciones puras del resultado del grafo a tablas para la UI.
Sin dependencia de Streamlit: testeables por separado.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from src.core.models import TransitionEvaluation, UniversalTrack
from src.core.timeline import TimelineSlot
from src.exporters import set_rows

PHASE_LABELS: dict[str, str] = {
    "warmup": "Warmup",
    "build": "Build",
    "breather": "Respiro",
    "peak_time": "Peak time",
    "closing": "Closing",
    "sustain": "Sostenido",
}

TRANSITION_LABELS: dict[str, str] = {
    "perfect": "Misma clave",
    "adjacent": "Adyacente ±1",
    "relative": "Relativa A↔B",
    "energy_boost_1": "Energy boost +7",
    "energy_boost_2": "Energy boost +2",
    "energy_drop": "Energy drop −2",
    "diagonal": "Diagonal",
    "discordant": "Disonante",
}


def phase_label(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase.replace("_", " ").capitalize())


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"


def set_table(
    selected: Sequence[UniversalTrack],
    slots: Sequence[TimelineSlot],
    transitions: Sequence[TransitionEvaluation],
    proposal: bool,
) -> pd.DataFrame:
    """Tabla del set: una fila por tema con su tramo y la transición de entrada."""
    has_suggestions = proposal and any(
        t.raw_source.payload.get("suggested_artist") for t in selected
    )
    records: list[dict[str, Any]] = []
    elapsed = 0
    for row in set_rows(selected, slots, transitions):
        t, tr = row.track, row.transition
        record: dict[str, Any] = {
            "#": row.position,
            "Inicio": format_duration(elapsed),
            "Tramo": phase_label(row.phase),
        }
        if proposal:
            if has_suggestions:
                artist = t.raw_source.payload.get("suggested_artist")
                title = t.raw_source.payload.get("suggested_title")
                record["Sugerencia"] = f"{artist} – {title}" if artist and title else "—"
                record["Fuente"] = t.raw_source.payload.get("suggested_source", "") or ""
                record["Enlace"] = t.raw_source.payload.get("suggested_url", "") or ""
            record["Busca"] = str(t.raw_source.payload.get("search_hint", ""))
        else:
            record["Artista"] = t.artist
            record["Título"] = t.title
        record.update(
            {
                "BPM": t.bpm,
                "Camelot": t.key,
                "Energía": t.energy,
                "Objetivo": row.target_energy if row.target_energy is not None else float("nan"),
                "Transición": TRANSITION_LABELS.get(tr.transition_type.value, tr.transition_type.value)
                if tr
                else "—",
                "Pitch %": round(tr.bpm_delta_pct, 1) if tr else float("nan"),
                "OK": ("✅" if tr.is_valid else "⚠️") if tr else "",
            }
        )
        records.append(record)
        elapsed += t.duration_sec
    return pd.DataFrame.from_records(records)


def curve_frames(
    selected: Sequence[UniversalTrack], slots: Sequence[TimelineSlot]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve (banda, series):
    - banda: rango de energía permitido por slot (para el área de fondo).
    - series: formato largo con la energía objetivo y la real del set.
    """
    band = pd.DataFrame.from_records(
        [
            {
                "Posición": s["index"] + 1,
                "Tramo": phase_label(s["phase"]),
                "Mín": s["energy_min"],
                "Máx": s["energy_max"],
            }
            for s in slots
        ]
    )
    series_records: list[dict[str, Any]] = []
    for slot, track in zip(slots, selected):
        common = {"Posición": slot["index"] + 1, "Tramo": phase_label(slot["phase"])}
        series_records.append(
            {**common, "Serie": "Objetivo", "Energía": slot["target_energy"], "BPM": slot["target_bpm"], "Tema": "—", "Camelot": "—"}
        )
        series_records.append(
            {
                **common,
                "Serie": "Set",
                "Energía": track.energy,
                "BPM": track.bpm,
                "Tema": f"{track.artist} – {track.title}",
                "Camelot": track.key,
            }
        )
    return band, pd.DataFrame.from_records(series_records)
