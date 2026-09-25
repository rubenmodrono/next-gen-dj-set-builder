"""Punto de entrada de la interfaz web: ``python -m streamlit run app.py``."""

from __future__ import annotations

import importlib.util
import sys

REQUIRED: dict[str, str] = {
    "pydantic": "pydantic>=2.6",
    "langgraph": "langgraph>=0.2",
    "pandas": "pandas>=2.2",
    "altair": "altair>=5",
}

missing = [spec for module, spec in REQUIRED.items() if importlib.util.find_spec(module) is None]

if missing:
    import streamlit as st

    st.set_page_config(page_title="Next-Gen DJ SetBuilder", page_icon="🎧")
    st.error("Faltan dependencias en el Python con el que se está ejecutando Streamlit.")
    st.markdown(f"**Python en uso:** `{sys.executable}`")
    st.markdown("**No encontrados:** " + ", ".join(f"`{m}`" for m in missing))
    st.markdown("Instálalas con **este mismo** intérprete y vuelve a arrancar:")
    st.code(
        f'"{sys.executable}" -m pip install -r requirements.txt\n'
        f'"{sys.executable}" -m streamlit run app.py',
        language="bash",
    )
    st.stop()

from src.app.web import main  # noqa: E402

main()
