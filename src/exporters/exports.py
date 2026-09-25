"""
Exportadores del set final:

- ``to_csv``: tabla completa (tramo, transición, pitch…), para revisar o compartir.
- ``to_m3u8``: playlist universal (Rekordbox, Engine DJ, Traktor, Serato, VLC…).
- ``to_rekordbox_xml``: XML importable en Rekordbox (Preferencias → Avanzado →
  Base de datos → rekordbox xml) con el set como playlist.

M3U8 y XML necesitan la ruta del fichero de audio (``raw_source.location``),
que solo existe si la colección viene de Rekordbox o de un CSV con columna de ruta.
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Sequence
from urllib.parse import quote

from src.core.models import TransitionEvaluation, UniversalTrack
from src.core.timeline import TimelineSlot

PRODUCT_NAME = "rekordbox-setbuilder"
PRODUCT_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class SetRow:
    position: int
    phase: str
    track: UniversalTrack
    target_energy: float | None
    transition: TransitionEvaluation | None


def set_rows(
    selected: Sequence[UniversalTrack],
    slots: Sequence[TimelineSlot],
    transitions: Sequence[TransitionEvaluation],
) -> list[SetRow]:
    """Une track, slot y transición de entrada (la del tema anterior a este)."""
    incoming = {t.to_track_id: t for t in transitions}
    rows: list[SetRow] = []
    for index, track in enumerate(selected):
        slot = slots[index] if index < len(slots) else None
        rows.append(
            SetRow(
                position=index + 1,
                phase=slot["phase"] if slot else "",
                track=track,
                target_energy=slot["target_energy"] if slot else None,
                transition=incoming.get(track.id) if index > 0 else None,
            )
        )
    return rows


def to_csv(rows: Sequence[SetRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["position", "phase", "artist", "title", "bpm", "key", "energy", "target_energy",
         "duration_sec", "genre", "transition", "pitch_pct", "valid", "location",
         "suggested_artist", "suggested_title", "suggested_url", "suggested_source"]
    )
    for row in rows:
        t, tr = row.track, row.transition
        payload = t.raw_source.payload
        writer.writerow(
            [row.position, row.phase, t.artist, t.title, t.bpm, t.key, t.energy,
             row.target_energy if row.target_energy is not None else "",
             t.duration_sec, t.genre or "",
             tr.transition_type.value if tr else "",
             f"{tr.bpm_delta_pct:.2f}" if tr else "",
             ("yes" if tr.is_valid else "no") if tr else "",
             t.raw_source.location or "",
             payload.get("suggested_artist", ""),
             payload.get("suggested_title", ""),
             payload.get("suggested_url", ""),
             payload.get("suggested_source", "")]
        )
    return buffer.getvalue()


def to_m3u8(tracks: Sequence[UniversalTrack], title: str = "Set") -> tuple[str, int]:
    """Devuelve (contenido, nº de tracks omitidos por no tener ruta)."""
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    missing = 0
    for t in tracks:
        if not t.raw_source.location:
            missing += 1
            continue
        lines.append(f"#EXTINF:{t.duration_sec},{t.artist} - {t.title}")
        lines.append(t.raw_source.location)
    return "\n".join(lines) + "\n", missing


def path_to_location(path: str) -> str:
    """Ruta local → URI ``file://localhost/...`` que espera Rekordbox."""
    if len(path) > 1 and path[1] == ":":
        posix = PureWindowsPath(path).as_posix()
        return "file://localhost/" + quote(posix, safe="/:")
    return "file://localhost" + quote(str(PurePosixPath(path)), safe="/")


def to_rekordbox_xml(tracks: Sequence[UniversalTrack], playlist_name: str = "Set") -> tuple[str, int]:
    """Devuelve (XML, nº de tracks omitidos por no tener ruta)."""
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name=PRODUCT_NAME, Version=PRODUCT_VERSION, Company="")
    exportable = [t for t in tracks if t.raw_source.location]
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(exportable)))
    for number, t in enumerate(exportable, start=1):
        ET.SubElement(
            collection,
            "TRACK",
            TrackID=str(number),
            Name=t.title,
            Artist=t.artist,
            Genre=t.genre or "",
            TotalTime=str(t.duration_sec),
            AverageBpm=f"{t.bpm:.2f}",
            Tonality=t.key,
            Location=path_to_location(t.raw_source.location or ""),
        )
    playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    playlist = ET.SubElement(
        root_node, "NODE", Name=playlist_name, Type="1", KeyType="0", Entries=str(len(exportable))
    )
    for number in range(1, len(exportable) + 1):
        ET.SubElement(playlist, "TRACK", Key=str(number))
    ET.indent(root)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    return xml + "\n", len(tracks) - len(exportable)
