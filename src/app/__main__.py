"""
Demo en modo standalone/sintético: ``python -m src.app``.

Genera una colección determinista, construye un set de 60 min y lo imprime.
"""

from __future__ import annotations

import random

from src.core.energy import estimate_energy_from_bpm
from src.core.models import SetConstraint, UniversalTrack
from src.graph.builder import build_set_graph
from src.graph.state import initial_state

CAMELOT_KEYS: tuple[str, ...] = tuple(f"{n}{m}" for n in range(1, 13) for m in ("A", "B"))


def synthetic_collection(size: int = 80, seed: int = 7) -> list[UniversalTrack]:
    rng = random.Random(seed)
    tracks: list[UniversalTrack] = []
    for i in range(size):
        bpm = round(rng.uniform(116.0, 134.0), 1)
        tracks.append(
            UniversalTrack(
                id=f"syn-{i:03d}",
                title=f"Synthetic Track {i:03d}",
                artist=f"Artist {rng.randint(1, 20)}",
                bpm=bpm,
                key=rng.choice(CAMELOT_KEYS),
                energy=estimate_energy_from_bpm(bpm),
                duration_sec=rng.randint(300, 480),
                genre="Tech House",
            )
        )
    return tracks


def main() -> None:
    constraints = SetConstraint(
        total_duration_min=60,
        target_genres=["Tech House"],
        harmonic_strictness="energy_boost",
        energy_curve_profile="warmup_to_peak",
    )
    graph = build_set_graph()
    result = graph.invoke(initial_state(constraints, synthetic_collection()))

    print(result["curator_notes"], end="\n\n")
    for pos, track in enumerate(result["selected_set"], start=1):
        print(f"{pos:>2}. {track.key:>3}  {track.bpm:6.1f} BPM  E{track.energy:4.1f}  {track.title}")
    if result["violations"]:
        print("\nAvisos:")
        for violation in result["violations"]:
            print(f" - {violation}")


if __name__ == "__main__":
    main()
