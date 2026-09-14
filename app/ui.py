"""Shared page chrome, number formatting and Plotly defaults."""

import streamlit as st

# Touch has no modebar and no hover; keep the chart itself as the only
# information surface.
PLOTLY_CONFIG = {"responsive": True, "displayModeBar": False}

CHANNEL_LABELS = {"own_store": "the own store", "amazon": "Amazon", "marketplace": "the marketplace"}


def configure_page(title: str, subtitle: str) -> None:
    st.set_page_config(page_title=f"Vella Home - {title}", layout="wide")
    st.markdown(f"### {title}")
    st.markdown(subtitle)


def fmt_eur(x: float) -> str:
    return f"€{x:,.0f}"


def fmt_eur_compact(x: float) -> str:
    # Every figure in this app is well under 10M, so everything rounds to the
    # nearest 1K. A figure rounded to the nearest 10K (an "M" with 2 decimals)
    # next to others rounded to the nearest 1K means the parts don't sum to
    # the displayed total - keeping one precision throughout avoids that.
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 10_000_000:
        return f"{sign}€{x / 1_000_000:.2f}M"
    if x >= 1_000:
        return f"{sign}€{x / 1_000:,.0f}K"
    return f"{sign}€{x:.0f}"
