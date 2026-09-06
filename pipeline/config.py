"""Paths and reporting assumptions shared by the generator, pipeline and app.

Read from the environment, with defaults so it runs with no .env file.
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

# Fixed so the dataset is identical on every run.
SEED = int(os.environ.get("VELLA_SEED", "20240117"))

# Reporting cutoff. Sits ~2 weeks after the last order month, so recent months
# still have returns in flight and get flagged provisional.
AS_OF_DATE = date.fromisoformat(os.environ.get("VELLA_AS_OF_DATE", "2026-09-15"))

# Own-store prices are VAT-inclusive; the marketplaces aren't. Stripped to net
# in cleaning so channels compare fairly.
VAT_RATE = float(os.environ.get("VAT_RATE", "0.20"))

# How late a return can arrive. Used to spread return dates and to flag
# months that aren't settled yet.
RETURN_WINDOW_DAYS = 60
