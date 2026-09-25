"""
Tipos y utilidades compartidas por los proveedores de sugerencias de temas
reales para el modo propuesta (``spotify.py``, ``lastfm.py``, ``llm_agent.py``).

Los tres proveedores devuelven la misma forma -``(list[UniversalTrack],
SuggestionReport)``- para que la UI y los exportadores no necesiten saber
cuál se usó: el tema real sugerido vive en ``raw_source.payload`` bajo las
claves ``suggested_artist`` / ``suggested_title`` / ``suggested_url`` /
``suggested_source``, sin prefijo de proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from src.core.models import UniversalTrack

ProgressCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class SuggestionReport:
    attempted: int = 0
    suggested: int = 0
    failed: int = 0
    first_error: str = ""
    source: str = ""

    @property
    def fell_back(self) -> int:
        """Slots que se quedan solo con el marcador BPM/clave/energía."""
        return self.attempted - self.suggested

    def summary(self) -> str:
        prefix = f"{self.source}: " if self.source else ""
        text = (
            f"{prefix}{self.suggested}/{self.attempted} slots con una canción real sugerida. "
            f"{self.fell_back} se quedan con la búsqueda por parámetros (BPM/clave/energía)."
        )
        if self.first_error:
            text += f" Primer error: {self.first_error}"
        return text


def search_query_terms(genres: Sequence[str], fallback: str = "electronic") -> list[str]:
    """
    Términos a probar en orden: primero los géneros tal cual los escribió el
    usuario (más específicos), luego un término genérico de reserva.
    """
    terms = [g.strip() for g in genres if g.strip()]
    if fallback.lower() not in (t.lower() for t in terms):
        terms.append(fallback)
    return terms


def assign_candidates(
    placeholders: Sequence[UniversalTrack],
    candidates: Sequence[dict[str, str]],
    report: SuggestionReport,
) -> list[UniversalTrack]:
    """
    Reparte los candidatos reales (``{"artist", "title", "url"}``) uno a uno
    sobre los marcadores de la propuesta, en orden. Nunca toca BPM/clave/
    energía. Un marcador sin candidato disponible conserva el suyo tal cual.
    """
    suggested: list[UniversalTrack] = []
    for index, track in enumerate(placeholders):
        if index >= len(candidates):
            suggested.append(track)
            continue
        pick = candidates[index]
        report.suggested += 1
        payload: dict[str, Any] = {
            **track.raw_source.payload,
            "suggested_artist": pick["artist"],
            "suggested_title": pick["title"],
            "suggested_source": report.source,
        }
        if pick.get("url"):
            payload["suggested_url"] = pick["url"]
        suggested.append(
            track.model_copy(update={"raw_source": track.raw_source.model_copy(update={"payload": payload})})
        )
    return suggested
