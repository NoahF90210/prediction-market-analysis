# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands assume the venv at `.venv/`:

```bash
# Set up
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Rebuild the full dataset (ingests, normalizes, scores, exports)
.venv/bin/python src/build_accuracy_dataset.py

# Regenerate summary analysis CSVs into data/cleaned/ (not committed)
.venv/bin/python src/analyze_accuracy.py

# Run the Dash dashboard locally at http://127.0.0.1:8050
.venv/bin/python app.py

# Run all tests
.venv/bin/python -m pytest

# Run a single test file
.venv/bin/python -m pytest tests/test_accuracy.py

# Run the Jupyter notebook
.venv/bin/jupyter notebook notebooks/prediction_market_accuracy.ipynb
```

## Architecture

The project evaluates forecast accuracy of resolved Polymarket and Kalshi binary markets. The pipeline has four stages:

### 1. Ingestion (`src/ingest_polymarket_resolved.py`, `src/ingest_kalshi_resolved.py`)
Pulls resolved market records from each platform's API/data, normalizes raw fields, and optionally syncs to a Supabase warehouse via `src/supabase_storage.py`. Polymarket has richer cached history; Kalshi relies more on snapshot fallbacks.

### 2. Category normalization (`src/normalize_market_categories.py`, `src/category_mapping.py`)
Each market is classified into a canonical category using a fail-closed priority chain:
1. **Override** — explicit entry in `config/category_overrides.csv` (confidence: 1.0)
2. **Platform metadata** — raw platform category mapped via `config/category_taxonomy.yml` → `platform_category_map` (confidence: 0.95)
3. **Tag slugs** (Polymarket only) — matched against `polymarket_tag_slug_map` in the taxonomy (confidence: 0.95)
4. **Mapping rules** — phrase patterns from `taxonomy.mapping_rules` (confidence: 0.90)
5. **Keyword fallback** — broader keyword list from `taxonomy.keyword_fallback` (confidence: 0.65, always flagged for review)
6. **Unclassified** — flagged for review, excluded from analysis

Classification confidence, source, and review flags are stored per row. Rows below `CATEGORY_CONFIDENCE_THRESHOLD` (default 0.85) are excluded from scoring.

### 3. Scoring (`src/warehouse_pipeline.py`, `src/accuracy.py`)
`build_accuracy_dataset.py` orchestrates the full pipeline. Only `analysis_ready` rows (volume ≥ $100K, valid resolution, non-trivial forecast probability, non-flagged category) enter scoring. Forecast probability is the **last non-trivial pre-resolution YES price** (between 0.02 and 0.98) from cached history. Metrics: Brier score, log loss, calibration, bootstrap 95% CIs, and OLS regression.

### 4. Dashboard (`app.py`)
Plotly/Dash app. Loads `data/cleaned/accuracy_markets.csv` at startup (cached with `@lru_cache`). All chart updates go through a single `@app.callback` that re-filters the in-memory DataFrame. Deployed on Render via `gunicorn app:server`.

### Key data flow

```
ingest_polymarket_resolved + ingest_kalshi_resolved
  → build_raw_inventory (warehouse_pipeline)
  → normalize_market_inventory (category classification)
  → score_markets (add_score_columns)
  → build_dashboard_export
  → data/cleaned/accuracy_markets.csv   ← app.py reads this
```

### Settings and environment (`src/settings.py`)
All thresholds and Supabase credentials come from `.env`. See `.env.example` for the full list. The `ROOT` path is resolved relative to `settings.py`, so scripts run correctly from any working directory.

### Config files
- `config/category_taxonomy.yml` — canonical category list, priority order, platform→canonical mapping, tag slug map, mapping rules, keyword fallback
- `config/category_overrides.csv` — per-market hard overrides (match by market_id, title, or slug)

To add or correct a category assignment, prefer adding a row to `category_overrides.csv` over editing the taxonomy.
