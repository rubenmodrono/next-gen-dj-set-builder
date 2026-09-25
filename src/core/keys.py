"""
Conversión de tonalidades a notación Camelot.

Acepta:
- Camelot: ``8A``, ``12b``
- Open Key (Traktor): ``1m``, ``6d``
- Clásica: ``Am``, ``F#m``, ``Bb``, ``C# minor``, ``Ebmaj``, ``G♯m``
- Pitch class + modo (Spotify): ``pitch_class_to_camelot(9, minor=True)``

La posición en la rueda se calcula por círculo de quintas en lugar de con una
tabla escrita a mano, así que todos los enarmónicos (G# = Ab, etc.) salen bien.
"""

from __future__ import annotations

import re
from typing import Final

_CAMELOT_RE: Final[re.Pattern[str]] = re.compile(r"^(1[0-2]|[1-9])\s*([ABab])$")
_OPEN_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^(1[0-2]|[1-9])\s*([mdMD])$")
_CLASSIC_RE: Final[re.Pattern[str]] = re.compile(
    r"^([A-Ga-g])\s*([#♯b♭]?)\s*(m|min|minor|maj|major|M)?$"
)

_NATURAL_PITCH: Final[dict[str, int]] = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}


def _wheel_number(value: int) -> int:
    number = value % 12
    return 12 if number == 0 else number


def pitch_class_to_camelot(pitch_class: int, minor: bool) -> str:
    """
    Pitch class (0 = C … 11 = B) + modo → Camelot.

    Mayor: C = 8B y cada quinta suma 1 → ``8 + 7·pc``.
    Menor: la relativa mayor está 3 semitonos arriba → ``5 + 7·pc``.
    """
    if not 0 <= pitch_class <= 11:
        raise ValueError(f"pitch_class fuera de rango: {pitch_class}")
    if minor:
        return f"{_wheel_number(5 + 7 * pitch_class)}A"
    return f"{_wheel_number(8 + 7 * pitch_class)}B"


def camelot_to_pitch_class(key: str) -> tuple[int, int]:
    """
    Camelot → (pitch class 0–11, modo: 1 = mayor, 0 = menor), como espera la
    API de Spotify. Inversa exacta de ``pitch_class_to_camelot``.
    """
    match = _CAMELOT_RE.match(key.strip())
    if not match:
        raise ValueError(f"Clave Camelot inválida: '{key}'")
    number = int(match.group(1))
    if match.group(2).upper() == "B":
        return (7 * (number - 8)) % 12, 1
    return (7 * (number - 5)) % 12, 0


def to_camelot(value: str | None) -> str | None:
    """Normaliza cualquier notación soportada a Camelot; ``None`` si no se reconoce."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    if match := _CAMELOT_RE.match(text):
        return f"{int(match.group(1))}{match.group(2).upper()}"

    if match := _OPEN_KEY_RE.match(text):
        number = _wheel_number(int(match.group(1)) + 7)
        mode = "A" if match.group(2).lower() == "m" else "B"
        return f"{number}{mode}"

    if match := _CLASSIC_RE.match(text):
        letter, accidental, quality = match.groups()
        pitch = _NATURAL_PITCH[letter.upper()]
        if accidental in ("#", "♯"):
            pitch += 1
        elif accidental in ("b", "♭"):
            pitch -= 1
        minor = quality is not None and quality.lower() in ("m", "min", "minor") and quality != "M"
        return pitch_class_to_camelot(pitch % 12, minor)

    return None
