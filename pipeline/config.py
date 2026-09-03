"""Shared configuration: filesystem layout and the reporting assumptions
that the generator, pipeline, and app all have to agree on.

Paths resolve relative to the repository root so the code behaves the same on
a laptop, in CI, or on Streamlit Community Cloud. Values are read from the
environment with committed defaults, so the app also runs with no .env file.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
CLEAN_DIR = REPO_ROOT / "data" / "clean"

# Fixed so the synthetic dataset is identical on every machine and every run.
# Changing this regenerates a different (but equally valid) history.
SEED = int(os.environ.get("VELLA_SEED", "20240117"))

# The synthetic history runs 2024-09-01 .. 2026-08-31. We report as of the day
# after the last order so the return window below is closed for every order and
# monthly return rates are comparable across the whole period.
AS_OF_DATE = date.fromisoformat(os.environ.get("VELLA_AS_OF_DATE", "2026-09-01"))

# Own-store list prices are VAT-inclusive; Amazon and the EU marketplace are
# exclusive. Own-store revenue is divided by (1 + VAT_RATE) in cleaning so
# margin is comparable across channels.
VAT_RATE = float(os.environ.get("VAT_RATE", "0.20"))

# Returns can land up to this many days after the order date. Used both by the
# generator (to spread return_date) and the pipeline (to flag periods that are
# not yet fully settled).
RETURN_WINDOW_DAYS = 60
