"""Smoke tests de la interfaz con el runner oficial de Streamlit (sin navegador)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.app.presenters import set_table  # noqa: E402
from src.core.models import SetConstraint  # noqa: E402
from src.graph.builder import build_set_graph  # noqa: E402
from src.graph.state import initial_state  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _run(at: AppTest) -> AppTest:
    at.run(timeout=30)
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_proposal_mode_end_to_end() -> None:
    at = _run(AppTest.from_file(APP))
    at.multiselect(key="genres").set_value(["Techno"])
    _run(at)
    at.button(key="build").click()
    _run(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Modo"] == "Propuesta"
    assert metrics["Temas"] == "12"  # 60 min / 5 min por tema
    assert at.dataframe[0].value["Camelot"].iloc[0] == "8A"


def test_demo_collection_end_to_end() -> None:
    at = _run(AppTest.from_file(APP))
    at.radio(key="source_mode").set_value("demo")
    _run(at)
    at.button(key="build").click()
    _run(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Modo"] == "Colección"
    assert int(metrics["Temas"]) > 0


def test_upload_mode_prompts_for_file() -> None:
    at = _run(AppTest.from_file(APP))
    at.radio(key="source_mode").set_value("upload")
    _run(at)
    assert any("Carga una colección" in i.value for i in at.info)


def test_limit_bpm_toggle_does_not_crash() -> None:
    """
    Regresión: ``st.slider`` exige que min_value/max_value/value/step compartan
    tipo. ``round()`` sin ``ndigits`` devuelve ``int``, así que construir
    ``value`` con ``round(...)`` sin convertir a ``float`` lanzaba
    ``StreamlitAPIException`` en cuanto se activaba "Fijar rango de BPM".
    """
    at = _run(AppTest.from_file(APP))
    at.toggle(key="limit_bpm").set_value(True)
    _run(at)
    lo, hi = at.slider(key="bpm_range").value
    assert isinstance(lo, float) and isinstance(hi, float)
    assert lo < hi


def test_proposal_mode_offers_suggestion_provider_choices() -> None:
    at = _run(AppTest.from_file(APP))
    radio = at.radio(key="suggestion_provider")
    assert radio.options == [
        "Sin sugerencias (solo BPM/clave/energía)",
        "Spotify (búsqueda por género)",
        "Last.fm (tags de género)",
        "Agente IA con búsqueda web (tu API key)",
    ]

    radio.set_value("Last.fm (tags de género)")
    at = _run(at)
    assert at.text_input(key="lastfm_api_key") is not None

    at.radio(key="suggestion_provider").set_value("Agente IA con búsqueda web (tu API key)")
    at = _run(at)
    assert at.text_input(key="llm_api_key") is not None
    assert at.text_input(key="llm_model").value == "claude-sonnet-5"


def test_collection_mode_hides_suggestion_provider_and_shows_spotify_enrichment() -> None:
    at = _run(AppTest.from_file(APP))
    at.radio(key="source_mode").set_value("demo")
    at = _run(at)
    with pytest.raises(KeyError):
        at.radio(key="suggestion_provider")
    assert at.text_input(key="spotify_client_id") is not None


def test_proposal_table_has_search_hint() -> None:
    constraints = SetConstraint(total_duration_min=30, target_genres=["House"], avg_track_duration_min=5)
    state = build_set_graph().invoke(initial_state(constraints))
    table = set_table(state["selected_set"], state["target_slots"], state["transitions"], proposal=True)
    assert list(table.columns)[:4] == ["#", "Inicio", "Tramo", "Busca"]
    assert table["Busca"].iloc[0].startswith("House · ")


def test_proposal_table_shows_real_suggestions_when_present() -> None:
    """Cuando al menos un slot tiene una sugerencia real (de cualquier proveedor), aparecen sus columnas."""
    constraints = SetConstraint(total_duration_min=30, target_genres=["House"], avg_track_duration_min=5)
    state = build_set_graph().invoke(initial_state(constraints))
    selected = state["selected_set"]
    suggested_first = selected[0].model_copy(
        update={
            "raw_source": selected[0].raw_source.model_copy(
                update={
                    "payload": {
                        **selected[0].raw_source.payload,
                        "suggested_artist": "Real Artist",
                        "suggested_title": "Real Title",
                        "suggested_url": "https://open.spotify.com/track/1",
                        "suggested_source": "Spotify",
                    }
                }
            )
        }
    )
    enriched = [suggested_first, *selected[1:]]
    table = set_table(enriched, state["target_slots"], state["transitions"], proposal=True)
    assert "Sugerencia" in table.columns and "Fuente" in table.columns and "Enlace" in table.columns
    assert table["Sugerencia"].iloc[0] == "Real Artist – Real Title"
    assert table["Fuente"].iloc[0] == "Spotify"
    assert table["Enlace"].iloc[0] == "https://open.spotify.com/track/1"
    assert table["Sugerencia"].iloc[1] == "—"
