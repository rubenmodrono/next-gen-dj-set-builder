"""Utilidades compartidas por los parsers: normalización de campos sueltos a UniversalTrack."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.core.energy import estimate_energy_from_bpm
from src.core.keys import to_camelot
from src.core.models import RawSource, TrackSource, UniversalTrack

_DURATION_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_duration_sec(value: Any) -> int | None:
    """Acepta segundos (``392``, ``392.4``) o reloj (``6:32``, ``1:02:03``)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if match := _DURATION_RE.match(text):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        return round(hours * 3600 + minutes * 60 + seconds)
    number = parse_float(text)
    return round(number) if number is not None else None


def normalize_bpm(value: Any) -> float | None:
    """Rekordbox DB guarda BPM×100 (12400 = 124.00)."""
    bpm = parse_float(value)
    if bpm is None or bpm <= 0:
        return None
    return round(bpm / 100.0, 2) if bpm > 1000 else round(bpm, 2)


@dataclass(slots=True)
class TrackAccumulator:
    """Acumula tracks válidos y cuenta los descartados por motivo."""

    source: TrackSource
    tracks: list[UniversalTrack] = field(default_factory=list)
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    energy_estimated: int = 0

    def skip(self, reason: str) -> None:
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1

    @property
    def skipped(self) -> int:
        return sum(self.skipped_reasons.values())

    def warnings(self) -> list[str]:
        return [f"{count} tracks descartados: {reason}." for reason, count in self.skipped_reasons.items()]

    def add(
        self,
        *,
        track_id: Any,
        title: Any,
        artist: Any,
        bpm: Any,
        key: Any,
        duration: Any,
        genre: Any = None,
        energy: Any = None,
        tags: Any = None,
        location: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> UniversalTrack | None:
        bpm_value = normalize_bpm(bpm)
        if bpm_value is None:
            self.skip("sin BPM")
            return None
        camelot = to_camelot(str(key)) if key is not None else None
        if camelot is None:
            self.skip("sin tonalidad reconocible")
            return None
        duration_sec = parse_duration_sec(duration)
        if duration_sec is None or duration_sec <= 0:
            self.skip("sin duración")
            return None

        energy_value = parse_float(energy)
        if energy_value is None:
            energy_value = estimate_energy_from_bpm(bpm_value)
            self.energy_estimated += 1

        title_text = str(title).strip() if title else ""
        try:
            track = UniversalTrack(
                id=str(track_id),
                title=title_text or f"Track {track_id}",
                artist=(str(artist).strip() if artist else "") or "Unknown Artist",
                bpm=bpm_value,
                key=camelot,
                energy=energy_value,
                duration_sec=duration_sec,
                genre=genre,
                tags=tags or (),
                raw_source=RawSource(
                    system=self.source,
                    native_id=str(track_id),
                    location=location,
                    payload=payload or {},
                ),
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            self.skip(f"dato inválido en '{first['loc'][0] if first['loc'] else '?'}'")
            return None
        self.tracks.append(track)
        return track
