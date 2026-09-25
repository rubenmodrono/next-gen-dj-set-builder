"""Estimación de energía cuando la fuente no la proporciona (p. ej. Rekordbox)."""

from __future__ import annotations

ENERGY_FLOOR: float = 1.0
ENERGY_CEIL: float = 10.0
BPM_ENERGY_OFFSET: float = 110.0
BPM_ENERGY_DIVISOR: float = 3.0


def estimate_energy_from_bpm(bpm: float) -> float:
    """
    Heurística del proyecto: ``(BPM − 110) / 3`` acotado a 1–10.

    Burda entre géneros, razonable dentro de un mismo género (el caso de uso).
    """
    if bpm <= 0:
        raise ValueError(f"BPM debe ser positivo, recibido {bpm}")
    raw = (bpm - BPM_ENERGY_OFFSET) / BPM_ENERGY_DIVISOR
    return round(min(max(raw, ENERGY_FLOOR), ENERGY_CEIL), 2)
