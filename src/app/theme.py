"""
Aspecto visual de la app: CSS global y piezas HTML (chips Camelot).
Sin dependencia de Streamlit salvo ``inject_css``; el resto es puro y testeable.
"""

from __future__ import annotations

import html
import re
from typing import Final, Sequence

# Colores de la rueda Camelot, de 1 a 12 (tonos equidistantes).
CAMELOT_HUES: Final[dict[int, str]] = {
    1: "#35d6c0", 2: "#3bd48a", 3: "#7bd44b", 4: "#c3d43b", 5: "#f0c030", 6: "#f29a30",
    7: "#f06a45", 8: "#ee4f7a", 9: "#d84fb8", 10: "#a465e8", 11: "#6a7ae8", 12: "#3da0e8",
}
NEUTRAL_CHIP: Final[str] = "#5b6070"
_KEY_RE = re.compile(r"^\s*(1[0-2]|[1-9])\s*([ABab])\s*$")

CSS: Final[str] = """
<style>
.block-container { padding-top: 2rem; max-width: 1200px; }
h1 { letter-spacing: -0.02em; }
div[data-testid="stMetric"] {
  background: #141821; border: 1px solid #232838; border-radius: 12px; padding: 14px 16px;
}
div[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
.nr-hero { margin-bottom: 1.2rem; }
.nr-hero .tag { color: #9aa1b5; font-size: 1.02rem; margin-top: -0.4rem; }
.nr-ribbon { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0.4rem 0 1rem; }
.nr-chip {
  display: inline-block; min-width: 2.6em; text-align: center; padding: 3px 9px; border-radius: 999px;
  font: 600 0.82rem ui-monospace, SFMono-Regular, Menlo, monospace; color: #0b0d12;
}
.nr-sep { color: #4a5063; font-size: 0.8rem; }
.nr-ribbon-title { color: #9aa1b5; font-size: 0.85rem; margin-top: 0.8rem; }
button[kind="primary"] { font-weight: 700; letter-spacing: 0.02em; }
</style>
"""


def camelot_color(key: str) -> str:
    """Color de la rueda para una clave Camelot ("8A"); gris si no es válida."""
    match = _KEY_RE.match(key or "")
    return CAMELOT_HUES[int(match.group(1))] if match else NEUTRAL_CHIP


def camelot_chip(key: str) -> str:
    label = html.escape((key or "—").strip().upper() or "—")
    return f'<span class="nr-chip" style="background:{camelot_color(key)}">{label}</span>'


def camelot_ribbon(keys: Sequence[str]) -> str:
    """Ruta armónica del set: una fila de chips de color unidos por flechas."""
    parts: list[str] = []
    for i, key in enumerate(keys):
        if i:
            parts.append('<span class="nr-sep">→</span>')
        parts.append(camelot_chip(key))
    return f'<div class="nr-ribbon">{"".join(parts)}</div>'


def inject_css() -> None:
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
