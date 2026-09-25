"""
Parser de la base de datos de Engine DJ (``Engine Library/Database2/m.db``).

La BD es SQLite. El esquema cambia entre versiones, así que las columnas se
detectan con ``PRAGMA table_info`` en lugar de asumirlas.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from src.core.models import TrackSource
from src.parsers.base import ParseResult
from src.parsers.common import TrackAccumulator

SQLITE_MAGIC = b"SQLite format 3\x00"


def engine_key(value: Any) -> str | None:
    """
    Engine DJ numera las tonalidades 0–23 recorriendo el círculo de quintas en
    parejas (mayor, relativa menor): 0 = C (8B), 1 = Am (8A), 2 = G (9B), …
    """
    if value is None:
        return None
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= index <= 23:
        return None
    number = (7 + index // 2) % 12 + 1
    return f"{number}{'B' if index % 2 == 0 else 'A'}"


def _first_present(columns: set[str], *names: str) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


class EngineDjParser:
    source: TrackSource = TrackSource.ENGINE_DJ

    def can_parse(self, filename: str, head: bytes) -> bool:
        return head.startswith(SQLITE_MAGIC)

    def parse(self, data: bytes) -> ParseResult:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "m.db"
            db_path.write_bytes(data)
            return self.parse_path(db_path)

    def parse_path(self, db_path: Path) -> ParseResult:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return self._read(connection)
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"No es una base de datos de Engine DJ válida: {exc}") from exc
        finally:
            connection.close()

    def _read(self, connection: sqlite3.Connection) -> ParseResult:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(Track)")}
        if not columns:
            raise ValueError("La base de datos no tiene tabla 'Track' (¿es el m.db de Engine DJ?).")

        bpm_col = _first_present(columns, "bpmAnalyzed", "bpm")
        wanted = {
            "id": "id",
            "title": _first_present(columns, "title"),
            "artist": _first_present(columns, "artist"),
            "bpm": bpm_col,
            "key": _first_present(columns, "key"),
            "length": _first_present(columns, "length"),
            "genre": _first_present(columns, "genre"),
            "path": _first_present(columns, "path"),
            "label": _first_present(columns, "label"),
        }
        selected = {alias: col for alias, col in wanted.items() if col}
        sql = "SELECT " + ", ".join(f'"{col}" AS {alias}' for alias, col in selected.items()) + " FROM Track"
        connection.row_factory = sqlite3.Row

        acc = TrackAccumulator(self.source)
        for row in connection.execute(sql):
            record = dict(row)
            acc.add(
                track_id=record.get("id", ""),
                title=record.get("title"),
                artist=record.get("artist"),
                bpm=record.get("bpm"),
                key=engine_key(record.get("key")),
                duration=record.get("length"),
                genre=record.get("genre"),
                tags=[record["label"]] if record.get("label") else [],
                location=record.get("path"),
                payload={k: v for k, v in record.items() if isinstance(v, (str, int, float))},
            )

        valid_ids = {t.id for t in acc.tracks}
        return ParseResult(
            source=self.source,
            tracks=acc.tracks,
            playlists=self._playlists(connection, valid_ids),
            skipped=acc.skipped,
            energy_estimated=acc.energy_estimated,
            warnings=acc.warnings(),
        )

    @staticmethod
    def _playlists(connection: sqlite3.Connection, valid_ids: set[str]) -> dict[str, list[str]]:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"Playlist", "PlaylistEntity"} <= tables:
            return {}
        entity_cols = {row[1] for row in connection.execute("PRAGMA table_info(PlaylistEntity)")}
        playlists: dict[str, list[str]] = {}
        for pl in connection.execute("SELECT id, title FROM Playlist"):
            rows = list(connection.execute("SELECT * FROM PlaylistEntity WHERE listId = ?", (pl["id"],)))
            ordered = rows
            if "nextEntityId" in entity_cols and rows:
                # Engine guarda el orden como lista enlazada: se reconstruye desde el primer elemento.
                by_id = {r["id"]: r for r in rows}
                pointed = {r["nextEntityId"] for r in rows}
                head = next((r for r in rows if r["id"] not in pointed), rows[0])
                ordered, seen = [], set()
                node = head
                while node is not None and node["id"] not in seen:
                    ordered.append(node)
                    seen.add(node["id"])
                    node = by_id.get(node["nextEntityId"])
            ids = [str(r["trackId"]) for r in ordered]
            playlists[str(pl["title"])] = [i for i in ids if i in valid_ids]
        return playlists
