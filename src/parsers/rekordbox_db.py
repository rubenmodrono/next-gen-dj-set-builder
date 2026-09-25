"""
Lector de la base de datos local de Rekordbox 6 mediante ``pyrekordbox``.

Rekordbox debe estar COMPLETAMENTE CERRADO: bloquea su base de datos mientras
está abierto. Para Rekordbox 7 (o si no quieres cerrar la app) usa la
exportación XML y ``RekordboxXmlParser``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

SMART_PLAYLIST_ATTRIBUTE = 4
FOLDER_ATTRIBUTE = 1


def _name_of(related: Any) -> str | None:
    """Lee ``.Name`` de una relación (Artist, Genre…) tolerando None."""
    if related is None:
        return None
    name = getattr(related, "Name", None)
    return str(name) if name else None


def _key_of(content: Any) -> str | None:
    key = getattr(content, "Key", None)
    if key is None:
        return None
    for attr in ("ScaleName", "Scale", "Name"):
        value = getattr(key, attr, None)
        if value:
            return str(value)
    return None


def content_to_fields(content: Any) -> dict[str, Any]:
    """Traduce un ``DjmdContent`` de pyrekordbox a campos planos (testeable sin BD)."""
    return {
        "track_id": getattr(content, "ID", ""),
        "title": getattr(content, "Title", None),
        "artist": _name_of(getattr(content, "Artist", None)),
        "bpm": getattr(content, "BPM", None),
        "key": _key_of(content),
        "duration": getattr(content, "Length", None),
        "genre": _name_of(getattr(content, "Genre", None)),
        "location": getattr(content, "FolderPath", None),
    }


class Rekordbox6DatabaseReader:
    source: TrackSource = TrackSource.REKORDBOX

    def __init__(self, db_dir: Path | None = None) -> None:
        self.db_dir = db_dir

    def read(self) -> ParseResult:
        try:
            from pyrekordbox import Rekordbox6Database
        except ImportError as exc:
            raise RuntimeError(
                "pyrekordbox no está instalado. Instálalo con: pip install -e '.[rekordbox]'"
            ) from exc

        try:
            db = Rekordbox6Database(db_dir=str(self.db_dir)) if self.db_dir else Rekordbox6Database()
        except Exception as exc:  # pyrekordbox lanza varios tipos según la causa
            raise RuntimeError(
                "No se pudo abrir la base de datos de Rekordbox. Comprueba que Rekordbox "
                f"está completamente cerrado. Detalle: {exc}"
            ) from exc

        try:
            acc = TrackAccumulator(self.source)
            for content in db.get_content():
                fields = content_to_fields(content)
                acc.add(**fields, payload={"ID": str(fields["track_id"])})
            valid_ids = {t.id for t in acc.tracks}
            playlists = self._read_playlists(db, valid_ids)
        finally:
            db.close()

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=playlists,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )

    @staticmethod
    def _read_playlists(db: Any, valid_ids: set[str]) -> dict[str, list[str]]:
        playlists: dict[str, list[str]] = {}
        try:
            for playlist in db.get_playlist():
                attribute = getattr(playlist, "Attribute", 0)
                if attribute in (FOLDER_ATTRIBUTE, SMART_PLAYLIST_ATTRIBUTE):
                    continue
                songs = sorted(getattr(playlist, "Songs", []) or [], key=lambda s: getattr(s, "TrackNo", 0) or 0)
                ids = [str(getattr(s, "ContentID", "")) for s in songs]
                playlists[str(getattr(playlist, "Name", "Playlist"))] = [i for i in ids if i in valid_ids]
        except Exception:  # las playlists son opcionales: si fallan, se usa la colección entera
            return {}
        return playlists
