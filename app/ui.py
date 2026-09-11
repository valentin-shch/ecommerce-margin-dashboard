"""Shared page chrome, number formatting and Plotly defaults."""

import streamlit as st

# Touch has no modebar and no hover; keep the chart itself as the only
# information surface.
PLOTLY_CONFIG = {"responsive": True, "displayModeBar": False}


def configure_page(title: str, subtitle: str) -> None:
    st.set_page_config(page_title=f"Vella Home - {title}", layout="wide")
    st.markdown(f"### {title}")
    st.caption(subtitle)


def fmt_eur(x: float) -> str:
    return f"EUR {x:,.0f}"


def fmt_eur_compact(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_000_000:
        return f"{sign}EUR {x / 1_000_000:.1f}M"
    if x >= 1_000:
        return f"{sign}EUR {x / 1_000:.0f}K"
    return f"{sign}EUR {x:.0f}"
