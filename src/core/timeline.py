"""
Construcción de la curva del set: reparte la duración en tramos (fases) y
genera un slot por track con BPM y energía objetivo.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Final, Sequence, TypedDict

from src.core.genres import DEFAULT_BPM_RANGE, genre_bpm_range
from src.core.models import EnergyCurveProfile, PhaseSpec, SetConstraint, UniversalTrack

DEFAULT_TRACK_DURATION_SEC: Final[int] = 360

Phase = PhaseSpec


ENERGY_PROFILES: Final[dict[str, tuple[Phase, ...]]] = {
    "warmup_to_peak": (
        Phase(name="warmup", weight=0.25, energy_min=2.0, energy_max=5.0),
        Phase(name="peak_time", weight=0.50, energy_min=7.0, energy_max=10.0),
        Phase(name="closing", weight=0.25, energy_min=4.0, energy_max=6.5),
    ),
    "rollercoaster": (
        Phase(name="warmup", weight=0.15, energy_min=3.0, energy_max=5.0),
        Phase(name="build", weight=0.20, energy_min=6.0, energy_max=8.0),
        Phase(name="breather", weight=0.15, energy_min=4.0, energy_max=6.0),
        Phase(name="peak_time", weight=0.30, energy_min=8.0, energy_max=10.0),
        Phase(name="closing", weight=0.20, energy_min=4.0, energy_max=6.5),
    ),
    "constant": (Phase(name="sustain", weight=1.0, energy_min=6.0, energy_max=8.0),),
}


class TimelineSlot(TypedDict):
    index: int
    phase: str
    start_sec: int
    end_sec: int
    target_bpm: float
    energy_min: float
    energy_max: float
    target_energy: float


def estimate_track_count(
    total_duration_sec: int,
    candidates: Sequence[UniversalTrack],
    avg_track_duration_sec: float | None = None,
) -> int:
    """
    Nº de temas necesarios. Usa la duración media indicada por el DJ (tiempo
    efectivo por tema, descontando solapes de mezcla) o, si no la hay, la
    mediana de duración de los candidatos.
    """
    if avg_track_duration_sec is not None:
        typical: float = avg_track_duration_sec
    elif candidates:
        typical = median(t.duration_sec for t in candidates)
    else:
        typical = DEFAULT_TRACK_DURATION_SEC
    return max(1, math.ceil(total_duration_sec / typical))


def resolve_phases(constraints: SetConstraint) -> tuple[PhaseSpec, ...]:
    """Tramos personalizados si existen; si no, los del perfil elegido."""
    return constraints.energy_phases or ENERGY_PROFILES[constraints.energy_curve_profile]


def resolve_bpm_range(
    constraints: SetConstraint, candidates: Sequence[UniversalTrack]
) -> tuple[float, float]:
    """
    Prioridad: rango del usuario → rango real de la colección → rango típico
    del género (modo propuesta) → rango por defecto.
    """
    if candidates:
        pool_min = min(t.bpm for t in candidates)
        pool_max = max(t.bpm for t in candidates)
    else:
        pool_min, pool_max = genre_bpm_range(constraints.target_genres) or DEFAULT_BPM_RANGE
    low = constraints.bpm_min if constraints.bpm_min is not None else pool_min
    high = constraints.bpm_max if constraints.bpm_max is not None else pool_max
    return (min(low, high), max(low, high))


def allocate_slot_counts(phases: Sequence[Phase], total_slots: int) -> list[int]:
    """
    Reparto por mayor resto: la suma es exactamente ``total_slots``.
    Los pesos se normalizan, así que no hace falta que sumen 1.
    """
    total_weight = sum(p.weight for p in phases)
    raw = [p.weight / total_weight * total_slots for p in phases]
    counts = [math.floor(r) for r in raw]
    remainder = total_slots - sum(counts)
    order = sorted(range(len(phases)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:remainder]:
        counts[i] += 1
    return counts


def build_timeline(
    constraints: SetConstraint,
    candidates: Sequence[UniversalTrack],
    profile: EnergyCurveProfile | None = None,
) -> list[TimelineSlot]:
    phases = ENERGY_PROFILES[profile] if profile else resolve_phases(constraints)
    total_sec = constraints.total_duration_sec
    avg_sec = (
        constraints.avg_track_duration_min * 60.0
        if constraints.avg_track_duration_min is not None
        else None
    )
    n_slots = estimate_track_count(total_sec, candidates, avg_sec)
    slot_len = total_sec / n_slots
    bpm_low, bpm_high = resolve_bpm_range(constraints, candidates)

    slots: list[TimelineSlot] = []
    index = 0
    for phase, count in zip(phases, allocate_slot_counts(phases, n_slots)):
        if count == 0:
            continue
        for k in range(count):
            # Rampa lineal dentro del tramo: del mínimo al máximo de energía.
            progress = (k + 0.5) / count
            target_energy = phase.energy_min + progress * (phase.energy_max - phase.energy_min)
            target_bpm = bpm_low + (target_energy / 10.0) * (bpm_high - bpm_low)
            slots.append(
                TimelineSlot(
                    index=index,
                    phase=phase.name,
                    start_sec=round(index * slot_len),
                    end_sec=round((index + 1) * slot_len),
                    target_bpm=round(target_bpm, 2),
                    energy_min=phase.energy_min,
                    energy_max=phase.energy_max,
                    target_energy=round(target_energy, 2),
                )
            )
            index += 1
    return slots
