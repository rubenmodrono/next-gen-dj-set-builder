"""
Rangos de BPM típicos por género. Se usan cuando no hay colección (modo
propuesta) y el DJ no ha fijado bpm_min/bpm_max.
"""

from __future__ import annotations

from typing import Final, Sequence

DEFAULT_BPM_RANGE: Final[tuple[float, float]] = (120.0, 128.0)

GENRE_BPM_RANGES: Final[dict[str, tuple[float, float]]] = {
    "downtempo": (90.0, 110.0),
    "disco": (110.0, 124.0),
    "nu disco": (112.0, 122.0),
    "deep house": (115.0, 124.0),
    "afro house": (118.0, 124.0),
    "house": (118.0, 126.0),
    "organic house": (112.0, 122.0),
    "melodic house & techno": (120.0, 126.0),
    "melodic techno": (120.0, 126.0),
    "progressive house": (120.0, 128.0),
    "tech house": (122.0, 128.0),
    "minimal": (124.0, 130.0),
    "breaks": (125.0, 135.0),
    "techno": (128.0, 138.0),
    "peak time techno": (130.0, 140.0),
    "trance": (132.0, 140.0),
    "psytrance": (138.0, 146.0),
    "dubstep": (138.0, 142.0),
    "hard techno": (140.0, 155.0),
    "hardstyle": (150.0, 160.0),
    "drum and bass": (170.0, 176.0),
    "drum & bass": (170.0, 176.0),
    "dnb": (170.0, 176.0),
}


def genre_bpm_range(genres: Sequence[str]) -> tuple[float, float] | None:
    """Rango combinado de los géneros conocidos; ``None`` si ninguno lo es."""
    ranges = [GENRE_BPM_RANGES[g.strip().lower()] for g in genres if g.strip().lower() in GENRE_BPM_RANGES]
    if not ranges:
        return None
    return (min(r[0] for r in ranges), max(r[1] for r in ranges))


def known_genres() -> list[str]:
    return sorted({g.title() for g in GENRE_BPM_RANGES if g not in ("dnb", "drum & bass")})
