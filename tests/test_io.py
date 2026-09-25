from __future__ import annotations

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.keys import camelot_to_pitch_class, pitch_class_to_camelot, to_camelot
from src.enrichment.spotify import enrich_with_spotify, suggest_tracks_for_proposal
from src.exporters import set_rows, to_csv, to_m3u8, to_rekordbox_xml
from src.graph.nodes import parse_collection_node
from src.graph.state import initial_state
from src.parsers import parse_file
from src.parsers.rekordbox_db import content_to_fields
from src.parsers.rekordbox_xml import location_to_path
from tests.conftest import make_track

RB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.8.5" Company="AlphaTheta"/>
  <COLLECTION Entries="4">
    <TRACK TrackID="1" Name="Night Drive" Artist="A" Genre="Tech House" TotalTime="392"
           AverageBpm="124.00" Tonality="Am" Location="file://localhost/Users/me/Music/Night%20Drive.aiff"/>
    <TRACK TrackID="2" Name="Sunrise" Artist="B" Genre="Tech House" TotalTime="410"
           AverageBpm="126.00" Tonality="9A" Location="file://localhost/C:/Music/Sunrise.mp3"/>
    <TRACK TrackID="3" Name="No Key" Artist="C" Genre="Techno" TotalTime="300" AverageBpm="130.00" Tonality=""/>
    <TRACK TrackID="4" Name="G sharp" Artist="D" Genre="Techno" TotalTime="300" AverageBpm="131.00" Tonality="G#"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="1">
      <NODE Type="0" Name="Gigs" Count="1">
        <NODE Name="Friday" Type="1" KeyType="0" Entries="3">
          <TRACK Key="2"/><TRACK Key="1"/><TRACK Key="3"/>
        </NODE>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Am", "8A"), ("C", "8B"), ("G#", "4B"), ("Abm", "1A"), ("F#m", "11A"), ("Bb", "6B"),
     ("8a", "8A"), ("1m", "8A"), ("6d", "1B"), ("C# minor", "12A"), ("", None), ("xx", None)],
)
def test_key_conversion(raw: str, expected: str | None) -> None:
    assert to_camelot(raw) == expected


def test_pitch_class_wheel_is_complete() -> None:
    keys = {pitch_class_to_camelot(pc, m) for pc in range(12) for m in (True, False)}
    assert len(keys) == 24


@pytest.mark.parametrize("number", range(1, 13))
@pytest.mark.parametrize("letter", ["A", "B"])
def test_camelot_to_pitch_class_round_trip(number: int, letter: str) -> None:
    """Inversa exacta: Camelot → pitch class/modo → Camelot debe devolver la misma clave."""
    camelot = f"{number}{letter}"
    pitch_class, mode = camelot_to_pitch_class(camelot)
    assert 0 <= pitch_class <= 11
    assert mode in (0, 1)
    assert pitch_class_to_camelot(pitch_class, minor=mode == 0) == camelot


def test_camelot_to_pitch_class_invalid() -> None:
    with pytest.raises(ValueError, match="Clave Camelot inválida"):
        camelot_to_pitch_class("Am")


def test_rekordbox_xml_parser() -> None:
    result = parse_file("collection.xml", RB_XML)
    assert [t.id for t in result.tracks] == ["1", "2", "4"]
    assert result.tracks[0].key == "8A" and result.tracks[2].key == "4B"
    assert result.tracks[0].raw_source.location == "/Users/me/Music/Night Drive.aiff"
    assert result.tracks[1].raw_source.location == "C:/Music/Sunrise.mp3"
    assert result.skipped == 1 and result.energy_estimated == 3
    assert result.playlists == {"Gigs / Friday": ["2", "1"]}
    assert result.genres == ["Tech House", "Techno"]


def test_location_to_path_passthrough() -> None:
    assert location_to_path(None) is None
    assert location_to_path("/plain/path.mp3") == "/plain/path.mp3"


def test_csv_parser_spanish_semicolon() -> None:
    data = (
        "Título;Artista;BPM;Tonalidad;Duración;Género;Energía\n"
        "Uno;X;124,5;Am;6:30;Techno;7\n"
        "Dos;Y;;Am;6:30;Techno;\n"
        "Tres;Z;128;F#m;400;Techno;\n"
    ).encode()
    result = parse_file("set.csv", data)
    assert [t.title for t in result.tracks] == ["Uno", "Tres"]
    assert result.tracks[0].bpm == 124.5 and result.tracks[0].duration_sec == 390
    assert result.tracks[0].energy == 7.0
    assert result.energy_estimated == 1 and result.skipped == 1


def test_csv_parser_missing_columns() -> None:
    with pytest.raises(ValueError, match="Faltan columnas"):
        parse_file("x.csv", b"title,artist\nA,B\n")


def test_unsupported_file() -> None:
    with pytest.raises(ValueError, match="Formato no soportado"):
        parse_file("x.mp3", b"ID3")


def test_rekordbox_db_content_mapping() -> None:
    content = SimpleNamespace(
        ID=77, Title="T", BPM=12400, Length=380, FolderPath="/m/t.mp3",
        Key=SimpleNamespace(ScaleName="Fm"), Genre=SimpleNamespace(Name="Techno"),
        Artist=SimpleNamespace(Name="Art"),
    )
    fields = content_to_fields(content)
    assert fields["key"] == "Fm" and fields["artist"] == "Art" and fields["genre"] == "Techno"
    assert fields["bpm"] == 12400


class FakeSpotify:
    def __init__(self, fail_features: bool) -> None:
        self.fail_features = fail_features

    def search(self, q: str, type: str, limit: int) -> dict[str, Any]:
        if "missing" in q:
            return {"tracks": {"items": []}}
        return {"tracks": {"items": [{"id": "sp-" + q}]}}

    def audio_features(self, ids: list[str]) -> list[dict[str, Any]]:
        if self.fail_features:
            raise RuntimeError("http status: 403")
        return [{"energy": 0.83, "key": 9, "mode": 0} for _ in ids]


def test_spotify_enrichment_success() -> None:
    tracks = [make_track("a", key="1A", energy=3.0), make_track("missing", key="1A")]
    tracks[1] = tracks[1].model_copy(update={"title": "missing"})
    out, report = enrich_with_spotify(tracks, "", "", client=FakeSpotify(False))
    assert out[0].energy == 8.3 and out[0].key == "8A"
    assert out[1] == tracks[1]
    assert report.enriched == 1 and report.not_found == 1 and report.fell_back == 1


def test_spotify_403_is_reported_not_silent() -> None:
    tracks = [make_track("a"), make_track("b")]
    out, report = enrich_with_spotify(tracks, "", "", client=FakeSpotify(True))
    assert out == tracks
    assert report.failed == 2 and "403" in report.first_error
    assert "2 usan la estimación por BPM" in report.summary()


def test_exports() -> None:
    parsed = parse_file("collection.xml", RB_XML).tracks
    no_path = make_track("np")
    tracks = [*parsed[:2], no_path]
    m3u, missing = to_m3u8(tracks, "Friday")
    assert missing == 1 and "/Users/me/Music/Night Drive.aiff" in m3u and m3u.startswith("#EXTM3U")

    xml, missing_xml = to_rekordbox_xml(tracks, "Friday")
    assert missing_xml == 1
    root = ET.fromstring(xml.split("\n", 1)[1])
    locations = [t.get("Location") for t in root.iterfind("./COLLECTION/TRACK")]
    assert locations == [
        "file://localhost/Users/me/Music/Night%20Drive.aiff",
        "file://localhost/C:/Music/Sunrise.mp3",
    ]
    assert [t.get("Key") for t in root.iterfind(".//NODE[@Name='Friday']/TRACK")] == ["1", "2"]
    # Ida y vuelta: el XML exportado se vuelve a leer igual.
    assert [t.title for t in parse_file("x.xml", xml.encode()).tracks] == ["Night Drive", "Sunrise"]

    csv_text = to_csv(set_rows(tracks, [], []))
    assert csv_text.splitlines()[0].startswith("position,phase,artist")
    assert len(csv_text.splitlines()) == 4


NML = b"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19"><COLLECTION ENTRIES="2">
<ENTRY TITLE="Deep One" ARTIST="T1"><LOCATION DIR="/:Users/:me/:Music/:" FILE="deep.mp3" VOLUME="Macintosh HD"/>
<INFO GENRE="Techno" PLAYTIME="400" KEY="1m"/><TEMPO BPM="130.000"/><MUSICAL_KEY VALUE="21"/></ENTRY>
<ENTRY TITLE="Win Track" ARTIST="T2"><LOCATION DIR="/:Music/:" FILE="w.mp3" VOLUME="C:"/>
<INFO GENRE="Techno" PLAYTIME="380" KEY="6d"/><TEMPO BPM="131.000"/></ENTRY>
</COLLECTION><PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="1">
<NODE TYPE="PLAYLIST" NAME="Sat"><PLAYLIST ENTRIES="1" TYPE="LIST">
<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="C:/:Music/:w.mp3"/></ENTRY></PLAYLIST></NODE>
</SUBNODES></NODE></PLAYLISTS></NML>"""

VDJ = b"""<?xml version="1.0" encoding="UTF-8"?>
<VirtualDJ_Database Version="2024">
<Song FilePath="D:\\Music\\a.mp3" FileSize="1"><Tags Author="V" Title="VA" Genre="House" Key="Am"/>
<Infos SongLength="360.5"/><Scan Bpm="0.483871" Key="Am"/></Song>
<Song FilePath="D:\\Music\\b.mp3"><Tags Author="V" Title="No bpm" Key="C"/><Infos SongLength="300"/></Song>
</VirtualDJ_Database>"""


def test_traktor_nml_parser() -> None:
    result = parse_file("collection.nml", NML)
    first, second = result.tracks
    assert first.key == "8A"  # MUSICAL_KEY 21 → 21-12 = 9 → A minor
    assert first.raw_source.location == "/Users/me/Music/deep.mp3"
    assert second.key == "1B" and second.raw_source.location == "C:/Music/w.mp3"
    assert result.playlists == {"Sat": ["C:/:Music/:w.mp3"]}


def test_virtualdj_parser() -> None:
    result = parse_file("database.xml", VDJ)
    assert [t.title for t in result.tracks] == ["VA"]
    assert result.tracks[0].bpm == 124.0 and result.tracks[0].key == "8A"
    assert result.tracks[0].duration_sec == 360 and result.skipped == 1


def _make_engine_db(path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE Track (id INTEGER PRIMARY KEY, title TEXT, artist TEXT, bpm REAL,
                            bpmAnalyzed REAL, key INTEGER, length INTEGER, genre TEXT, path TEXT);
        INSERT INTO Track VALUES (1,'E1','X',124,124.0,1,390,'House','../Music/e1.mp3');
        INSERT INTO Track VALUES (2,'E2','Y',126,126.0,23,400,'House','../Music/e2.mp3');
        INSERT INTO Track VALUES (3,'E3','Z',126,126.0,NULL,400,'House','../Music/e3.mp3');
        CREATE TABLE Playlist (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE PlaylistEntity (id INTEGER PRIMARY KEY, listId INTEGER, trackId INTEGER, nextEntityId INTEGER);
        INSERT INTO Playlist VALUES (1, 'Warm');
        INSERT INTO PlaylistEntity VALUES (10, 1, 2, 11), (11, 1, 1, 0);
        """
    )
    con.commit()
    con.close()


def test_engine_dj_parser(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "m.db"
    _make_engine_db(db)
    result = parse_file("m.db", db.read_bytes())
    assert [(t.id, t.key) for t in result.tracks] == [("1", "8A"), ("2", "7A")]
    assert result.skipped == 1
    assert result.playlists == {"Warm": ["2", "1"]}


# --------------------------------------------------------------------------- #
# Deduplicación de temas repetidos en la biblioteca (mismo tema, id distinto)
# --------------------------------------------------------------------------- #
def test_dedupe_key_same_location_different_id() -> None:
    """El mismo fichero de audio reimportado en Rekordbox recibe un TrackID nuevo."""
    a = make_track("1", location="/Music/track.mp3")
    b = make_track("2", location="/Music/track.mp3")
    assert a.dedupe_key() == b.dedupe_key()


def test_dedupe_key_same_metadata_no_location() -> None:
    """Sin ruta de archivo, el mismo título/artista/BPM (redondeado) cuenta como duplicado."""
    a = make_track("1", title="Same Song", artist="Same Artist", bpm=124.1)
    b = make_track("2", title="Same Song", artist="Same Artist", bpm=124.4)
    assert a.dedupe_key() == b.dedupe_key()


def test_dedupe_key_distinguishes_different_songs() -> None:
    a = make_track("1", title="Song A", artist="Artist", bpm=124.0)
    b = make_track("2", title="Song B", artist="Artist", bpm=124.0)
    c = make_track("3", location="/Music/a.mp3")
    d = make_track("4", location="/Music/b.mp3")
    assert a.dedupe_key() != b.dedupe_key()
    assert c.dedupe_key() != d.dedupe_key()


def test_parse_collection_node_drops_real_world_duplicates(constraints) -> None:  # type: ignore[no-untyped-def]
    """
    Reproduce el bug reportado: la misma colección de Rekordbox con un tema
    reimportado (mismo archivo, TrackID distinto) no debe producir el tema
    dos veces en ``available_tracks``.
    """
    tracks = [
        make_track("1", genre="Tech House", location="/Music/a.mp3"),
        make_track("2", genre="Tech House", location="/Music/a.mp3"),  # reimportado
        make_track("3", genre="Tech House", title="Other", artist="X", bpm=125.0),
    ]
    state = initial_state(constraints, tracks)
    update = parse_collection_node(state)
    assert len(update["available_tracks"]) == 2
    assert any("duplicados descartados" in v for v in update["violations"])


class FakeGenreSearch:
    """
    Doble de ``spotipy.Spotify`` para probar ``suggest_tracks_for_proposal``:
    simula la vía principal (``search(type="track", q='genre:"..."')``) y la
    de reserva (``search(type="artist", ...)`` + ``artist_top_tracks``), tal
    como hace la implementación real. Ninguna de las dos usa texto libre ni
    ``recommendations``.
    """

    def __init__(
        self,
        track_hits: int = 0,
        artist_hits: int = 0,
        tracks_per_artist: int = 3,
        fail: bool = False,
    ) -> None:
        self.track_hits = track_hits
        self.artist_hits = artist_hits
        self.tracks_per_artist = tracks_per_artist
        self.fail = fail
        self.search_calls: list[tuple[str, str]] = []  # (q, type)

    def search(self, q: str, type: str, limit: int, offset: int = 0) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("http status: 403")
        self.search_calls.append((q, type))
        if type == "track":
            items = [
                {
                    "id": f"direct{i}",
                    "name": f"Direct Track {i}",
                    "artists": [{"name": f"Direct Artist {i}"}],
                    "external_urls": {"spotify": f"https://open.spotify.com/track/direct{i}"},
                }
                for i in range(offset, min(offset + limit, self.track_hits))
            ]
            return {"tracks": {"items": items}}
        if type == "artist":
            items = [
                {"id": f"artist{i}", "name": f"Real Artist {i}"}
                for i in range(offset, min(offset + limit, self.artist_hits))
            ]
            return {"artists": {"items": items}}
        raise AssertionError(f"tipo de búsqueda inesperado: {type}")

    def artist_top_tracks(self, artist_id: str, country: str = "US") -> dict[str, Any]:
        n = artist_id.removeprefix("artist")
        return {
            "tracks": [
                {
                    "id": f"top-{n}-{i}",
                    "name": f"Top Track {n}-{i}",
                    "artists": [{"name": f"Real Artist {n}"}],
                    "external_urls": {"spotify": f"https://open.spotify.com/track/top-{n}-{i}"},
                }
                for i in range(self.tracks_per_artist)
            ]
        }


def test_suggest_tracks_for_proposal_success_via_direct_track_search() -> None:
    """La vía principal (temas directos con filtro de género) basta por sí sola."""
    placeholders = [make_track("s1", key="8A", bpm=124.0), make_track("s2", key="9B", bpm=126.0)]
    fake = FakeGenreSearch(track_hits=10)
    out, report = suggest_tracks_for_proposal(placeholders, ["tech house"], "", "", client=fake)
    assert {t.raw_source.payload["suggested_title"] for t in out} == {"Direct Track 0", "Direct Track 1"}
    assert all(t.raw_source.payload["suggested_url"].startswith("https://open.spotify.com/track/") for t in out)
    # El BPM/clave/energía del slot original nunca cambian.
    assert out[0].bpm == placeholders[0].bpm and out[0].key == placeholders[0].key
    assert out[1].bpm == placeholders[1].bpm and out[1].key == placeholders[1].key
    assert report.suggested == 2 and report.fell_back == 0
    assert all(t == "track" for _, t in fake.search_calls)  # nunca hizo falta la reserva por artista


def test_suggest_tracks_for_proposal_falls_back_to_artist_top_tracks() -> None:
    """Si los temas directos no bastan, completa con artistas del género + su top."""
    placeholders = [make_track(f"s{i}", key="8A") for i in range(4)]
    fake = FakeGenreSearch(track_hits=1, artist_hits=3, tracks_per_artist=2)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    titles = {t.raw_source.payload["suggested_artist"] for t in out}
    assert "Direct Artist 0" in titles
    assert any(a.startswith("Real Artist") for a in titles)
    assert report.suggested == 4 and report.fell_back == 0
    assert any(t == "artist" for _, t in fake.search_calls)  # sí recurrió a la reserva


def test_suggest_tracks_for_proposal_not_enough_candidates_keeps_rest() -> None:
    """Si ni temas directos ni artistas del género dan bastantes, el resto conserva el marcador."""
    placeholders = [make_track(f"s{i}", key="8A") for i in range(5)]
    fake = FakeGenreSearch(track_hits=0, artist_hits=1, tracks_per_artist=1)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    assert out[0].raw_source.payload.get("suggested_artist") == "Real Artist 0"
    assert out[1:] == placeholders[1:]
    assert report.suggested == 1 and report.fell_back == 4 and report.failed == 0


def test_suggest_tracks_for_proposal_hard_failure_falls_back_for_all() -> None:
    """Credenciales inválidas u otro fallo de red: ningún slot se queda a medias."""
    placeholders = [make_track("s1", key="8A"), make_track("s2", key="9A"), make_track("s3", key="10A")]
    fake = FakeGenreSearch(fail=True)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 3 and "403" in report.first_error


def test_suggest_tracks_for_proposal_empty_input() -> None:
    out, report = suggest_tracks_for_proposal([], [], "", "", client=FakeGenreSearch())
    assert out == [] and report.attempted == 0


def test_suggest_tracks_for_proposal_uses_user_genre_before_fallback() -> None:
    """Prueba primero el género tal cual lo escribió el usuario, con el filtro de campo genre:."""
    fake = FakeGenreSearch()  # sin resultados en ninguna vía
    suggest_tracks_for_proposal([make_track("s1")], ["Progressive House"], "", "", client=fake)
    assert fake.search_calls[0] == ('genre:"Progressive House"', "track")


def test_suggest_tracks_for_proposal_skips_artist_with_no_top_tracks() -> None:
    """Un artista sin temas destacados no debe abortar la búsqueda para el resto."""

    class PartialArtists(FakeGenreSearch):
        def artist_top_tracks(self, artist_id: str, country: str = "US") -> dict[str, Any]:
            if artist_id == "artist0":
                raise RuntimeError("no top tracks")
            return super().artist_top_tracks(artist_id, country)

    placeholders = [make_track("s1", key="8A")]
    fake = PartialArtists(track_hits=0, artist_hits=2, tracks_per_artist=1)
    out, report = suggest_tracks_for_proposal(placeholders, [], "", "", client=fake)
    assert out[0].raw_source.payload.get("suggested_artist") == "Real Artist 1"
    assert report.suggested == 1
