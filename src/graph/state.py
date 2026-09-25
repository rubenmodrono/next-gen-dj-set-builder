"""Estado global que circula entre los nodos del grafo de LangGraph."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, NotRequired, Required, Sequence, TypedDict

from src.core.models import SetConstraint, TransitionEvaluation, UniversalTrack
from src.core.timeline import TimelineSlot

SetMode = Literal["collection", "proposal"]


class SetGraphState(TypedDict, total=False):
    """
    ``constraints`` y ``available_tracks`` son la entrada obligatoria; el resto
    lo van rellenando los nodos.

    ``violations`` usa un reducer de concatenación: cada nodo devuelve solo sus
    avisos nuevos y LangGraph los acumula a lo largo de la ejecución.
    """

    constraints: Required[SetConstraint]
    available_tracks: Required[list[UniversalTrack]]
    target_slots: NotRequired[list[TimelineSlot]]
    selected_set: NotRequired[list[UniversalTrack]]
    violations: NotRequired[Annotated[list[str], operator.add]]
    current_step: NotRequired[str]
    mode: NotRequired[SetMode]
    transitions: NotRequired[list[TransitionEvaluation]]
    curator_notes: NotRequired[str]


def initial_state(
    constraints: SetConstraint, tracks: Sequence[UniversalTrack] = ()
) -> SetGraphState:
    """Estado de entrada listo para ``graph.invoke``. Sin tracks → modo propuesta."""
    return SetGraphState(
        constraints=constraints,
        available_tracks=list(tracks),
        target_slots=[],
        selected_set=[],
        violations=[],
        current_step="init",
        mode="proposal" if not tracks else "collection",
        transitions=[],
        curator_notes="",
    )
