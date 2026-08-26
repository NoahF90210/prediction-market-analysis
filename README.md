# Prediction Market Analysis

**[Open the live dashboard](https://forecastaudit.dev)** · **[View the source on GitHub](https://github.com/NoahF90210/prediction-market-analysis)**

Prediction Market Analysis is an open-source study of whether Polymarket's pre-result YES probabilities lined up with what happened.

The project turns public market records into a simple calibration view that is easy to inspect, reproduce, and challenge.

## The question

> When Polymarket says an outcome has a certain probability, does that outcome happen about that often?

The analysis compares the latest YES probability observed at or before 24 hours before resolution with the final YES or NO outcome.

It presents a descriptive comparison of assigned probabilities and resolved outcomes.

## Headline result

Across **75,036 qualifying YES/NO markets** resolved during 2025, the average predicted YES probability was **27.1%** and YES occurred **24.6%** of the time.

The largest difference appeared in the 40% to 60% range.

Markets in that range predicted YES about **49.4%** of the time, while YES occurred about **39.8%** of the time.

The careful conclusion is that the probabilities were broadly informative, with the largest mismatch in the middle range.

## Why the weighting matters

Polymarket events can contain several related markets.

The primary view gives every qualifying market one row.

A robustness check selects one deterministic market per event.

| Analysis | Markets | Average prediction | Observed YES | Gap |
| --- | ---: | ---: | ---: | ---: |
| All qualifying markets | 75,036 | 27.10% | 24.58% | -2.53 percentage points |
| One market per event | 14,678 | 37.13% | 37.98% | +0.84 percentage points |

The result is a market-level descriptive analysis with a one-market-per-event robustness view.

## What is included

The analysis uses Polymarket records resolved from **January 1, 2025 00:00 UTC** through **January 1, 2026 00:00 UTC**, with the end boundary exclusive.

The collection inventory contained **1,495,875 unique market IDs** after keyset pagination and deduplication.

The analytical candidate set contained **92,875 canonical YES/NO markets** with resolved outcomes and verified `closedTime` values inside the window.

The final included dataset contains **75,036 markets across 14,678 events** after requiring a usable pre-resolution price snapshot.

Named-outcome markets such as `Texas/ASU`, `Over/Under`, and `Up/Down` receive explicit eligibility treatment instead of heuristic mapping.

Categories are retained as metadata for inspection.

## How it works

1. Enumerate the closed Polymarket inventory through the official Gamma keyset endpoint.
2. Keep canonical YES/NO markets whose verified `closedTime` falls inside the observation window.
3. Read the YES token's official CLOB price history.
4. Select the latest observed price at or before the 24-hour cutoff.
5. Record an inclusion reason for every row.
6. Compare the selected probability with the final YES or NO outcome.
7. Publish the verified summary to the dashboard payload.

The result is generated from public Polymarket endpoints and a bounded, auditable analysis pipeline.

## Live dashboard

The [dashboard](https://forecastaudit.dev) shows the headline result, probability buckets, the related-market robustness check, coverage information, analysis scope, and a linked evidence sample.

Each evidence row includes its market ID, event context, forecast timestamp, resolution timestamp, and source market URL.

## Run locally

Use Python 3.11 or a compatible recent Python version.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the dashboard with:

```bash
make serve
```

Then open [http://127.0.0.1:8050](http://127.0.0.1:8050).

## Verification

Run the complete local validation gate with:

```bash
make validate
```

The gate compiles the Python source, runs the test suite, checks public claims and tracked-secret boundaries, and confirms that the deterministic fixture build is reproducible.

The committed fixture corpus provides deterministic software-test inputs.

The public dashboard payload is generated from the verified real dataset.

## Repository map

- `static_dashboard/` contains the public dashboard shell and generated payload.
- `src/polymarket/` contains Polymarket collection, normalization, analysis, and publication code.
- `src/rebuild/` contains the validation and reproducible-build machinery.
- `src/portfolio/` contains the dashboard data contract and portfolio view helpers.
- `tests/` contains unit and integration tests for the analysis and publication paths.
- `data/fixtures/` contains small synthetic inputs used by the test suite.
- `config/` and `schemas/` define the analysis rules and data contracts.
- `scripts/refresh_dashboard_copy.py` refreshes public scope copy from the existing generated dashboard payload.

Generated research outputs and local collection data stay outside the public source tree.

## Analysis scope

- Related markets remain visible in the primary analysis and are paired with a one-market-per-event view.
- The pooled and one-event views provide complementary market-level perspectives.
- Included rows use a verified pre-resolution price within the stated snapshot-age rule.
- The analysis covers one platform and one completed calendar year.
- The Gamma category field was missing in the collected inventory and remains available as an explicit data-quality detail.
- The dashboard presents a descriptive probability-outcome comparison with linked evidence.

## Official sources

- [Polymarket markets and events](https://docs.polymarket.com/concepts/markets-events)
- [Gamma keyset market pagination](https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination)
- [CLOB price history](https://docs.polymarket.com/api-reference/markets/get-prices-history)

## License

This project is available under the MIT License.
