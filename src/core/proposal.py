"""
Modo propuesta: sin colección de entrada, genera un plan de set slot a slot.

Cada slot se convierte en un ``UniversalTrack`` de marcador (fuente SYNTHETIC)
con el BPM, la energía, la duración y la clave Camelot que debería tener el
tema ideal. Las claves siguen una ruta armónica que respeta el rigor pedido y
acompaña la curva: si la energía sube, la rueda avanza (+1, o +2 si se permiten
energy boosts); si baja, retrocede; si se mantiene, alterna relativa y adyacente.
"""

from __future__ import annotations

from typing import Final, Sequence

from src.core.harmonic_engine import StrictnessLevel, evaluate_harmonic_transition
from src.core.models import (
    HarmonicStrictness,
    RawSource,
    SetConstraint,
    TrackSource,
    UniversalTrack,
)
from src.core.timeline import TimelineSlot
from src.core.transitions import ALLOWED_HARMONIC_TYPES

DEFAULT_START_KEY: Final[str] = "8A"
BIG_STEP: Final[float] = 1.0
SMALL_STEP: Final[float] = 0.25
PROPOSAL_ARTIST: Final[str] = "Propuesta"


def shift_key(key: str, steps: int = 0, switch_mode: bool = False) -> str:
    """Mueve ``steps`` posiciones en la rueda y opcionalmente cambia A↔B."""
    number = int(key[:-1])
    mode = key[-1]
    new_number = (number - 1 + steps) % 12 + 1
    if switch_mode:
        mode = "B" if mode == "A" else "A"
    return f"{new_number}{mode}"


def _candidate_moves(energy_delta: float, index: int) -> list[tuple[int, bool]]:
    """Movimientos preferidos (pasos, cambio de modo) según la dirección de la energía."""
    if energy_delta > BIG_STEP:
        return [(2, False), (1, False), (0, False)]
    if energy_delta > SMALL_STEP:
        return [(1, False), (0, False)]
    if energy_delta < -BIG_STEP:
        return [(-2, False), (-1, False), (0, False)]
    if energy_delta < -SMALL_STEP:
        return [(-1, False), (0, False)]
    if index % 2:
        return [(0, True), (0, False)]
    return [(1, False), (0, False)]


def plan_key_path(
    slots: Sequence[TimelineSlot],
    strictness: HarmonicStrictness,
    start_key: str | None = None,
) -> list[str]:
    """Una clave por slot; cada paso es una transición válida para ``strictness``."""
    if not slots:
        return []
    allowed = ALLOWED_HARMONIC_TYPES[strictness]
    keys = [start_key or DEFAULT_START_KEY]
    for index in range(1, len(slots)):
        current = keys[-1]
        delta = slots[index]["target_energy"] - slots[index - 1]["target_energy"]
        chosen = current
        for steps, switch in _candidate_moves(delta, index):
            candidate = shift_key(current, steps, switch)
            kind, _ = evaluate_harmonic_transition(current, candidate, StrictnessLevel(strictness))
            if kind in allowed:
                chosen = candidate
                break
        keys.append(chosen)
    return keys


def build_proposal_tracks(
    slots: Sequence[TimelineSlot], constraints: SetConstraint
) -> list[UniversalTrack]:
    """Marcadores de tema ideal por slot, listos para pasar por el resto del grafo."""
    keys = plan_key_path(slots, constraints.harmonic_strictness, constraints.start_key)
    genre = constraints.target_genres[0] if constraints.target_genres else None
    tracks: list[UniversalTrack] = []
    for slot, key in zip(slots, keys):
        bpm = round(slot["target_bpm"] * 2) / 2
        energy = round(slot["target_energy"], 1)
        hint = f"{genre or 'cualquier género'} · {bpm:g} BPM · {key} · energía {energy:g}"
        tracks.append(
            UniversalTrack(
                id=f"slot-{slot['index'] + 1:02d}",
                title=f"Slot {slot['index'] + 1} · {slot['phase']}",
                artist=PROPOSAL_ARTIST,
                bpm=bpm,
                key=key,
                energy=energy,
                duration_sec=max(1, slot["end_sec"] - slot["start_sec"]),
                genre=genre,
                tags=("propuesta", slot["phase"]),
                raw_source=RawSource(
                    system=TrackSource.SYNTHETIC,
                    native_id=f"slot-{slot['index'] + 1:02d}",
                    payload={"search_hint": hint},
                ),
            )
        )
    return tracks
