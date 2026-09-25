"""
Sugerencia de temas reales para el modo propuesta usando Last.fm (opcional).

Alternativa a Spotify: Last.fm no exige aprobación ni cuota especial -la
``api_key`` se obtiene al instante y gratis en
https://www.last.fm/api/account/create-, y su sistema de tags cubre
microgéneros electrónicos ("tech house", "melodic techno"…) tan bien como
Spotify o mejor.

Usa ``tag.getTopTracks`` (https://www.last.fm/api/show/tag.getTopTracks):
para un tag de género, devuelve los temas más etiquetados con él, ordenados
por peso del tag. Un único endpoint, sin autenticación de usuario, sin el
paso adicional de artistas que hace falta en Spotify. Verificado contra la
documentación oficial el 25-09-2026: parámetros ``tag`` + ``api_key``
(requeridos), ``limit``/``page`` (opcionales); respuesta
``{"tracks": {"track": [{"name", "artist": {"name", ...}, "url", ...}]}}``.

Igual que con Spotify: no filtra por tempo ni tonalidad, así que la
sugerencia es un tema real del género correcto, no uno verificado nota a
nota contra el BPM del slot. El BPM, la clave y la energía del slot -los que
respetan la curva y la ruta armónica- nunca cambian.
"""

from __future__ import annotations

from typing import Any, Callable, Final, Sequence

from src.core.models import UniversalTrack
from src.enrichment.common import ProgressCallback, SuggestionReport, assign_candidates, search_query_terms

LASTFM_API_URL: Final[str] = "http://ws.audioscrobbler.com/2.0/"
LASTFM_PAGE: Final[int] = 50
LASTFM_MAX_PAGES_PER_TERM: Final[int] = 4

LastfmCall = Callable[..., dict[str, Any]]


def _make_client(api_key: str) -> LastfmCall:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "requests no está instalado. Instálalo con: pip install -e '.[lastfm]'"
        ) from exc

    def call(method: str, **params: str) -> dict[str, Any]:
        response = requests.get(
            LASTFM_API_URL,
            params={"method": method, "api_key": api_key, "format": "json", **params},
            timeout=10,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if "error" in data:
            raise RuntimeError(f"Last.fm: {data.get('message', 'error desconocido')} (código {data['error']})")
        return data

    return call


def _tracks_for_tag(call: LastfmCall, tag: str, page: int) -> list[dict[str, Any]]:
    data = call("tag.gettoptracks", tag=tag, limit=str(LASTFM_PAGE), page=str(page))
    items = (data.get("tracks") or {}).get("track") or []
    if isinstance(items, dict):
        # Last.fm devuelve un objeto suelto, no una lista, cuando solo hay un resultado.
        items = [items]
    return list(items)


def _track_from_item(item: dict[str, Any]) -> tuple[str, dict[str, str]] | None:
    title = item.get("name")
    artist = (item.get("artist") or {}).get("name")
    if not (title and artist):
        return None
    key = f"{artist.strip().lower()}::{title.strip().lower()}"
    return key, {"artist": artist, "title": title, "url": item.get("url", "")}


def _search_candidates(
    call: LastfmCall, terms: Sequence[str], needed: int, progress: ProgressCallback | None
) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for term in terms:
        if len(seen) >= needed:
            break
        for page in range(1, LASTFM_MAX_PAGES_PER_TERM + 1):
            if len(seen) >= needed:
                break
            if progress:
                progress(min(len(seen) + 1, needed), needed, f"Buscando temas de {term} en Last.fm…")
            items = _tracks_for_tag(call, term, page)
            if not items:
                break
            for item in items:
                if len(seen) >= needed:
                    break
                parsed = _track_from_item(item)
                if parsed and parsed[0] not in seen:
                    seen[parsed[0]] = parsed[1]
    return list(seen.values())[:needed]


def suggest_tracks_for_proposal_lastfm(
    placeholders: Sequence[UniversalTrack],
    genres: Sequence[str],
    api_key: str,
    progress: ProgressCallback | None = None,
    client: LastfmCall | None = None,
) -> tuple[list[UniversalTrack], SuggestionReport]:
    """
    Busca, para cada término de género, los temas más etiquetados con ese tag
    en Last.fm y sustituye el nombre/artista de cada marcador por uno real y
    distinto. Nunca cambia el BPM/clave/energía del slot: solo añade el
    título, artista y enlace reales al ``payload`` del marcador. Si no hay
    bastantes temas distintos, o la llamada falla, los slots restantes
    conservan su marcador sintético tal cual.
    """
    report = SuggestionReport(attempted=len(placeholders), source="Last.fm")
    if not placeholders:
        return [], report
    call = client if client is not None else _make_client(api_key)
    terms = search_query_terms(genres)

    try:
        candidates = _search_candidates(call, terms, len(placeholders), progress)
    except Exception as exc:
        report.failed = len(placeholders)
        report.first_error = str(exc)
        return list(placeholders), report

    return assign_candidates(placeholders, candidates, report), report
