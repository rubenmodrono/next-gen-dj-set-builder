from __future__ import annotations

from src.core.models import SetConstraint, UniversalTrack
from src.graph.builder import build_set_graph
from src.graph.nodes import CuratorReport, graph_search_node, parse_collection_node
from src.graph.state import SetGraphState, initial_state
from tests.conftest import make_track


def test_graph_has_expected_nodes() -> None:
    nodes = set(build_set_graph().get_graph().nodes)
    assert {
        "parse_collection_node",
        "build_timeline_slots_node",
        "graph_search_node",
        "llm_curator_node",
        "proposal_node",
    } <= nodes


def test_full_run_builds_complete_set(
    collection: list[UniversalTrack], constraints: SetConstraint
) -> None:
    result = build_set_graph().invoke(initial_state(constraints, collection))
    assert result["current_step"] == "llm_curator"
    assert len(result["selected_set"]) == len(result["target_slots"]) == 10
    assert len({t.id for t in result["selected_set"]}) == 10
    assert len(result["transitions"]) == 9
    assert "peak_time" in result["curator_notes"]
    peak = [t for t, s in zip(result["selected_set"], result["target_slots"]) if s["phase"] == "peak_time"]
    assert all(t.energy >= 5.0 for t in peak)


def test_run_is_deterministic(collection: list[UniversalTrack], constraints: SetConstraint) -> None:
    graph = build_set_graph()
    first = graph.invoke(initial_state(constraints, collection))
    second = graph.invoke(initial_state(constraints, list(reversed(collection))))
    assert [t.id for t in first["selected_set"]] == [t.id for t in second["selected_set"]]


def test_no_collection_builds_proposal() -> None:
    constraints = SetConstraint(
        total_duration_min=60, target_genres=["Techno"], avg_track_duration_min=5,
        harmonic_strictness="strict", start_key="5A",
    )
    result = build_set_graph().invoke(initial_state(constraints))
    assert result["mode"] == "proposal"
    selected = result["selected_set"]
    assert len(selected) == 12 and selected[0].key == "5A"
    assert all(128 <= t.bpm <= 138 for t in selected)  # rango típico de techno
    assert all(ev.is_valid for ev in result["transitions"])
    assert result["curator_notes"].startswith("Propuesta sin colección")
    assert result["violations"] == []


def test_filtered_out_collection_falls_back_to_proposal(constraints: SetConstraint) -> None:
    tracks = [make_track("a", genre="Techno")]
    result = build_set_graph().invoke(initial_state(constraints, tracks))
    assert result["mode"] == "proposal"
    assert len(result["selected_set"]) == 10
    assert any("se genera una propuesta" in v for v in result["violations"])


def test_parse_dedupes_and_filters_bpm() -> None:
    constraints = SetConstraint(total_duration_min=30, bpm_min=120, bpm_max=126)
    tracks = [make_track("a", bpm=124), make_track("a", bpm=124), make_track("b", bpm=130)]
    update = parse_collection_node(initial_state(constraints, tracks))
    assert [t.id for t in update["available_tracks"]] == ["a"]
    assert any("duplicados" in v for v in update["violations"])


def test_energy_window_widens_instead_of_failing(constraints: SetConstraint) -> None:
    state: SetGraphState = initial_state(constraints, [make_track("a", energy=4.0)])
    state["target_slots"] = [
        {
            "index": 0, "phase": "peak_time", "start_sec": 0, "end_sec": 360,
            "target_bpm": 126.0, "energy_min": 5.5, "energy_max": 10.0, "target_energy": 7.0,
        }
    ]
    update = graph_search_node(state)
    assert [t.id for t in update["selected_set"]] == ["a"]
    assert any("ampliada" in v for v in update["violations"])


def test_custom_curator_can_reorder(
    collection: list[UniversalTrack], constraints: SetConstraint
) -> None:
    def reversing_curator(state: SetGraphState) -> CuratorReport:
        ids = [t.id for t in state["selected_set"]]
        return CuratorReport(notes="reversed", reordered_ids=list(reversed(ids)))

    baseline = build_set_graph().invoke(initial_state(constraints, collection))
    result = build_set_graph(curator=reversing_curator).invoke(initial_state(constraints, collection))
    assert result["curator_notes"] == "reversed"
    assert [t.id for t in result["selected_set"]] == [t.id for t in reversed(baseline["selected_set"])]


def test_curator_rejects_invalid_permutation(
    collection: list[UniversalTrack], constraints: SetConstraint
) -> None:
    def bad_curator(state: SetGraphState) -> CuratorReport:
        return CuratorReport(notes="bad", reordered_ids=["nope"])

    result = build_set_graph(curator=bad_curator).invoke(initial_state(constraints, collection))
    assert any("permutación" in v for v in result["violations"])
    assert len(result["selected_set"]) == 10
