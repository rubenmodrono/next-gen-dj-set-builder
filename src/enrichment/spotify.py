"""
Enriquecimiento de energía y tonalidad, y sugerencia de temas reales, con
Spotify (opcional).

AVISO sobre ``audio-features`` (modo colección, ``enrich_with_spotify``):
Spotify retiró este endpoint el 27-11-2024. Solo responden las apps que tenían
(o habían pedido) una ampliación de cuota antes de esa fecha; el resto recibe
403 y no hay sustituto oficial. Por eso el fallo NUNCA es silencioso: el
informe cuenta cuántos temas se quedan sin datos reales y guarda el primer
error.

La sugerencia de temas reales para el modo propuesta (``suggest_tracks_for_
proposal``) NO usa ``audio-features`` ni ``recommendations`` -ambos con la
misma restricción-. Tampoco busca el género como texto libre contra el
título/artista de la canción (``/v1/search?type=track&q=<texto>``): un track
de Spotify no lleva género como campo, así que ese texto libre solo
encuentra temas cuyo título o artista *contiene literalmente* la palabra del
género, que en la práctica es casi ninguno.

En su lugar usa el filtro de campo ``genre:"..."`` de la búsqueda de Spotify
-que, según la documentación oficial
(https://developer.spotify.com/documentation/web-api/reference/search),
funciona tanto en ``type=artist`` como en ``type=track``, verificado el
25-09-2026-:

1. Primero busca temas directamente con ``/v1/search?type=track&
   q=genre:"..."``: un único filtro, real y del género correcto.
2. Si eso no reúne bastantes temas distintos (género poco tageado, término
   no reconocido…), recurre a buscar **artistas** con ese mismo filtro
   (``type=artist``) y coge los temas más escuchados de cada uno
   (``/v1/artists/{id}/top-tracks``), como red de seguridad.

Ninguno de estos tres endpoints está restringido por el cambio de cuota del
27-11-2024, así que todo esto funciona con credenciales de Spotify normales,
sin necesitar una app antigua con cuota ampliada. El precio es que ninguno
filtra por tempo o tonalidad: la canción sugerida es real y del género
correcto, pero no está verificada nota a nota contra el BPM del slot; el
BPM, la clave y la energía del slot -los que respetan la curva y la ruta
armónica- nunca cambian.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Final, Sequence

from src.core.keys import pitch_class_to_camelot
from src.core.models import UniversalTrack

FEATURES_BATCH: Final[int] = 100
SEARCH_PAGE: Final[int] = 50
SEARCH_MAX_PAGES_PER_TERM: Final[int] = 4
ProgressCallback = Callable[[int, int, str], None]

# Subconjunto de géneros conocidos por Spotify más cercano a cada género
# interno, usado como término de búsqueda de reserva cuando el género tal
# cual lo escribió el usuario no encuentra temas etiquetados con él.
# Spotify etiqueta con microgéneros bastante literales (p. ej. "tech house"
# existe tal cual), así que el texto del usuario suele bastar.
GENRE_SEED_OVERRIDES: Final[dict[str, str]] = {
    "downtempo": "chill",
    "disco": "disco",
    "nu disco": "disco",
    "deep house": "deep-house",
    "afro house": "house",
    "house": "house",
    "organic house": "house",
    "melodic house & techno": "techno",
    "melodic techno": "techno",
    "progressive house": "progressive-house",
    "tech house": "house",
    "minimal": "minimal-techno",
    "breaks": "breakbeat",
    "techno": "techno",
    "peak time techno": "techno",
    "trance": "trance",
    "psytrance": "trance",
    "dubstep": "dubstep",
    "hard techno": "techno",
    "hardstyle": "hardstyle",
    "drum and bass": "drum-and-bass",
    "drum & bass": "drum-and-bass",
    "dnb": "drum-and-bass",
}
DEFAULT_SEED_GENRE: Final[str] = "electronic"


def seed_genre(genres: Sequence[str]) -> str:
    """El primer género reconocido de la lista, o un valor genérico por defecto."""
    for genre in genres:
        mapped = GENRE_SEED_OVERRIDES.get(genre.strip().lower())
        if mapped:
            return mapped
    return DEFAULT_SEED_GENRE


@dataclass(slots=True)
class EnrichmentReport:
    attempted: int = 0
    enriched: int = 0
    not_found: int = 0
    failed: int = 0
    first_error: str = ""

    @property
    def fell_back(self) -> int:
        """Tracks que siguen con la energía/tonalidad de origen."""
        return self.attempted - self.enriched

    def summary(self) -> str:
        text = (
            f"Spotify: {self.enriched}/{self.attempted} temas enriquecidos, "
            f"{self.not_found} no encontrados, {self.failed} con error. "
            f"{self.fell_back} usan la estimación por BPM."
        )
        if self.first_error:
            text += f" Primer error: {self.first_error}"
        return text


def _make_client(client_id: str, client_secret: str) -> Any:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError as exc:
        raise RuntimeError(
            "spotipy no está instalado. Instálalo con: pip install -e '.[spotify]'"
        ) from exc
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret),
        requests_timeout=10,
        retries=1,
    )


def enrich_with_spotify(
    tracks: Sequence[UniversalTrack],
    client_id: str,
    client_secret: str,
    progress: ProgressCallback | None = None,
    client: Any | None = None,
) -> tuple[list[UniversalTrack], EnrichmentReport]:
    """
    Busca cada track en Spotify y sustituye energía (0–1 → 0–10) y tonalidad.
    Devuelve SIEMPRE la lista completa: los que fallan quedan como estaban.
    """
    report = EnrichmentReport(attempted=len(tracks))
    sp = client if client is not None else _make_client(client_id, client_secret)

    spotify_ids: dict[str, str] = {}
    for index, track in enumerate(tracks, start=1):
        if progress:
            progress(index, len(tracks), f"Buscando {track.artist} – {track.title}")
        try:
            result = sp.search(q=f"track:{track.title} artist:{track.artist}", type="track", limit=1)
        except Exception as exc:
            report.failed += 1
            report.first_error = report.first_error or str(exc)
            continue
        items = (result or {}).get("tracks", {}).get("items", [])
        if items:
            spotify_ids[track.id] = items[0]["id"]
        else:
            report.not_found += 1

    features_by_track: dict[str, dict[str, Any]] = {}
    pending = list(spotify_ids.items())
    for start in range(0, len(pending), FEATURES_BATCH):
        chunk = pending[start : start + FEATURES_BATCH]
        try:
            features = sp.audio_features([sid for _, sid in chunk]) or []
        except Exception as exc:
            # Típicamente 403 para apps creadas después del 27-11-2024: no insistir.
            report.failed += len(pending) - start
            report.first_error = report.first_error or str(exc)
            break
        for (track_id, _), feature in zip(chunk, features):
            if feature:
                features_by_track[track_id] = feature
            else:
                report.not_found += 1

    enriched: list[UniversalTrack] = []
    for track in tracks:
        feature = features_by_track.get(track.id)
        if feature is None:
            enriched.append(track)
            continue
        update: dict[str, Any] = {}
        energy = feature.get("energy")
        if isinstance(energy, (int, float)):
            update["energy"] = round(min(max(float(energy) * 10.0, 0.0), 10.0), 2)
        key, mode = feature.get("key"), feature.get("mode")
        if isinstance(key, int) and 0 <= key <= 11 and mode in (0, 1):
            update["key"] = pitch_class_to_camelot(key, minor=mode == 0)
        if update:
            report.enriched += 1
            enriched.append(track.model_copy(update=update))
        else:
            enriched.append(track)
    return enriched, report


@dataclass(slots=True)
class SuggestionReport:
    attempted: int = 0
    suggested: int = 0
    failed: int = 0
    first_error: str = ""

    @property
    def fell_back(self) -> int:
        """Slots que se quedan solo con el marcador BPM/clave/energía."""
        return self.attempted - self.suggested

    def summary(self) -> str:
        text = (
            f"Spotify: {self.suggested}/{self.attempted} slots con una canción real sugerida. "
            f"{self.fell_back} se quedan con la búsqueda por parámetros (BPM/clave/energía)."
        )
        if self.first_error:
            text += f" Primer error: {self.first_error}"
        return text


def _search_query_terms(genres: Sequence[str], seed: str) -> list[str]:
    """
    Términos a probar en orden: primero los géneros tal cual los escribió el
    usuario (más específicos), luego el género genérico mapeado como reserva.
    """
    terms = [g.strip() for g in genres if g.strip()]
    fallback = seed.replace("-", " ")
    if fallback.lower() not in (t.lower() for t in terms):
        terms.append(fallback)
    return terms


def _track_from_item(item: dict[str, Any]) -> tuple[str, dict[str, str]] | None:
    track_id = item.get("id")
    title = item.get("name")
    artists = ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name"))
    if not (track_id and title and artists):
        return None
    return track_id, {
        "artist": artists,
        "title": title,
        "url": item.get("external_urls", {}).get("spotify", ""),
    }


def _tracks_by_genre_filter(
    sp: Any, terms: Sequence[str], needed: int, seen: dict[str, dict[str, str]], progress: ProgressCallback | None
) -> None:
    """
    Vía principal: ``/v1/search?type=track&q=genre:"..."``. El filtro
    ``genre`` está documentado para ``type=track``, no solo para artistas
    (verificado contra la referencia oficial de Spotify).
    """
    for term in terms:
        if len(seen) >= needed:
            break
        for page in range(SEARCH_MAX_PAGES_PER_TERM):
            if len(seen) >= needed:
                break
            if progress:
                progress(min(len(seen) + 1, needed), needed, f"Buscando temas de {term}…")
            result = sp.search(q=f'genre:"{term}"', type="track", limit=SEARCH_PAGE, offset=page * SEARCH_PAGE)
            items = (result or {}).get("tracks", {}).get("items", []) or []
            if not items:
                break
            for item in items:
                if len(seen) >= needed:
                    break
                parsed = _track_from_item(item)
                if parsed and parsed[0] not in seen:
                    seen[parsed[0]] = parsed[1]


def _tracks_by_artist_top_tracks(
    sp: Any, terms: Sequence[str], needed: int, seen: dict[str, dict[str, str]], progress: ProgressCallback | None
) -> None:
    """
    Red de seguridad si la vía principal no reúne bastantes temas: busca
    artistas con el mismo filtro ``genre:"..."`` (``type=artist``, también
    documentado) y coge los temas más escuchados de cada uno
    (``/v1/artists/{id}/top-tracks``). Un artista sin top-tracks disponible
    simplemente se salta, sin abortar la búsqueda.
    """
    seen_artists: set[str] = set()
    for term in terms:
        if len(seen) >= needed:
            break
        for page in range(SEARCH_MAX_PAGES_PER_TERM):
            if len(seen) >= needed:
                break
            result = sp.search(q=f'genre:"{term}"', type="artist", limit=SEARCH_PAGE, offset=page * SEARCH_PAGE)
            artists = (result or {}).get("artists", {}).get("items", []) or []
            if not artists:
                break
            for artist in artists:
                if len(seen) >= needed:
                    break
                artist_id = artist.get("id")
                if not artist_id or artist_id in seen_artists:
                    continue
                seen_artists.add(artist_id)
                if progress:
                    progress(
                        min(len(seen) + 1, needed), needed, f"Buscando temas de {artist.get('name') or term}…"
                    )
                try:
                    top = sp.artist_top_tracks(artist_id) or {}
                except Exception:
                    continue
                for item in top.get("tracks", []) or []:
                    if len(seen) >= needed:
                        break
                    parsed = _track_from_item(item)
                    if parsed and parsed[0] not in seen:
                        seen[parsed[0]] = parsed[1]


def _search_candidates(
    sp: Any, terms: Sequence[str], needed: int, progress: ProgressCallback | None
) -> list[dict[str, str]]:
    """Hasta ``needed`` temas reales y distintos del género, con la vía principal y, si hace falta, la de reserva."""
    seen: dict[str, dict[str, str]] = {}
    _tracks_by_genre_filter(sp, terms, needed, seen, progress)
    if len(seen) < needed:
        _tracks_by_artist_top_tracks(sp, terms, needed, seen, progress)
    return list(seen.values())[:needed]


def suggest_tracks_for_proposal(
    placeholders: Sequence[UniversalTrack],
    genres: Sequence[str],
    client_id: str,
    client_secret: str,
    progress: ProgressCallback | None = None,
    client: Any | None = None,
) -> tuple[list[UniversalTrack], SuggestionReport]:
    """
    Busca artistas reales del género de la propuesta y coge sus temas más
    escuchados, para sustituir el nombre y artista de cada marcador por uno
    real y distinto. Nunca cambia el BPM/clave/energía del slot (son los que
    respetan la curva y la ruta armónica): solo añade el título, artista y
    enlace reales al ``payload`` del marcador. Si no hay bastantes temas
    distintos para cubrir todos los slots, o la búsqueda falla, los slots
    restantes conservan su marcador sintético tal cual.
    """
    report = SuggestionReport(attempted=len(placeholders))
    if not placeholders:
        return [], report
    sp = client if client is not None else _make_client(client_id, client_secret)
    terms = _search_query_terms(genres, seed_genre(genres))

    try:
        candidates = _search_candidates(sp, terms, len(placeholders), progress)
    except Exception as exc:
        # P. ej. credenciales inválidas o un fallo de red: no insistir, todos
        # los slots se quedan con el marcador sintético.
        report.failed = len(placeholders)
        report.first_error = str(exc)
        return list(placeholders), report

    suggested: list[UniversalTrack] = []
    for index, track in enumerate(placeholders):
        if index >= len(candidates):
            suggested.append(track)
            continue
        pick = candidates[index]
        report.suggested += 1
        payload = {**track.raw_source.payload, "spotify_artist": pick["artist"], "spotify_title": pick["title"]}
        if pick["url"]:
            payload["spotify_url"] = pick["url"]
        suggested.append(
            track.model_copy(
                update={"raw_source": track.raw_source.model_copy(update={"payload": payload})}
            )
        )
    return suggested, report
