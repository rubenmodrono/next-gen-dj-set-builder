"""
Modelos de dominio agnósticos del fabricante.

Ningún componente interno (core, graph, app) debe conocer el formato nativo de
Pioneer, Denon, Native Instruments o Serato: los parsers de ``src/parsers``
traducen cada colección a ``UniversalTrack`` y, a partir de ahí, todo el
sistema trabaja sobre estos modelos.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from src.core.harmonic_engine import TransitionType

CAMELOT_PATTERN: re.Pattern[str] = re.compile(r"^(1[0-2]|[1-9])[AB]$")

HarmonicStrictness = Literal["strict", "energy_boost", "permissive"]
EnergyCurveProfile = Literal["warmup_to_peak", "rollercoaster", "constant"]


class TrackSource(str, Enum):
    """Ecosistema del que procede un track."""

    REKORDBOX = "rekordbox"
    ENGINE_DJ = "engine_dj"
    TRAKTOR = "traktor"
    SERATO = "serato"
    VIRTUALDJ = "virtualdj"
    M3U8 = "m3u8"
    CSV = "csv"
    SYNTHETIC = "synthetic"


class RawSource(BaseModel):
    """
    Referencia opaca al registro original.

    Se conserva para poder exportar de vuelta al formato nativo, pero el core
    nunca lee ``payload``: solo los parsers y exporters lo interpretan.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    system: TrackSource
    native_id: str | None = None
    location: str | None = Field(default=None, description="Ruta o URI del fichero de audio.")
    payload: dict[str, Any] = Field(default_factory=dict)


class UniversalTrack(BaseModel):
    """Track normalizado, independiente del software de origen."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    artist: str = Field(default="Unknown Artist")
    bpm: float = Field(gt=0.0, le=300.0)
    key: str = Field(description="Tonalidad en notación Camelot (1A–12B).")
    energy: float = Field(ge=0.0, le=10.0)
    duration_sec: int = Field(gt=0)
    genre: str | None = None
    tags: tuple[str, ...] = Field(default_factory=tuple)
    raw_source: RawSource = Field(
        default_factory=lambda: RawSource(system=TrackSource.SYNTHETIC)
    )

    @field_validator("key", mode="before")
    @classmethod
    def _normalize_and_validate_key(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError("key debe ser un string en notación Camelot")
        normalized = value.strip().upper()
        if not CAMELOT_PATTERN.fullmatch(normalized):
            raise ValueError(
                f"Clave Camelot inválida: '{value}'. Formato esperado 1A–12A / 1B–12B."
            )
        return normalized

    @field_validator("genre", mode="before")
    @classmethod
    def _normalize_genre(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = [value]
        seen: dict[str, None] = {}
        for tag in value:
            clean = str(tag).strip().lower()
            if clean:
                seen.setdefault(clean, None)
        return tuple(seen)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def camelot_number(self) -> int:
        return int(self.key[:-1])

    @computed_field  # type: ignore[prop-decorator]
    @property
    def camelot_mode(self) -> Literal["A", "B"]:
        return "A" if self.key.endswith("A") else "B"

    @property
    def duration_min(self) -> float:
        return self.duration_sec / 60.0

    def matches_genres(self, genres: list[str]) -> bool:
        """Coincidencia case-insensitive; una lista vacía acepta cualquier género."""
        if not genres:
            return True
        if self.genre is None:
            return False
        wanted = {g.strip().lower() for g in genres}
        return self.genre.lower() in wanted

    def dedupe_key(self) -> str:
        """
        Clave para detectar el mismo tema aunque tenga un ``id`` distinto.

        Las bibliotecas de DJ acumulan duplicados reales: el mismo archivo
        importado dos veces recibe un TrackID distinto en cada copia. Con
        ruta de archivo, dos tracks son el mismo tema si apuntan al mismo
        fichero; sin ruta, se comparan título, artista y BPM redondeado.
        """
        location = self.raw_source.location
        if location:
            return f"loc:{location.strip().lower()}"
        return f"meta:{self.title.strip().lower()}|{self.artist.strip().lower()}|{round(self.bpm)}"

    def __hash__(self) -> int:
        return hash((self.raw_source.system, self.id))


class PhaseSpec(BaseModel):
    """Tramo del set: peso relativo en la duración y rango de energía objetivo."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    weight: float = Field(gt=0.0, le=100.0, description="Peso relativo; se normaliza.")
    energy_min: float = Field(ge=0.0, le=10.0)
    energy_max: float = Field(ge=0.0, le=10.0)

    @model_validator(mode="after")
    def _check_energy_range(self) -> PhaseSpec:
        if self.energy_min > self.energy_max:
            raise ValueError(
                f"Tramo '{self.name}': energy_min ({self.energy_min}) > energy_max ({self.energy_max})"
            )
        return self


class SetConstraint(BaseModel):
    """Parámetros que el DJ define para el set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_duration_min: int = Field(gt=0, le=720)
    target_genres: list[str] = Field(default_factory=list)
    bpm_min: float | None = Field(default=None, gt=0.0, le=300.0)
    bpm_max: float | None = Field(default=None, gt=0.0, le=300.0)
    harmonic_strictness: HarmonicStrictness = "energy_boost"
    energy_curve_profile: EnergyCurveProfile = "warmup_to_peak"
    energy_phases: tuple[PhaseSpec, ...] | None = Field(
        default=None,
        description="Tramos personalizados; si se indican, sustituyen al perfil.",
    )
    start_key: str | None = Field(
        default=None,
        description="Clave Camelot de arranque para el modo propuesta (sin colección).",
    )
    avg_track_duration_min: float | None = Field(
        default=None,
        gt=0.5,
        le=20.0,
        description="Minutos efectivos por tema; None = mediana de la colección.",
    )

    @field_validator("target_genres", mode="before")
    @classmethod
    def _clean_genres(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(g).strip() for g in value if str(g).strip()]

    @model_validator(mode="after")
    def _check_bpm_range(self) -> SetConstraint:
        if self.bpm_min is not None and self.bpm_max is not None and self.bpm_min > self.bpm_max:
            raise ValueError(
                f"bpm_min ({self.bpm_min}) no puede ser mayor que bpm_max ({self.bpm_max})"
            )
        return self

    @field_validator("start_key", mode="before")
    @classmethod
    def _validate_start_key(cls, value: Any) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        normalized = str(value).strip().upper()
        if not CAMELOT_PATTERN.fullmatch(normalized):
            raise ValueError(f"start_key inválida: '{value}'. Formato esperado 1A–12B.")
        return normalized

    @field_validator("energy_phases")
    @classmethod
    def _check_phases(
        cls, value: tuple[PhaseSpec, ...] | None
    ) -> tuple[PhaseSpec, ...] | None:
        if value is not None and len(value) == 0:
            raise ValueError("energy_phases no puede estar vacío; usa None para el perfil")
        return value

    @property
    def total_duration_sec(self) -> int:
        return self.total_duration_min * 60


class TransitionEvaluation(BaseModel):
    """Resultado de evaluar la mezcla Track_n → Track_n+1 (peso de arista del grafo)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_track_id: str
    to_track_id: str
    cost: float = Field(ge=0.0)
    transition_type: TransitionType
    bpm_delta: float = Field(description="BPM destino − BPM origen (con half/double-time resuelto).")
    bpm_delta_pct: float = Field(ge=0.0, description="Pitch necesario en % respecto al origen.")
    energy_delta: float
    is_valid: bool
