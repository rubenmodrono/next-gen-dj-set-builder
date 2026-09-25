"""Tests de los proveedores alternativos de sugerencias del modo propuesta."""

from __future__ import annotations

from typing import Any

import pytest

from src.enrichment.common import SuggestionReport
from src.enrichment.lastfm import suggest_tracks_for_proposal_lastfm
from src.enrichment.llm_agent import suggest_tracks_for_proposal_llm
from tests.conftest import make_track


# --------------------------------------------------------------------------- #
# Last.fm
# --------------------------------------------------------------------------- #
class FakeLastfm:
    """Doble de ``tag.gettoptracks``: ``tracks_by_tag[tag]`` es la lista completa de items."""

    def __init__(self, tracks_by_tag: dict[str, list[dict[str, Any]]] | None = None, fail: bool = False) -> None:
        self.tracks_by_tag = tracks_by_tag or {}
        self.fail = fail
        self.calls: list[tuple[str, int]] = []  # (tag, page)

    def __call__(self, method: str, **params: str) -> dict[str, Any]:
        assert method == "tag.gettoptracks"
        if self.fail:
            raise RuntimeError("Last.fm: Invalid API key (código 10)")
        tag, page, limit = params["tag"], int(params["page"]), int(params["limit"])
        self.calls.append((tag, page))
        items = self.tracks_by_tag.get(tag, [])
        start = (page - 1) * limit
        return {"tracks": {"track": items[start : start + limit]}}


def _item(artist: str, title: str) -> dict[str, Any]:
    return {"name": title, "artist": {"name": artist}, "url": f"https://www.last.fm/music/{artist}/_/{title}"}


def test_suggest_tracks_for_proposal_lastfm_success() -> None:
    placeholders = [make_track("s1", key="8A"), make_track("s2", key="9B")]
    fake = FakeLastfm({"tech house": [_item("A1", "T1"), _item("A2", "T2")]})
    out, report = suggest_tracks_for_proposal_lastfm(placeholders, ["tech house"], "key", client=fake)
    assert {t.raw_source.payload["suggested_title"] for t in out} == {"T1", "T2"}
    assert all(t.raw_source.payload["suggested_source"] == "Last.fm" for t in out)
    assert all(t.raw_source.payload["suggested_url"].startswith("https://www.last.fm/") for t in out)
    # El BPM/clave/energía del slot original nunca cambian.
    assert out[0].bpm == placeholders[0].bpm and out[0].key == placeholders[0].key
    assert report.suggested == 2 and report.fell_back == 0 and report.source == "Last.fm"


def test_suggest_tracks_for_proposal_lastfm_single_result_is_a_dict_not_a_list() -> None:
    """Last.fm devuelve un objeto suelto (no una lista) cuando el tag solo tiene un resultado."""

    class SingleResultLastfm(FakeLastfm):
        def __call__(self, method: str, **params: str) -> dict[str, Any]:
            assert method == "tag.gettoptracks"
            if params["page"] != "1":
                return {"tracks": {"track": []}}
            return {"tracks": {"track": _item("Solo Artist", "Solo Track")}}

    out, report = suggest_tracks_for_proposal_lastfm(
        [make_track("s1")], ["deep house"], "key", client=SingleResultLastfm()
    )
    assert out[0].raw_source.payload["suggested_artist"] == "Solo Artist"
    assert report.suggested == 1


def test_suggest_tracks_for_proposal_lastfm_not_enough_candidates_keeps_rest() -> None:
    placeholders = [make_track(f"s{i}", key="8A") for i in range(3)]
    fake = FakeLastfm({"electronic": [_item("A1", "T1")]})
    out, report = suggest_tracks_for_proposal_lastfm(placeholders, [], "key", client=fake)
    assert out[0].raw_source.payload.get("suggested_artist") == "A1"
    assert out[1:] == placeholders[1:]
    assert report.suggested == 1 and report.fell_back == 2 and report.failed == 0


def test_suggest_tracks_for_proposal_lastfm_hard_failure_falls_back_for_all() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    out, report = suggest_tracks_for_proposal_lastfm(placeholders, [], "bad-key", client=FakeLastfm(fail=True))
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 2 and "10" in report.first_error


def test_suggest_tracks_for_proposal_lastfm_empty_input() -> None:
    out, report = suggest_tracks_for_proposal_lastfm([], [], "key", client=FakeLastfm())
    assert out == [] and report.attempted == 0


# --------------------------------------------------------------------------- #
# Agente IA (búsqueda web)
# --------------------------------------------------------------------------- #
class FakeAnthropicMessages:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleTextResponse(self.text or "[]")


class SimpleTextResponse:
    def __init__(self, text: str) -> None:
        self.content = [SimpleTextBlock(text)]


class SimpleTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class FakeAnthropicClient:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.messages = FakeAnthropicMessages(text=text, error=error)


def test_suggest_tracks_for_proposal_llm_success() -> None:
    placeholders = [make_track("s1", key="8A"), make_track("s2", key="9B")]
    text = (
        'Aquí tienes los temas:\n'
        '[{"artist": "Real Artist 0", "title": "Real Title 0", "url": "https://beatport.com/t/0"},'
        ' {"artist": "Real Artist 1", "title": "Real Title 1", "url": ""}]'
    )
    client = FakeAnthropicClient(text=text)
    out, report = suggest_tracks_for_proposal_llm(placeholders, "key", client=client)
    assert out[0].raw_source.payload["suggested_artist"] == "Real Artist 0"
    assert out[0].raw_source.payload["suggested_url"] == "https://beatport.com/t/0"
    assert out[1].raw_source.payload["suggested_artist"] == "Real Artist 1"
    assert "suggested_url" not in out[1].raw_source.payload
    assert all(t.raw_source.payload["suggested_source"] == "Agente IA (búsqueda web)" for t in out)
    assert out[0].bpm == placeholders[0].bpm and out[0].key == placeholders[0].key
    assert report.suggested == 2 and report.fell_back == 0
    assert client.messages.calls[0]["tools"][0]["type"] == "web_search_20250305"


def test_suggest_tracks_for_proposal_llm_keeps_placeholder_when_agent_finds_nothing() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    text = '[{"artist": null, "title": null}, {"artist": "Real Artist 1", "title": "Real Title 1"}]'
    out, report = suggest_tracks_for_proposal_llm(placeholders, "key", client=FakeAnthropicClient(text=text))
    assert out[0] == placeholders[0]
    assert out[1].raw_source.payload["suggested_artist"] == "Real Artist 1"
    assert report.suggested == 1 and report.fell_back == 1


def test_suggest_tracks_for_proposal_llm_malformed_response_falls_back_for_all() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    client = FakeAnthropicClient(text="no soy json en absoluto")
    out, report = suggest_tracks_for_proposal_llm(placeholders, "key", client=client)
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 2 and report.first_error


def test_suggest_tracks_for_proposal_llm_api_failure_falls_back_for_all() -> None:
    placeholders = [make_track("s1"), make_track("s2")]
    client = FakeAnthropicClient(error=RuntimeError("invalid x-api-key"))
    out, report = suggest_tracks_for_proposal_llm(placeholders, "bad-key", client=client)
    assert out == placeholders
    assert report.suggested == 0 and report.failed == 2 and "invalid x-api-key" in report.first_error


def test_suggest_tracks_for_proposal_llm_empty_input() -> None:
    out, report = suggest_tracks_for_proposal_llm([], "key", client=FakeAnthropicClient(text="[]"))
    assert out == [] and report.attempted == 0


def test_suggest_tracks_for_proposal_llm_missing_package_raises_helpful_error() -> None:
    """Sin ``client`` inyectado y sin el paquete ``anthropic`` instalado, el error explica cómo instalarlo."""
    with pytest.raises(RuntimeError, match="anthropic"):
        suggest_tracks_for_proposal_llm([make_track("s1")], "key")


def test_suggestion_report_summary_includes_source_prefix() -> None:
    report = SuggestionReport(attempted=3, suggested=2, source="Last.fm")
    assert report.summary().startswith("Last.fm: 2/3")
