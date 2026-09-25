"""
Parsers de colecciones → UniversalTrack.

Formatos soportados (detección automática por nombre y contenido):
- Rekordbox: XML de colección (cualquier versión) y BD local de Rekordbox 6 (pyrekordbox)
- Engine DJ: m.db (SQLite)
- Traktor: collection.nml
- VirtualDJ: database.xml
- CSV genérico (Serato y cualquier otra app vía exportación a CSV)
"""

from src.parsers.base import CollectionParser, ParseResult
from src.parsers.csv_parser import CsvCollectionParser
from src.parsers.engine_dj import EngineDjParser
from src.parsers.rekordbox_db import Rekordbox6DatabaseReader
from src.parsers.rekordbox_xml import RekordboxXmlParser
from src.parsers.traktor_nml import TraktorNmlParser
from src.parsers.virtualdj_xml import VirtualDjXmlParser

# El orden importa: los detectores por contenido van antes que el CSV (que acepta por extensión).
FILE_PARSERS: tuple[CollectionParser, ...] = (
    EngineDjParser(),
    RekordboxXmlParser(),
    TraktorNmlParser(),
    VirtualDjXmlParser(),
    CsvCollectionParser(),
)

SUPPORTED_EXTENSIONS: tuple[str, ...] = ("xml", "nml", "db", "csv", "tsv", "txt")


def parse_file(filename: str, data: bytes) -> ParseResult:
    """Elige el parser adecuado según nombre y contenido."""
    head = data[:4096]
    for parser in FILE_PARSERS:
        if parser.can_parse(filename, head):
            return parser.parse(data)
    raise ValueError(
        f"Formato no soportado: '{filename}'. Admitidos: XML de Rekordbox, m.db de Engine DJ, "
        "collection.nml de Traktor, database.xml de VirtualDJ o CSV."
    )


__all__ = [
    "CollectionParser",
    "CsvCollectionParser",
    "EngineDjParser",
    "FILE_PARSERS",
    "ParseResult",
    "Rekordbox6DatabaseReader",
    "RekordboxXmlParser",
    "SUPPORTED_EXTENSIONS",
    "TraktorNmlParser",
    "VirtualDjXmlParser",
    "parse_file",
]
