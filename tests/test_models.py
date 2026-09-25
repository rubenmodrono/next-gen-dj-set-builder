from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.energy import estimate_energy_from_bpm
from src.core.harmonic_engine import TransitionType
from src.core.models import SetConstraint, TransitionEvaluation
from tests.conftest import make_track


@pytest.mark.parametrize("key", ["1A", "9B", "10A", "12B", " 8a "])
def test_valid_camelot_keys(key: str) -> None:
    assert make_track("x", key=key).key == key.strip().upper()


@pytest.mark.parametrize("key", ["0A", "13B", "8C", "Am", "", "1AA"])
def test_invalid_camelot_keys(key: str) -> None:
    with pytest.raises(ValidationError):
        make_track("x", key=key)


def test_energy_bounds() -> None:
    with pytest.raises(ValidationError):
        make_track("x", energy=10.5)
    with pytest.raises(ValidationError):
        make_track("x", energy=-0.1)


def test_track_is_immutable_and_hashable() -> None:
    track = make_track("x")
    with pytest.raises(ValidationError):
        track.bpm = 130.0  # type: ignore[misc]
    assert len({track, make_track("x")}) == 1
    assert track.camelot_number == 8 and track.camelot_mode == "A"


def test_tags_normalized() -> None:
    track = make_track("x").model_copy(update={"tags": ("Vocal", "vocal", "Peak")})
    rebuilt = type(track).model_validate(track.model_dump(exclude={"camelot_number", "camelot_mode"}))
    assert rebuilt.tags == ("vocal", "peak")


def test_genre_matching() -> None:
    track = make_track("x", genre="Tech House")
    assert track.matches_genres([])
    assert track.matches_genres(["tech house"])
    assert not track.matches_genres(["techno"])
    assert not make_track("y", genre=None).matches_genres(["techno"])


def test_constraint_bpm_range_validation() -> None:
    with pytest.raises(ValidationError):
        SetConstraint(total_duration_min=60, bpm_min=130, bpm_max=120)
    with pytest.raises(ValidationError):
        SetConstraint(total_duration_min=60, harmonic_strictness="loose")  # type: ignore[arg-type]
    assert SetConstraint(total_duration_min=60, target_genres="Techno").target_genres == ["Techno"]


def test_transition_evaluation_model() -> None:
    ev = TransitionEvaluation(
        from_track_id="a",
        to_track_id="b",
        cost=0.2,
        transition_type=TransitionType.ADJACENT,
        bpm_delta=1.0,
        bpm_delta_pct=0.8,
        energy_delta=0.5,
        is_valid=True,
    )
    assert ev.transition_type is TransitionType.ADJACENT


@pytest.mark.parametrize(("bpm", "expected"), [(100, 1.0), (125, 5.0), (140, 10.0), (200, 10.0)])
def test_energy_estimation(bpm: float, expected: float) -> None:
    assert estimate_energy_from_bpm(bpm) == expected
