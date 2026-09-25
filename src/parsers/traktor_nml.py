"""Parser de la colección de Traktor (``collection.nml``)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.core.keys import pitch_class_to_camelot
from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator


def traktor_key(musical_key_value: str | None, info_key: str | None) -> str | None:
    """
    ``MUSICAL_KEY VALUE``: 0–11 mayores (C…B), 12–23 menores (Cm…Bm).
    Si falta, se usa el texto de ``INFO KEY`` (Open Key, Camelot o clásica).
    """
    if musical_key_value is not None and musical_key_value.strip().isdigit():
        value = int(musical_key_value)
        if 0 <= value <= 23:
            return pitch_class_to_camelot(value % 12, minor=value >= 12)
    return info_key


def traktor_path(volume: str | None, directory: str | None, filename: str | None) -> str | None:
    """``DIR="/:Users/:me/:Music/:"`` → ``/Users/me/Music/``; en Windows antepone el volumen."""
    if not filename:
        return None
    path = (directory or "").replace("/:", "/") + filename
    if volume and len(volume) == 2 and volume[1] == ":":
        return volume + path
    return path


def primary_key(volume: str | None, directory: str | None, filename: str | None) -> str:
    """Formato de ``PRIMARYKEY KEY`` en las playlists de Traktor."""
    return f"{volume or ''}{directory or ''}{filename or ''}"


class TraktorNmlParser:
    source: TrackSource = TrackSource.TRAKTOR

    def can_parse(self, filename: str, head: bytes) -> bool:
        return filename.lower().endswith(".nml") or b"<NML" in head[:4096]

    def parse(self, data: bytes) -> ParseResult:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"NML de Traktor mal formado: {exc}") from exc
        if root.tag != "NML":
            raise ValueError("El fichero no es una colección de Traktor (falta <NML>).")

        acc = TrackAccumulator(self.source)
        for entry in root.iterfind("./COLLECTION/ENTRY"):
            location = entry.find("LOCATION")
            info = entry.find("INFO")
            tempo = entry.find("TEMPO")
            musical_key = entry.find("MUSICAL_KEY")
            volume = location.get("VOLUME") if location is not None else None
            directory = location.get("DIR") if location is not None else None
            filename = location.get("FILE") if location is not None else None
            acc.add(
                track_id=primary_key(volume, directory, filename) or entry.get("AUDIO_ID", ""),
                title=entry.get("TITLE"),
                artist=entry.get("ARTIST"),
                bpm=tempo.get("BPM") if tempo is not None else None,
                key=traktor_key(
                    musical_key.get("VALUE") if musical_key is not None else None,
                    info.get("KEY") if info is not None else None,
                ),
                duration=info.get("PLAYTIME") if info is not None else None,
                genre=info.get("GENRE") if info is not None else None,
                tags=[info.get("LABEL", "")] if info is not None and info.get("LABEL") else [],
                location=traktor_path(volume, directory, filename),
                payload={k: v for k, v in entry.attrib.items()},
            )

        valid_ids = {t.id for t in acc.tracks}
        playlists: dict[str, list[str]] = {}
        for node in root.iter("NODE"):
            if node.get("TYPE") != "PLAYLIST":
                continue
            playlist = node.find("PLAYLIST")
            if playlist is None:
                continue
            ids = [pk.get("KEY", "") for pk in playlist.iter("PRIMARYKEY")]
            playlists[node.get("NAME", "Playlist")] = [i for i in ids if i in valid_ids]

        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=playlists,
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )
