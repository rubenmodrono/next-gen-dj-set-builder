"""
Parser del XML de colección de Rekordbox (Archivo → Exportar colección en formato xml).

Funciona con cualquier versión de Rekordbox (6 y 7) y no requiere cerrar la app.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

PLAYLIST_NODE_TYPE = "1"


def location_to_path(location: str | None) -> str | None:
    """``file://localhost/Users/x/My%20Track.mp3`` → ``/Users/x/My Track.mp3``."""
    if not location:
        return None
    parsed = urlparse(location)
    if parsed.scheme != "file":
        return unquote(location)
    path = unquote(parsed.path)
    # Windows: /C:/Music/... → C:/Music/...
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path


def _split_tags(*values: str | None) -> list[str]:
    tags: list[str] = []
    for value in values:
        if value:
            tags.extend(part for part in value.replace(",", " / ").split(" / ") if part.strip())
    return tags


class RekordboxXmlParser:
    source: TrackSource = TrackSource.REKORDBOX

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith(".xml") and b"DJ_PLAYLISTS" in head[:4096]

    def parse(self, data: bytes) -> ParseResult:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"XML de Rekordbox mal formado: {exc}") from exc
        if root.tag != "DJ_PLAYLISTS":
            raise ValueError("El fichero no es un XML de colección de Rekordbox (falta DJ_PLAYLISTS).")

        acc = TrackAccumulator(self.source)
        for node in root.iterfind("./COLLECTION/TRACK"):
            attrs = dict(node.attrib)
            acc.add(
                track_id=attrs.get("TrackID", ""),
                title=attrs.get("Name"),
                artist=attrs.get("Artist"),
                bpm=attrs.get("AverageBpm"),
                key=attrs.get("Tonality"),
                duration=attrs.get("TotalTime"),
                genre=attrs.get("Genre"),
                tags=_split_tags(attrs.get("Label"), attrs.get("Grouping")),
                location=location_to_path(attrs.get("Location")),
                payload=attrs,
            )

        valid_ids = {t.id for t in acc.tracks}
        playlists: dict[str, list[str]] = {}
        self._collect_playlists(root.find("./PLAYLISTS/NODE"), [], playlists, valid_ids)

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=playlists,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )

    def _collect_playlists(
        self,
        node: ET.Element | None,
        path: list[str],
        out: dict[str, list[str]],
        valid_ids: set[str],
    ) -> None:
        if node is None:
            return
        name = node.get("Name", "")
        if node.get("Type") == PLAYLIST_NODE_TYPE:
            ids = [t.get("Key", "") for t in node.iterfind("TRACK")]
            label = " / ".join([*path, name]) if path else name
            out[label] = [i for i in ids if i in valid_ids]
            return
        child_path = path if name == "ROOT" else [*path, name]
        for child in node.iterfind("NODE"):
            self._collect_playlists(child, child_path, out, valid_ids)
