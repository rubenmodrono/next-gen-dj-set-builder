"""Compilación del ``StateGraph`` del set builder."""

from __future__ import annotations

from typing import Final, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.graph.nodes import (
    SetCurator,
    build_timeline_slots_node,
    graph_search_node,
    make_llm_curator_node,
    parse_collection_node,
    proposal_node,
    route_after_timeline,
)
from src.graph.state import SetGraphState

PARSE: Final = "parse_collection_node"
TIMELINE: Final = "build_timeline_slots_node"
SEARCH: Final[Literal["graph_search_node"]] = "graph_search_node"
PROPOSAL: Final[Literal["proposal_node"]] = "proposal_node"
CURATOR: Final = "llm_curator_node"

SetGraph = CompiledStateGraph[SetGraphState, None, SetGraphState, SetGraphState]


def _after_timeline(state: SetGraphState) -> Literal["graph_search_node", "proposal_node"]:
    return SEARCH if route_after_timeline(state) else PROPOSAL


def build_set_graph(curator: SetCurator | None = None) -> SetGraph:
    """
    START → parse → timeline ─┬─(hay colección)→ graph_search ─┬→ curator → END
                              └─(sin colección)→ proposal ──────┘
    """
    graph: StateGraph[SetGraphState, None, SetGraphState, SetGraphState] = StateGraph(
        SetGraphState
    )

    graph.add_node(PARSE, parse_collection_node)
    graph.add_node(TIMELINE, build_timeline_slots_node)
    graph.add_node(SEARCH, graph_search_node)
    graph.add_node(PROPOSAL, proposal_node)
    graph.add_node(CURATOR, make_llm_curator_node(curator))

    graph.add_edge(START, PARSE)
    graph.add_edge(PARSE, TIMELINE)
    graph.add_conditional_edges(TIMELINE, _after_timeline, {SEARCH: SEARCH, PROPOSAL: PROPOSAL})
    graph.add_edge(SEARCH, CURATOR)
    graph.add_edge(PROPOSAL, CURATOR)
    graph.add_edge(CURATOR, END)

    return graph.compile()
