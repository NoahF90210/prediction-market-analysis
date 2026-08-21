from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Deliberately do not auto-load .env. Callers must supply environment variables
# explicitly so validation and fixture builds never read local secret files.

RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "cleaned"
SUPABASE_DIR = ROOT / "supabase"
SUPABASE_MIGRATIONS_DIR = SUPABASE_DIR / "migrations"

MIN_ANALYSIS_VOLUME = float(os.getenv("MIN_ANALYSIS_VOLUME", "100000"))
CROSS_PLATFORM_MIN_MARKETS = int(os.getenv("CROSS_PLATFORM_MIN_MARKETS", "30"))
CATEGORY_CONFIDENCE_THRESHOLD = float(os.getenv("CATEGORY_CONFIDENCE_THRESHOLD", "0.85"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "market_analysis")

OUTPUT_MARKETS_CSV = CLEAN_DIR / "accuracy_markets.csv"
OUTPUT_SCORED_CSV = CLEAN_DIR / "accuracy_markets_scored.csv"
OUTPUT_REVIEW_QUEUE_CSV = CLEAN_DIR / "category_review_queue.csv"
