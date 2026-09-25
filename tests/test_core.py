from __future__ import annotations
import pytest

from src.core.harmonic_engine import TransitionType
from src.core.models import SetConstraint
from src.core.timeline import allocate_slot_counts, build_timeline, ENERGY_PROFILES
from src.core.transitions import effective_bpm_delta, evaluate_transition
from tests.conftest import make_track


def test_half_double_time_resolution() -> None:
    delta, pct = effective_bpm_delta(87.0, 174.0)
    assert pct == 0.0 and delta == 0.0


def test_adjacent_transition_is_valid_and_cheap() -> None:
    ev = evaluate_transition(make_track("a", key="8A"), make_track("b", key="9A", bpm=125.0))
    assert ev.transition_type is TransitionType.ADJACENT
    assert ev.is_valid and ev.cost < 1.0


def test_strict_rejects_energy_boost() -> None:
    a, b = make_track("a", key="8A"), make_track("b", key="10A")
    assert evaluate_transition(a, b, "energy_boost").is_valid
    assert not evaluate_transition(a, b, "strict").is_valid


def test_big_pitch_is_invalid() -> None:
    ev = evaluate_transition(make_track("a", bpm=120.0), make_track("b", bpm=132.0))
    assert not ev.is_valid


def test_slot_allocation_sums_exactly() -> None:
    for profile in ENERGY_PROFILES.values():
        for n in range(1, 30):
            assert sum(allocate_slot_counts(profile, n)) == n


def test_warmup_to_peak_timeline_shape(collection: list) -> None:
    constraints = SetConstraint(total_duration_min=60)
    slots = build_timeline(constraints, collection)
    assert len(slots) == 10  # 3600 s / 360 s
    phases = [s["phase"] for s in slots]
    assert phases.count("peak_time") == 5
    assert phases[0] == "warmup" and phases[-1] == "closing"
    assert slots[-1]["end_sec"] == 3600


def test_custom_phases_override_profile(collection: list) -> None:
    from src.core.models import PhaseSpec

    constraints = SetConstraint(
        total_duration_min=60,
        avg_track_duration_min=5.0,
        energy_phases=(
            PhaseSpec(name="intro", weight=1, energy_min=1, energy_max=3),
            PhaseSpec(name="drive", weight=3, energy_min=6, energy_max=9),
        ),
    )
    slots = build_timeline(constraints, collection)
    assert len(slots) == 12
    assert [s["phase"] for s in slots].count("intro") == 3
    assert all(1 <= s["target_energy"] <= 3 for s in slots if s["phase"] == "intro")


def test_phase_spec_validation() -> None:
    import pytest
    from pydantic import ValidationError

    from src.core.models import PhaseSpec

    with pytest.raises(ValidationError):
        PhaseSpec(name="x", weight=0.5, energy_min=8, energy_max=3)
    with pytest.raises(ValidationError):
        SetConstraint(total_duration_min=60, energy_phases=())


@pytest.mark.parametrize("strictness", ["strict", "energy_boost", "permissive"])
@pytest.mark.parametrize("profile", ["warmup_to_peak", "rollercoaster", "constant"])
def test_proposal_key_path_is_always_valid(strictness: str, profile: str) -> None:
    from src.core.harmonic_engine import StrictnessLevel, evaluate_harmonic_transition
    from src.core.proposal import plan_key_path
    from src.core.transitions import ALLOWED_HARMONIC_TYPES

    constraints = SetConstraint(
        total_duration_min=120, harmonic_strictness=strictness, energy_curve_profile=profile  # type: ignore[arg-type]
    )
    slots = build_timeline(constraints, [])
    keys = plan_key_path(slots, constraints.harmonic_strictness, "11B")
    assert keys[0] == "11B" and len(keys) == len(slots)
    for a, b in zip(keys, keys[1:]):
        kind, _ = evaluate_harmonic_transition(a, b, StrictnessLevel(strictness))
        assert kind in ALLOWED_HARMONIC_TYPES[strictness]


def test_genre_bpm_presets() -> None:
    from src.core.genres import genre_bpm_range
    from src.core.timeline import resolve_bpm_range

    assert genre_bpm_range(["Drum and Bass"]) == (170.0, 176.0)
    assert genre_bpm_range(["unknown"]) is None
    c = SetConstraint(total_duration_min=60, target_genres=["house", "techno"], bpm_max=130)
    assert resolve_bpm_range(c, []) == (118.0, 130.0)
