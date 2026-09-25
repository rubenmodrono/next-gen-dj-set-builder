"""
Parser CSV genérico (exportaciones propias, hojas de cálculo, otras apps).

Reconoce cabeceras en inglés y español, separador ``,`` o ``;`` y duraciones
en segundos o ``mm:ss``. Columnas mínimas: título, BPM, tonalidad y duración.
"""

from __future__ import annotations

import csv
import io
from typing import Final

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

COLUMN_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "id": ("id", "track_id", "trackid"),
    "title": ("title", "name", "track", "título", "titulo", "nombre"),
    "artist": ("artist", "artista"),
    "bpm": ("bpm", "tempo", "averagebpm"),
    "key": ("key", "camelot", "tonality", "tonalidad", "clave", "tono"),
    "energy": ("energy", "energía", "energia"),
    "duration": ("duration_sec", "duration", "length", "time", "totaltime", "duración", "duracion"),
    "genre": ("genre", "género", "genero"),
    "tags": ("tags", "etiquetas"),
    "location": ("location", "path", "file", "filepath", "ruta"),
}
REQUIRED: Final[tuple[str, ...]] = ("title", "bpm", "key", "duration")


def _resolve_columns(header: list[str]) -> dict[str, str]:
    lowered = {h.strip().lower(): h for h in header if h}
    mapping: dict[str, str] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field_name] = lowered[alias]
                break
    return mapping


class CsvCollectionParser:
    source: TrackSource = TrackSource.CSV

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith((".csv", ".tsv", ".txt"))

    def parse(self, data: bytes) -> ParseResult:
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        columns = _resolve_columns(list(reader.fieldnames or []))
        missing = [f for f in REQUIRED if f not in columns]
        if missing:
            raise ValueError(
                "Faltan columnas obligatorias en el CSV: "
                + ", ".join(missing)
                + f". Cabeceras encontradas: {reader.fieldnames}"
            )

        acc = TrackAccumulator(self.source)
        for index, row in enumerate(reader, start=1):
            def get(name: str) -> str | None:
                column = columns.get(name)
                return row.get(column) if column else None

            raw_tags = get("tags")
            acc.add(
                track_id=get("id") or f"row-{index}",
                title=get("title"),
                artist=get("artist"),
                bpm=get("bpm"),
                key=get("key"),
                duration=get("duration"),
                genre=get("genre"),
                energy=get("energy"),
                tags=[t for t in (raw_tags or "").replace(";", ",").split(",") if t.strip()],
                location=get("location") or None,
                payload={k: v for k, v in row.items() if k},
            )

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )
