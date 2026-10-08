"""Piezas visuales puras: color Camelot y chips."""

from src.app.theme import NEUTRAL_CHIP, camelot_chip, camelot_color, camelot_ribbon


def test_camelot_color_by_number_ignores_mode() -> None:
    assert camelot_color("8A") == camelot_color("8b")
    assert camelot_color("1A") != camelot_color("2A")


def test_camelot_color_invalid_is_neutral() -> None:
    for bad in ("", "13A", "0B", "Am", "—"):
        assert camelot_color(bad) == NEUTRAL_CHIP


def test_chip_escapes_html() -> None:
    assert "<script>" not in camelot_chip("<script>")


def test_ribbon_has_one_chip_per_key_and_arrows_between() -> None:
    out = camelot_ribbon(["8A", "9A", "9B"])
    assert out.count("nr-chip") == 3
    assert out.count("→") == 2
