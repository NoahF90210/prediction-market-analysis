# Prediction Market Accuracy

[![Tests](https://github.com/NoahF90210/prediction-market-analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/NoahF90210/prediction-market-analysis/actions/workflows/tests.yml)

**How well do liquid prediction-market prices forecast resolved binary outcomes?**

This project evaluates resolved YES/NO contracts from Polymarket and Kalshi using Brier score, log loss, calibration buckets, bootstrap confidence intervals, and simple structural baselines.

**Live dashboard:** https://www.forecastaudit.dev

## Portfolio Snapshot

This is an end-to-end data product: API ingestion, market taxonomy normalization, forecast snapshot extraction, statistical scoring, data-quality checks, test coverage, and a deployed browser dashboard.

What it demonstrates:

- Built a reproducible Python analytics pipeline for 769 resolved, high-volume prediction-market contracts.
- Designed an apples-to-apples scoring rule that avoids last-trade leakage by using the last non-trivial YES price at least 30 minutes before close.
- Evaluated market calibration with Brier score, log loss, calibration buckets, bootstrap confidence intervals, and structural ML baselines.
- Added explicit data-quality reporting so category-level claims are separated from descriptive-only slices.
- Deployed a static editorial dashboard backed by generated data artifacts and covered core scoring logic with pytest.

## Core Question

Prediction-market prices are often interpreted as probabilities. This analysis asks whether those probabilities were calibrated before resolution, rather than after markets had already converged to the known outcome.

The primary scoring rule uses the last available non-trivial YES price observed at least 30 minutes before close. That guard is important for sports and short-window markets, where final trades can occur after the outcome is practically known.

## Current Dataset

The current scored dataset contains **769 resolved binary contracts** with at least **$100k** in traded volume.

| Platform | Scored markets | Mean Brier |
|---|---:|---:|
| Polymarket | 365 | 0.113 |
| Kalshi | 404 | 0.164 |
| Overall | 769 | 0.140 |

The sample is liquid but not broad. It is heavily concentrated in sports, with additional descriptive coverage in Kalshi crypto markets and Polymarket election markets.

## Main Findings

- Market prices beat the always-50% baseline and simple structural baselines on Brier score.
- The overall platform gap is not stable enough for a broad platform-quality claim outside sports-heavy samples.
- Calibration is strongest in the extreme probability buckets.
- Mid-range buckets show mild overconfidence, though bucket-level sample sizes are modest.
- Higher volume and longer lead time are associated with lower error; this is observational, not causal.

## Data Quality Status

The strongest current evidence supports a **sports-heavy analysis of liquid markets**, not a broad conclusion about every prediction-market category.

Category-level recommendations from the current scored dataset:

| Category | n | Use in analysis |
|---|---:|---|
| Sports | 583 | Cross-platform comparison is supported |
| Crypto | 118 | Descriptive only; Kalshi-only in current scored sample |
| Elections | 36 | Descriptive only; mostly Polymarket |
| Commodities | 17 | Too small for category-level claims |
| Geopolitics | 7 | Too small for category-level claims |
| Politics | 7 | Too small for category-level claims |
| Finance | 1 | Drop from category-level analysis |

The pipeline now supports explicit `30m`, `1d`, and `7d` snapshot fields (probability, observed timestamp, target timestamp, source, and quality label). In the current cached rebuild, only `30m` snapshots are populated; `1d` and `7d` remain a required backfill step when live API access is available.

## Methodology

**Scope.** Resolved binary YES/NO contracts on Polymarket and Kalshi with at least $100k traded volume.

**Forecast definition.** The primary forecast is the last non-trivial YES price between 0.02 and 0.98 observed at least 30 minutes before close. The schema also carries 1-day and 7-day snapshot slots for explicit horizon auditing.

**Metrics.**

- Brier score
- Log loss
- 10-percentage-point calibration buckets
- Bootstrap confidence intervals for platform-level Brier
- Baselines using always-50%, category base rate, logistic regression, and gradient-boosted trees on structural features

**Category handling.** Markets are assigned to a canonical taxonomy using platform metadata, tags, mapping rules, and a review queue. Sparse categories are flagged separately from categories with enough support for comparison.

## Reproduce Locally

The deployed dashboard uses the committed `static_dashboard/data.js` payload, so it can be served from a fresh clone without API credentials.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8050.

Run the test suite:

```bash
source .venv/bin/activate
python -m pytest -q
```

Optional API-backed rebuild:

```bash
cp .env.example .env
python src/build_accuracy_dataset.py
python src/build_dashboard_data.py
```

Polymarket collection can run without private credentials. Kalshi trade-history backfills require Kalshi API credentials in `.env`; Supabase variables are only needed for warehouse sync tasks.

## Technical Architecture

The pipeline runs as:

1. Ingest resolved markets and historical prices from Polymarket and Kalshi.
2. Normalize market categories with platform metadata, taxonomy rules, and explicit overrides.
3. Extract forecast snapshots at controlled pre-close horizons.
4. Score forecasts and baselines with reusable metric functions.
5. Write dashboard-ready data and render an editorial static dashboard.

## Project Structure

- `src/collect_polymarket.py`: Polymarket event and CLOB price-history collection
- `src/ingest_kalshi_resolved.py`: Kalshi resolved-market ingestion
- `src/forecast_snapshots.py`: shared forecast snapshot and pre-close cutoff logic
- `src/kalshi_forecasts.py`: Kalshi trade-history forecast extraction
- `src/category_mapping.py`: category normalization
- `src/data_quality.py`: data-quality and category-eligibility summaries
- `src/build_dashboard_data.py`: dashboard payload generation
- `static_dashboard/`: browser-rendered dashboard
- `.github/workflows/tests.yml`: CI workflow for pytest
- `LICENSE`: MIT license

## Limitations

- The current dataset is dominated by sports markets.
- Only sports currently has enough observations on both platforms for a meaningful platform/category comparison.
- Some Kalshi rows are missing open-time metadata, limiting lead-time analysis.
- Bootstrap intervals assume independent markets, but related contracts from the same event can be correlated.
- The baseline models use only structural features. Event-specific modeling would require richer features.

## Next Improvements

- Backfill the dataset with live `1d` and `7d` snapshot extraction now that the schema paths are in place.
- Expand category coverage before making non-sports category claims.
- Separate single-market binary contracts from multileg or parlay-style markets.
- Add matched event-type comparisons across platforms.
