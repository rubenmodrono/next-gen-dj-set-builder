"""
Sugerencia de temas reales para el modo propuesta usando un agente de Claude
con búsqueda web (opcional, requiere una API key de Anthropic propia).

A diferencia de Spotify y Last.fm -que solo emparejan por *tag* de género-,
este agente recibe la curva completa de la propuesta (BPM, clave, energía y
tramo de cada slot, en orden) en una sola llamada y busca en la web
(Beatport, 1001Tracklists, Resident Advisor, Spotify, SoundCloud) un tema
real y coherente con esa curva para cada slot, no solo con el género.

Usa la herramienta de búsqueda web integrada de la API de Mensajes de Claude
(https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool,
verificado el 25-09-2026): un bloque ``{"type": "web_search_20250305",
"name": "web_search"}`` en ``tools``, sin que el código tenga que implementar
la búsqueda ni el scraping -los hace el propio modelo, servidor a servidor-.

Tiene coste (tokens del modelo + ~10 USD por cada 1000 búsquedas web), y
requiere que el usuario pegue su propia API key de
https://console.anthropic.com/ en la barra lateral: por eso es opt-in y
nunca se activa por defecto ni comparte esa clave con nada más que la
llamada a la API de Anthropic.
"""

from __future__ import annotations

import json
from typing import Any, Final, Sequence

from src.core.models import UniversalTrack
from src.enrichment.common import ProgressCallback, SuggestionReport

DEFAULT_MODEL: Final[str] = "claude-sonnet-5"
WEB_SEARCH_TOOL: Final[str] = "web_search_20250305"
MAX_SEARCHES: Final[int] = 25
DEFAULT_ALLOWED_DOMAINS: Final[tuple[str, ...]] = (
    "beatport.com",
    "1001tracklists.com",
    "residentadvisor.net",
    "open.spotify.com",
    "soundcloud.com",
)

_SYSTEM_PROMPT = (
    "Eres un digger de música electrónica que ayuda a un DJ a completar un set. "
    "Para cada slot recibirás el género, el tramo del set (warmup/peak_time/closing…), "
    "el BPM objetivo, la clave Camelot objetivo y la energía objetivo (1-10). "
    "Busca en la web (Beatport, 1001Tracklists, Resident Advisor, Spotify, SoundCloud) "
    "un tema REAL, publicado, que encaje con esos parámetros para cada slot -nunca "
    "inventes un artista o título; si no encuentras algo perfecto, elige el tema real más "
    "cercano de ese género y tramo en vez de inventar uno-. No repitas el mismo tema en dos "
    "slots distintos. Responde ÚNICAMENTE con un array JSON, sin texto antes ni después, con "
    "un objeto por slot EN EL MISMO ORDEN en que te los he dado: "
    '[{"artist": "...", "title": "...", "url": "..."}, ...]. '
    'Si de verdad no encuentras nada razonable para un slot, usa {"artist": null, "title": null} '
    "en esa posición, sin saltártela."
)


def _slot_line(track: UniversalTrack, index: int) -> str:
    phase = track.tags[1] if len(track.tags) > 1 else ""
    return (
        f"{index + 1}. género={track.genre or 'cualquiera'} · tramo={phase} · "
        f"bpm={track.bpm:g} · clave={track.key} · energía={track.energy:g}"
    )


def _make_client(api_key: str) -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "El paquete 'anthropic' no está instalado. Instálalo con: pip install -e '.[agent]'"
        ) from exc
    return anthropic.Anthropic(api_key=api_key)


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type", ""))
    return str(getattr(block, "type", "") or "")


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("text", ""))
    return str(getattr(block, "text", "") or "")


def _extract_json_array(text: str) -> list[Any]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("la respuesta del agente no contiene un array JSON reconocible")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("la respuesta del agente no es un array JSON")
    return parsed


def _parse_candidates(picks: Sequence[Any]) -> list[dict[str, str] | None]:
    """Valida cada elemento del array del agente; descarta inventos y repetidos."""
    seen: set[str] = set()
    candidates: list[dict[str, str] | None] = []
    for pick in picks:
        if not isinstance(pick, dict):
            candidates.append(None)
            continue
        artist, title = pick.get("artist"), pick.get("title")
        if not (isinstance(artist, str) and isinstance(title, str) and artist.strip() and title.strip()):
            candidates.append(None)
            continue
        dedupe_key = f"{artist.strip().lower()}::{title.strip().lower()}"
        if dedupe_key in seen:
            candidates.append(None)
            continue
        seen.add(dedupe_key)
        url = pick.get("url")
        candidates.append(
            {"artist": artist.strip(), "title": title.strip(), "url": url.strip() if isinstance(url, str) else ""}
        )
    return candidates


def suggest_tracks_for_proposal_llm(
    placeholders: Sequence[UniversalTrack],
    api_key: str,
    model: str = DEFAULT_MODEL,
    progress: ProgressCallback | None = None,
    client: Any | None = None,
    allowed_domains: Sequence[str] = DEFAULT_ALLOWED_DOMAINS,
) -> tuple[list[UniversalTrack], SuggestionReport]:
    """
    Pide a un modelo de Claude con búsqueda web activada que rellene, en una
    sola llamada, un tema real por slot de la propuesta -coherente con el
    BPM/clave/energía/tramo de cada uno, no solo con el género-. Nunca
    cambia el BPM/clave/energía del slot: solo añade el título, artista y
    enlace reales, o deja el slot como estaba si el agente no encuentra nada
    razonable para él, o si la llamada falla.
    """
    report = SuggestionReport(attempted=len(placeholders), source="Agente IA (búsqueda web)")
    if not placeholders:
        return [], report
    sp = client if client is not None else _make_client(api_key)

    if progress:
        progress(0, len(placeholders), "Preguntando al agente (puede tardar: está buscando en la web)…")

    slots_text = "\n".join(_slot_line(track, i) for i, track in enumerate(placeholders))
    try:
        response = sp.messages.create(
            model=model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "type": WEB_SEARCH_TOOL,
                    "name": "web_search",
                    "max_uses": MAX_SEARCHES,
                    "allowed_domains": list(allowed_domains),
                }
            ],
            messages=[{"role": "user", "content": f"Slots del set ({len(placeholders)}):\n{slots_text}"}],
        )
        text = "\n".join(_block_text(block) for block in response.content if _block_type(block) == "text")
        candidates = _parse_candidates(_extract_json_array(text))
    except Exception as exc:
        report.failed = len(placeholders)
        report.first_error = str(exc)
        return list(placeholders), report

    if progress:
        progress(len(placeholders), len(placeholders), "Agente terminado.")

    suggested: list[UniversalTrack] = []
    for index, track in enumerate(placeholders):
        pick = candidates[index] if index < len(candidates) else None
        if pick is None:
            suggested.append(track)
            continue
        report.suggested += 1
        payload: dict[str, Any] = {
            **track.raw_source.payload,
            "suggested_artist": pick["artist"],
            "suggested_title": pick["title"],
            "suggested_source": report.source,
        }
        if pick["url"]:
            payload["suggested_url"] = pick["url"]
        suggested.append(
            track.model_copy(update={"raw_source": track.raw_source.model_copy(update={"payload": payload})})
        )
    return suggested, report
