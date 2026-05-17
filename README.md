# Forecast Audit: Prediction Market Accuracy

[![Tests](https://github.com/NoahF90210/prediction-market-analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/NoahF90210/prediction-market-analysis/actions/workflows/tests.yml)

**Summary:** I built a deployed data product that audits whether Polymarket and Kalshi prices were actually good forecasts before outcomes were known.

**Were prediction markets actually accurate forecasts before outcomes were known?**

Prediction markets claim to turn crowd belief into probabilities. This project tests that claim on **769 resolved, high-volume contracts** from Polymarket and Kalshi, then ships the results as a browser dashboard. It audits resolved YES/NO contracts using only pre-close prices. The short answer: in this liquid, sports-heavy sample, market-implied probabilities were meaningfully better than naive baselines, especially at the extremes, but the evidence is not broad enough to claim all prediction markets or all categories are well-calibrated.

**Live dashboard:** https://www.forecastaudit.dev

## Portfolio Snapshot

An end-to-end public data product: ingestion, category normalization, leakage-resistant snapshot extraction, scoring, baseline comparison, data-quality checks, tests, and a deployed editorial dashboard. It is designed to be quickly understandable: collect real market data, avoid leakage, score forecast accuracy, and show the findings clearly.

| What to inspect | Current result |
|---|---:|
| Scored contracts | 769 resolved binary contracts |
| Platforms | Polymarket: 365, Kalshi: 404 |
| Liquidity rule | Each scored contract has at least $100k traded volume |
| Combined scored volume | $815.1M |
| Primary forecast | Last non-trivial YES price at least 30 minutes before close |
| Overall Brier score | 0.1397 |
| Overall log loss | 0.4216 |
| Always-50% Brier baseline | 0.2500 |
| Gradient-boosted structural baseline | 0.2405 Brier |

What this demonstrates:

- Built an end-to-end Python analytics pipeline for **769 resolved prediction-market contracts** across Polymarket and Kalshi.
- Designed a leakage-resistant scoring rule using the last non-trivial YES price at least **30 minutes before close**, so markets are scored before outcomes are effectively known.
- Evaluated forecast quality with **Brier score, log loss, calibration buckets, bootstrap confidence intervals, and baseline models**.
- Added data-quality checks that separate strong cross-platform claims from descriptive-only categories.
- Deployed a polished dashboard for filtering individual contracts, inspecting calibration, and comparing platform/category performance, backed by committed `static_dashboard/data.js` so reviewers can reproduce the audit without API credentials.

## Key Findings

- **Markets beat simple baselines in this sample.** The market Brier score was **0.1397**, compared with **0.2500** for an always-50% forecast and **0.2405** for a gradient-boosted baseline using volume, lead time, category, and platform.
- **Forecasts were most reliable at the extremes.** Buckets below 20% and above 80% tracked realized outcomes closely; mid-range YES probabilities showed mild overconfidence.
- **Platform differences should be read cautiously.** Polymarket's point Brier score was lower than Kalshi's in the dashboard payload, but the sample is sports-heavy and bootstrap intervals overlap.
- **Volume and lead time are associated with lower error.** The dashboard shows lower average Brier scores for higher-volume and longer-lead-time buckets, but this is observational, not causal.

## Methodology In Plain English

Prediction markets often look accurate near the end because the outcome may already be obvious. This audit asks a stricter question: what did the market imply **before** the close?

```text
Resolved YES/NO contracts
        |
        v
Keep liquid markets only ($100k+ volume)
        |
        v
Find the last non-trivial YES price at least 30 minutes before close
        |
        v
Compare that probability with the final YES/NO outcome
        |
        v
Score accuracy with Brier, log loss, calibration, confidence intervals, and baselines
```

The primary forecast is the last YES price between `0.02` and `0.98` observed at least 30 minutes before market close. That rule excludes terminal prices that may reflect information that was already effectively resolved, especially in sports and short-window contracts.

The pipeline also has schema fields for `1d` and `7d` snapshots. In the current committed dashboard build, the populated and audited horizon is `30m`; the longer horizons are marked as future backfill work.


## Data Quality And Caveats

The strongest current evidence supports a **liquid, sports-heavy audit**, not a universal claim about every prediction-market category.

| Category | n | Use in analysis |
|---|---:|---|
| Sports | 583 | Cross-platform comparison is supported |
| Crypto | 118 | Descriptive only; Kalshi-only in current scored sample |
| Elections | 36 | Descriptive only; mostly Polymarket |
| Commodities | 17 | Too small for category-level claims |
| Geopolitics | 7 | Too small for category-level claims |
| Politics | 7 | Too small for category-level claims |
| Finance | 1 | Drop from category-level analysis |

Important limitations:

- The current dataset is dominated by sports markets, so overall performance is heavily weighted toward that category.
- Only sports currently has enough observations on both platforms for a meaningful platform/category comparison.
- The $100k volume threshold selects markets with active price discovery; illiquid contracts are out of scope.
- Bootstrap intervals assume independent markets, but related contracts from the same event can be correlated.
- Baselines use structural features only. Event-specific models would need richer market text, timing, news, and domain features.

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

1. Ingest resolved markets and historical prices from Polymarket and Kalshi.
2. Normalize categories using platform metadata, tags, taxonomy rules, and explicit overrides.
3. Extract controlled pre-close forecast snapshots.
4. Score forecasts and baselines with reusable metric functions.
5. Export dashboard-ready data and render the static browser dashboard.

Key files:

- `src/forecast_snapshots.py`: shared pre-close snapshot logic
- `src/build_accuracy_dataset.py`: scoring dataset build
- `src/build_dashboard_data.py`: dashboard payload generation
- `src/data_quality.py`: category eligibility and data-quality reporting
- `static_dashboard/`: browser-rendered dashboard
- `tests/`: pytest coverage for scoring, exports, categories, and dashboard payload shape

## Next Improvements

- Backfill live `1d` and `7d` snapshot extraction now that the schema paths are in place.
- Expand category coverage before making non-sports category claims.
- Separate single-market binary contracts from multileg or parlay-style markets.
- Add matched event-type comparisons across platforms.
