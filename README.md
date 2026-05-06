# Prediction Market Accuracy

**How accurate are the prices on liquid prediction markets?**

Across **900 resolved binary contracts** from Polymarket and Kalshi (≥ $100k volume each), market-implied probabilities scored a **Brier of 0.127** — beating an always-50% baseline by **49%**, an in-sample category base-rate by **43%**, and a 5-fold gradient-boosted model trained on volume + lead time + category by **44%**.

**Live dashboard:** www.forecastaudit.dev

---

## What's in here

A reproducible end-to-end pipeline (ingest → category-normalize → score → export → static dashboard) plus a written editorial dashboard. Aimed at an audience of one analyst who'd read it carefully, not a generic "data science portfolio."

## Methodology

**Scope.** Resolved binary YES/NO contracts on Polymarket and Kalshi with ≥ $100k traded volume. Categories assigned via a metadata-first taxonomy with override CSV; rows below the category-confidence threshold are excluded.

**Forecast definition (apples-to-apples).** For each market, the forecast probability is the **last non-trivial YES price** (between 0.02 and 0.98) observed at least **30 minutes before close**. The lead-time guard matters: sports markets trade up to the final second when the outcome is essentially decided, so scoring the last trade alone measures clairvoyance, not forecasting. The same rule is applied to both platforms.

**Metrics.**
- Brier score (mean squared error of probability vs. outcome)
- Log loss
- Calibration in 10-percentage-point buckets
- Bootstrap 95% CIs on platform-level Brier (2,000 resamples)
- A 5-fold OOF logistic regression baseline on `log(volume) + days_to_resolution + category`
- A 5-fold OOF gradient-boosted baseline on the same features plus platform

## Headline findings

| | Brier | 95% CI |
|---|---:|---:|
| Polymarket (n=365) | 0.113 | [0.098, 0.128] |
| Kalshi (n=535) | 0.137 | [0.119, 0.154] |
| **Overall (n=900)** | **0.127** | — |

- **The platform CIs overlap.** Polymarket has the lower headline number, but the gap is small enough that any sharp claim about "which platform is more accurate" is not supported.
- **Markets beat both ML baselines.** The OOF logistic and gradient-boosted models on the obvious structural features (volume, lead time, category, platform) score Brier 0.211 and 0.226. Markets at 0.127 contain real signal beyond what those features alone capture.
- **Calibration is reasonable but not perfect** — mid-probability buckets (40–60%) sit slightly below the 45° line, hinting at modest overestimation away from the extremes.
- **Lead time and volume both correlate with lower error.** Markets open >30 days before resolution, and markets above $5M volume, score notably better. Associational, not causal — but consistent with the intuition that liquidity and time give the price room to converge.

## Architecture

Four-stage pipeline orchestrated by `src/build_accuracy_dataset.py`:

1. **Ingest.** `src/ingest_polymarket_resolved.py` and `src/ingest_kalshi_resolved.py` pull resolved markets and cache trade history per market under `data/raw/`. Kalshi trades are paginated via `/markets/trades` (see `src/backfill_kalshi_trades.py` to (re)build the cache).
2. **Normalize categories.** `src/normalize_market_categories.py` applies a fail-closed priority chain: explicit override → platform metadata → tag slug (Polymarket) → mapping rule → keyword fallback → unclassified. Confidence + source recorded per row. Configured via `config/category_taxonomy.yml` and `config/category_overrides.csv`.
3. **Score.** `src/score_markets.py` and `src/accuracy.py` compute Brier, log loss, calibration, baselines, and bootstrap CIs.
4. **Export.** `src/build_dashboard_data.py` writes `static_dashboard/data.js` for the React-in-browser dashboard.

The dashboard (`static_dashboard/`) is deliberately build-step-free: React + Babel-standalone served as static files by a thin Flask app (`app.py`), deployed on Render.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Full rebuild (re-fetches Polymarket events and Kalshi inventory; slow)
.venv/bin/python src/build_accuracy_dataset.py

# Just rebuild the dashboard payload from the existing scored CSV (fast)
.venv/bin/python src/build_dashboard_data.py

# Serve the dashboard locally
.venv/bin/python app.py    # → http://127.0.0.1:8050
```

Tests:

```bash
.venv/bin/python -m pytest
```

## Limitations

- The two ML baselines use only structural features (volume, lead time, category, platform). A serious effort to *beat* the market would need event-specific features.
- The platform comparison restricts to markets ≥ $100k. Kalshi has many smaller markets; this filter biases the sample toward Kalshi's more liquid, sports-heavy slice.
- Bootstrap CIs assume i.i.d. sampling. Markets within an event (e.g. all teams in one tournament) are correlated, so the true intervals are slightly wider than reported.
- The category taxonomy is opinionated. The override CSV is the right place to correct individual mis-classifications.

## What's next

- Score earlier snapshots (1 day, 7 days before resolution) to separate genuine forecasting from last-mile convergence.
- Add an external benchmark — Metaculus or 538 forecasts — for the categories where comparable forecasts exist.
- A matched-sample platform comparison restricting both sides to the same event types.
