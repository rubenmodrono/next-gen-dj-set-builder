"""
Nodos del grafo. Todos son funciones puras ``state -> actualización parcial``,
lo que permite testearlos sin compilar el grafo.

- ``parse_collection_node``: normaliza y filtra la colección (género, BPM, duplicados).
- ``build_timeline_slots_node``: genera la curva objetivo (slots con BPM/energía).
- ``proposal_node``: sin colección (o si nada pasa los filtros), genera el set
  ideal slot a slot con BPM, energía y ruta de claves Camelot.
- ``graph_search_node``: selección determinista slot a slot. Implementación base
  greedy sobre el mismo coste de arista que usará el futuro Dijkstra/A*.
- ``llm_curator_node``: curaduría narrativa. Recibe un ``SetCurator`` inyectable;
  por defecto usa ``rule_based_curator`` (sin dependencia de ningún LLM).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Final, Protocol, Sequence

from pydantic import BaseModel, Field

from src.core.models import SetConstraint, TransitionEvaluation, UniversalTrack
from src.core.proposal import build_proposal_tracks
from src.core.timeline import TimelineSlot, build_timeline
from src.core.transitions import evaluate_transition
from src.graph.state import SetGraphState, SetMode

StateUpdate = dict[str, Any]


class GraphNode(Protocol):
    """Firma de un nodo de LangGraph sobre ``SetGraphState``."""

    def __call__(self, state: SetGraphState) -> StateUpdate: ...

ENERGY_WINDOW_WIDENING: Final[float] = 2.0
ENERGY_FIT_WEIGHT: Final[float] = 0.8
BPM_FIT_WEIGHT_PER_PCT: Final[float] = 0.3
DURATION_TOLERANCE: Final[float] = 0.10


# --------------------------------------------------------------------------- #
# 1. Parseo / normalización
# --------------------------------------------------------------------------- #
def parse_collection_node(state: SetGraphState) -> StateUpdate:
    constraints = state["constraints"]
    violations: list[str] = []

    unique: dict[str, UniversalTrack] = {}
    for track in state["available_tracks"]:
        unique.setdefault(track.dedupe_key(), track)
    duplicates = len(state["available_tracks"]) - len(unique)
    if duplicates:
        violations.append(
            f"parse: {duplicates} tracks duplicados descartados (mismo archivo o misma "
            "combinación título/artista/BPM con un id distinto)."
        )

    filtered = [
        t
        for t in unique.values()
        if t.matches_genres(constraints.target_genres)
        and (constraints.bpm_min is None or t.bpm >= constraints.bpm_min)
        and (constraints.bpm_max is None or t.bpm <= constraints.bpm_max)
    ]
    filtered.sort(key=lambda t: (t.energy, t.bpm, t.id))

    mode: SetMode = "collection" if filtered else "proposal"
    if not filtered and state["available_tracks"]:
        violations.append(
            "parse: ningún track cumple género/BPM "
            f"(géneros={constraints.target_genres or 'cualquiera'}, "
            f"bpm={constraints.bpm_min}–{constraints.bpm_max}); se genera una propuesta."
        )

    return {
        "available_tracks": filtered,
        "mode": mode,
        "violations": violations,
        "current_step": "parse_collection",
    }


def route_after_timeline(state: SetGraphState) -> bool:
    """True si hay colección con la que buscar; False → modo propuesta."""
    return bool(state["available_tracks"])


# --------------------------------------------------------------------------- #
# 2. Curva objetivo
# --------------------------------------------------------------------------- #
def build_timeline_slots_node(state: SetGraphState) -> StateUpdate:
    tracks = state["available_tracks"]
    slots = build_timeline(state["constraints"], tracks)
    violations: list[str] = []
    if tracks and len(tracks) < len(slots):
        violations.append(
            f"timeline: colección insuficiente, {len(tracks)} temas para {len(slots)} slots."
        )
    return {
        "target_slots": slots,
        "violations": violations,
        "current_step": "build_timeline_slots",
    }


# --------------------------------------------------------------------------- #
# 3. Búsqueda
# --------------------------------------------------------------------------- #
def _slot_fit_cost(track: UniversalTrack, slot: TimelineSlot) -> float:
    energy_gap = abs(track.energy - slot["target_energy"])
    bpm_gap_pct = abs(track.bpm - slot["target_bpm"]) / slot["target_bpm"] * 100.0
    return energy_gap * ENERGY_FIT_WEIGHT + bpm_gap_pct * BPM_FIT_WEIGHT_PER_PCT


def _candidates_for_slot(
    pool: Sequence[UniversalTrack], slot: TimelineSlot
) -> tuple[list[UniversalTrack], float | None]:
    """
    Devuelve candidatos y la tolerancia usada: 0 → ventana nominal,
    ±2 → ventana ampliada (regla del proyecto), None → sin ventana (último recurso).
    """
    for tolerance in (0.0, ENERGY_WINDOW_WIDENING):
        low = slot["energy_min"] - tolerance
        high = slot["energy_max"] + tolerance
        inside = [t for t in pool if low <= t.energy <= high]
        if inside:
            return inside, tolerance
    return list(pool), None


def graph_search_node(state: SetGraphState) -> StateUpdate:
    constraints = state["constraints"]
    slots = state.get("target_slots", [])
    remaining: dict[str, UniversalTrack] = {t.id: t for t in state["available_tracks"]}
    selected: list[UniversalTrack] = []
    transitions: list[TransitionEvaluation] = []
    violations: list[str] = []

    for slot in slots:
        if not remaining:
            violations.append(
                f"search: sin temas para slot {slot['index']} ({slot['phase']}); set incompleto."
            )
            break

        candidates, tolerance = _candidates_for_slot(list(remaining.values()), slot)
        if tolerance is None:
            violations.append(
                f"search: slot {slot['index']} ({slot['phase']}) sin temas en energía "
                f"{slot['energy_min']}–{slot['energy_max']} ni ampliando ±{ENERGY_WINDOW_WIDENING}."
            )
        elif tolerance > 0:
            violations.append(
                f"search: slot {slot['index']} ({slot['phase']}) ventana de energía "
                f"ampliada ±{tolerance}."
            )

        previous = selected[-1] if selected else None
        best_track: UniversalTrack | None = None
        best_eval: TransitionEvaluation | None = None
        best_score = float("inf")
        for cand in sorted(candidates, key=lambda t: t.id):
            evaluation = (
                evaluate_transition(previous, cand, constraints.harmonic_strictness)
                if previous
                else None
            )
            score = _slot_fit_cost(cand, slot) + (evaluation.cost if evaluation else 0.0)
            if score < best_score:
                best_track, best_eval, best_score = cand, evaluation, score

        assert best_track is not None  # candidates nunca está vacío aquí
        selected.append(best_track)
        del remaining[best_track.id]
        if best_eval is not None:
            transitions.append(best_eval)

    return {
        "selected_set": selected,
        "transitions": transitions,
        "violations": violations,
        "current_step": "graph_search",
    }


# --------------------------------------------------------------------------- #
# 3b. Propuesta (sin colección)
# --------------------------------------------------------------------------- #
def proposal_node(state: SetGraphState) -> StateUpdate:
    """Genera el set ideal slot a slot a partir solo de los parámetros."""
    constraints = state["constraints"]
    slots = state.get("target_slots", [])
    placeholders = build_proposal_tracks(slots, constraints)
    transitions = [
        evaluate_transition(a, b, constraints.harmonic_strictness)
        for a, b in zip(placeholders, placeholders[1:])
    ]
    return {
        "selected_set": placeholders,
        "transitions": transitions,
        "violations": [],
        "current_step": "proposal",
    }


# --------------------------------------------------------------------------- #
# 4. Curaduría
# --------------------------------------------------------------------------- #
class CuratorReport(BaseModel):
    """Salida de cualquier curador (reglas o LLM)."""

    notes: str
    violations: list[str] = Field(default_factory=list)
    reordered_ids: list[str] | None = Field(
        default=None,
        description="Permutación opcional del set propuesta por el curador.",
    )


SetCurator = Callable[[SetGraphState], CuratorReport]


def _phase_summary(tracks: Sequence[UniversalTrack], slots: Sequence[TimelineSlot]) -> str:
    by_phase: dict[str, list[UniversalTrack]] = defaultdict(list)
    order: list[str] = []
    for track, slot in zip(tracks, slots):
        if slot["phase"] not in by_phase:
            order.append(slot["phase"])
        by_phase[slot["phase"]].append(track)
    lines: list[str] = []
    for phase in order:
        items = by_phase[phase]
        lines.append(
            f"{phase}: {len(items)} temas, "
            f"{items[0].bpm:g}→{items[-1].bpm:g} BPM, "
            f"energía {items[0].energy:g}→{items[-1].energy:g}, "
            f"claves {' → '.join(t.key for t in items)}"
        )
    return "\n".join(lines)


def rule_based_curator(state: SetGraphState) -> CuratorReport:
    """Curador determinista: audita el set y redacta un resumen por tramo."""
    constraints: SetConstraint = state["constraints"]
    selected = state.get("selected_set", [])
    slots = state.get("target_slots", [])
    transitions = state.get("transitions", [])
    violations: list[str] = []

    for ev in transitions:
        if not ev.is_valid:
            violations.append(
                f"curator: transición {ev.from_track_id}→{ev.to_track_id} fuera de reglas "
                f"({ev.transition_type.value}, pitch {ev.bpm_delta_pct:.1f}%)."
            )

    total_sec = sum(t.duration_sec for t in selected)
    target_sec = constraints.total_duration_sec
    if selected and abs(total_sec - target_sec) > target_sec * DURATION_TOLERANCE:
        violations.append(
            f"curator: duración {total_sec / 60:.1f} min vs objetivo "
            f"{constraints.total_duration_min} min (±{DURATION_TOLERANCE:.0%})."
        )

    valid = sum(1 for ev in transitions if ev.is_valid)
    prefix = "Propuesta sin colección · " if state.get("mode") == "proposal" else ""
    header = (
        f"{prefix}Set de {len(selected)} temas · {total_sec / 60:.1f} min · "
        f"perfil {constraints.energy_curve_profile} · "
        f"{valid}/{len(transitions)} transiciones dentro de reglas ({constraints.harmonic_strictness})."
    )
    notes = header if not selected else f"{header}\n{_phase_summary(selected, slots)}"
    return CuratorReport(notes=notes, violations=violations)


def make_llm_curator_node(curator: SetCurator | None = None) -> GraphNode:
    """
    Fábrica del nodo de curaduría. ``curator`` puede envolver un LLM
    (p. ej. un chat model con salida estructurada ``CuratorReport``).
    """
    active: SetCurator = curator or rule_based_curator

    def llm_curator_node(state: SetGraphState) -> StateUpdate:
        report = active(state)
        selected = state.get("selected_set", [])
        violations = list(report.violations)
        update: StateUpdate = {"curator_notes": report.notes, "current_step": "llm_curator"}

        if report.reordered_ids is not None:
            by_id = {t.id: t for t in selected}
            if sorted(report.reordered_ids) == sorted(by_id):
                update["selected_set"] = [by_id[i] for i in report.reordered_ids]
            else:
                violations.append(
                    "curator: reordenación rechazada, no es una permutación del set seleccionado."
                )

        update["violations"] = violations
        return update

    llm_curator_node.__name__ = "llm_curator_node"
    return llm_curator_node


llm_curator_node: GraphNode = make_llm_curator_node()
