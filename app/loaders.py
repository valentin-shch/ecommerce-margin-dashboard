"""Cached readers for the precomputed marts.

streamlit run app/X.py puts app/ on sys.path, not the repo root, so importing
pipeline.config needs a small path fix first, same issue as python script.py.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from pipeline.config import CLEAN_DIR

MARTS_DIR = CLEAN_DIR / "marts"


@st.cache_data
def load_mart(name: str) -> pd.DataFrame:
    return pd.read_parquet(MARTS_DIR / f"{name}.parquet")


@st.cache_data
def load_clean(name: str) -> pd.DataFrame:
    return pd.read_parquet(CLEAN_DIR / f"{name}.parquet")
