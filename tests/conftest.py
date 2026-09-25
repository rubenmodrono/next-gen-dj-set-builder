from __future__ import annotations

import pytest

from src.core.models import RawSource, SetConstraint, TrackSource, UniversalTrack


def make_track(
    track_id: str,
    bpm: float = 124.0,
    key: str = "8A",
    energy: float = 5.0,
    duration_sec: int = 360,
    genre: str | None = "Tech House",
    title: str | None = None,
    artist: str = "Test",
    location: str | None = None,
) -> UniversalTrack:
    return UniversalTrack(
        id=track_id,
        title=title or f"Track {track_id}",
        artist=artist,
        bpm=bpm,
        key=key,
        energy=energy,
        duration_sec=duration_sec,
        genre=genre,
        raw_source=RawSource(system=TrackSource.SYNTHETIC, location=location),
    )


@pytest.fixture
def collection() -> list[UniversalTrack]:
    keys = ["8A", "9A", "9B", "10A", "10B", "11A", "8B", "7A", "6A", "5A", "4A", "3A"]
    tracks: list[UniversalTrack] = []
    for i in range(36):
        energy = 2.0 + (i % 9)  # 2..10
        tracks.append(
            make_track(
                f"t{i:02d}",
                bpm=118.0 + (energy - 2.0) * 1.2,
                key=keys[i % len(keys)],
                energy=min(energy, 10.0),
            )
        )
    return tracks


@pytest.fixture
def constraints() -> SetConstraint:
    return SetConstraint(total_duration_min=60, target_genres=["tech house"])
