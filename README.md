**Summary:** I built a deployed data product that audits whether Polymarket and Kalshi prices were actually good forecasts before outcomes were known.

**Live dashboard:** https://www.forecastaudit.dev

## Portfolio Snapshot

Prediction markets claim to turn crowd belief into probabilities. I tested that claim on **769 resolved, high-volume contracts** from Polymarket and Kalshi, then shipped the results as a browser dashboard.

This project is designed to be quickly understandable: collect real market data, avoid leakage, score forecast accuracy, show the findings clearly.

What it demonstrates:

- Built an end-to-end Python analytics pipeline for **769 resolved prediction-market contracts** across Polymarket and Kalshi.
- Designed a leakage-resistant scoring rule using the last non-trivial YES price at least **30 minutes before close**, so markets are scored before outcomes are effectively known.
- Evaluated forecast quality with **Brier score, log loss, calibration buckets, bootstrap confidence intervals, and baseline models**.
- Added data-quality checks that separate strong cross-platform claims from descriptive-only categories.
- Deployed a polished dashboard that lets users filter individual contracts, inspect calibration, and compare platform/category performance.

