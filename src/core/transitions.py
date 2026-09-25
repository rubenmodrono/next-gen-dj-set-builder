"""
Evaluación de transiciones entre dos ``UniversalTrack``.

Combina el coste armónico (``harmonic_engine``) con el coste de tempo y de
energía. El resultado (``TransitionEvaluation.cost``) es el peso de arista que
usarán los algoritmos de búsqueda (greedy hoy, Dijkstra/A* después).
"""

from __future__ import annotations

from typing import Final

from src.core.harmonic_engine import (
    StrictnessLevel,
    TransitionType,
    evaluate_harmonic_transition,
)
from src.core.models import HarmonicStrictness, TransitionEvaluation, UniversalTrack

# Pitch máximo aceptable (%) según el rigor pedido.
MAX_BPM_DELTA_PCT: Final[dict[str, float]] = {
    "strict": 4.0,
    "energy_boost": 6.0,
    "permissive": 8.0,
}

# Tipos armónicos aceptados según el rigor pedido.
ALLOWED_HARMONIC_TYPES: Final[dict[str, frozenset[TransitionType]]] = {
    "strict": frozenset(
        {TransitionType.PERFECT, TransitionType.ADJACENT, TransitionType.RELATIVE}
    ),
    "energy_boost": frozenset(
        {
            TransitionType.PERFECT,
            TransitionType.ADJACENT,
            TransitionType.RELATIVE,
            TransitionType.DIAGONAL,
            TransitionType.ENERGY_BOOST_1,
            TransitionType.ENERGY_BOOST_2,
        }
    ),
    "permissive": frozenset(t for t in TransitionType if t is not TransitionType.DISCORDANT),
}

BPM_COST_PER_PCT: Final[float] = 0.5
ENERGY_COST_PER_POINT: Final[float] = 0.3
INVALID_PENALTY: Final[float] = 25.0
TEMPO_RATIOS: Final[tuple[float, ...]] = (1.0, 0.5, 2.0)


def effective_bpm_delta(bpm_from: float, bpm_to: float) -> tuple[float, float]:
    """
    Devuelve (delta_bpm, delta_pct) resolviendo half/double-time
    (p. ej. 87 → 174 en DnB/halftime cuenta como 0 %).
    """
    best_delta = bpm_to - bpm_from
    best_pct = abs(best_delta) / bpm_from * 100.0
    for ratio in TEMPO_RATIOS[1:]:
        delta = bpm_to * ratio - bpm_from
        pct = abs(delta) / bpm_from * 100.0
        if pct < best_pct:
            best_delta, best_pct = delta, pct
    return round(best_delta, 3), round(best_pct, 3)


def evaluate_transition(
    track_from: UniversalTrack,
    track_to: UniversalTrack,
    strictness: HarmonicStrictness = "energy_boost",
) -> TransitionEvaluation:
    """Calcula tipo, coste y validez de la mezcla ``track_from → track_to``."""
    harmonic_type, harmonic_cost = evaluate_harmonic_transition(
        track_from.key, track_to.key, StrictnessLevel(strictness)
    )
    bpm_delta, bpm_delta_pct = effective_bpm_delta(track_from.bpm, track_to.bpm)
    energy_delta = round(track_to.energy - track_from.energy, 3)

    harmonic_ok = harmonic_type in ALLOWED_HARMONIC_TYPES[strictness]
    tempo_ok = bpm_delta_pct <= MAX_BPM_DELTA_PCT[strictness]
    is_valid = harmonic_ok and tempo_ok

    cost = (
        harmonic_cost
        + bpm_delta_pct * BPM_COST_PER_PCT
        + abs(energy_delta) * ENERGY_COST_PER_POINT
        + (0.0 if is_valid else INVALID_PENALTY)
    )

    return TransitionEvaluation(
        from_track_id=track_from.id,
        to_track_id=track_to.id,
        cost=round(cost, 4),
        transition_type=harmonic_type,
        bpm_delta=bpm_delta,
        bpm_delta_pct=bpm_delta_pct,
        energy_delta=energy_delta,
        is_valid=is_valid,
    )
