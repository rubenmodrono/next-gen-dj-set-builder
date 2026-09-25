"""Parser de la base de datos de VirtualDJ (``database.xml``)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator, parse_float


def vdj_bpm(value: str | None) -> float | None:
    """VirtualDJ guarda segundos por beat (0.483871 → 124 BPM); versiones antiguas, BPM directo."""
    number = parse_float(value)
    if number is None or number <= 0:
        return None
    return round(60.0 / number, 2) if number < 5 else round(number, 2)


class VirtualDjXmlParser:
    source: TrackSource = TrackSource.VIRTUALDJ

    def can_parse(self, filename: str, head: bytes) -> bool:
        return b"VirtualDJ_Database" in head[:4096]

    def parse(self, data: bytes) -> ParseResult:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"database.xml de VirtualDJ mal formado: {exc}") from exc
        if root.tag != "VirtualDJ_Database":
            raise ValueError("El fichero no es una base de datos de VirtualDJ.")

        acc = TrackAccumulator(self.source)
        for song in root.iterfind("Song"):
            tags = song.find("Tags")
            infos = song.find("Infos")
            scan = song.find("Scan")
            path = song.get("FilePath")
            key = (tags.get("Key") if tags is not None else None) or (
                scan.get("Key") if scan is not None else None
            )
            bpm_raw = (scan.get("Bpm") if scan is not None else None) or (
                tags.get("Bpm") if tags is not None else None
            )
            acc.add(
                track_id=path or f"vdj-{len(acc.tracks) + acc.skipped + 1}",
                title=tags.get("Title") if tags is not None else None,
                artist=tags.get("Author") if tags is not None else None,
                bpm=vdj_bpm(bpm_raw),
                key=key,
                duration=infos.get("SongLength") if infos is not None else None,
                genre=tags.get("Genre") if tags is not None else None,
                location=path,
                payload=dict(song.attrib),
            )

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )
