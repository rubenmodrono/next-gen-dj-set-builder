"""Contrato común para todos los parsers de colecciones."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from src.core.models import TrackSource, UniversalTrack


class ParseResult(BaseModel):
    """Salida normalizada de cualquier parser."""

    model_config = ConfigDict(frozen=True)

    source: TrackSource
    tracks: list[UniversalTrack] = Field(default_factory=list)
    playlists: dict[str, list[str]] = Field(
        default_factory=dict, description="Nombre de playlist → ids de track, en orden."
    )
    skipped: int = 0
    energy_estimated: int = Field(
        default=0, description="Tracks cuya energía se ha estimado por BPM."
    )
    warnings: list[str] = Field(default_factory=list)

    @property
    def genres(self) -> list[str]:
        return sorted({t.genre for t in self.tracks if t.genre}, key=str.lower)


@runtime_checkable
class CollectionParser(Protocol):
    """
    Parser de ficheros exportados (XML, CSV…). Cada fabricante implementa este
    protocolo; el resto del sistema solo ve ``UniversalTrack``.
    """

    source: TrackSource

    def can_parse(self, filename: str, head: bytes) -> bool:
        """True si el fichero pertenece a este formato (por nombre y primeros bytes)."""
        ...

    def parse(self, data: bytes) -> ParseResult:
        """Lee el contenido completo del fichero y devuelve tracks normalizados."""
        ...
