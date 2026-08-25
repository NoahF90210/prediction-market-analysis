# Prediction Market Probability Check

A reproducible analysis of whether Polymarket's pre-result YES probabilities matched what actually happened.

**Takeaway: in the pooled market view, 24-hour probabilities were close overall, with the largest miss in the middle range.**

Twenty-four hours before resolution, Polymarket probabilities were broadly informative, especially at the extremes.
The largest weakness was the middle range, where markets predicted YES about 49% of the time but YES happened about 40% of the time.

## The question

> When Polymarket says an outcome has a certain probability, does that outcome happen about that often?

This project uses a simple, understandable test.
It compares the probability observed 24 hours before resolution with the final YES or NO outcome.

## Result in one sentence

Across **75,036 qualifying YES/NO markets** resolved during 2025, the average predicted YES probability was **27.1%**, while YES occurred **24.6%** of the time.

The largest mismatch appeared in the 40% to 60% range, where markets predicted YES about **49.4%** of the time but YES occurred about **39.8%** of the time.

The careful conclusion is that Polymarket's 24-hour probabilities were **broadly informative**, not that every probability was perfectly accurate.

## Dataset

The analysis uses Polymarket records resolved between **January 1, 2025 00:00 UTC** and **January 1, 2026 00:00 UTC**, with the end boundary exclusive.

The inventory contained **1,495,875 unique market IDs** after keyset pagination and deduplication.

The analytical candidate set contained **92,875 canonical YES/NO markets** with resolved outcomes and verified `closedTime` values inside the window.

The final included dataset contains **75,036 markets across 14,678 events** after requiring a usable pre-resolution price snapshot.

Named-outcome markets such as `Texas/ASU`, `Over/Under`, and `Up/Down` were excluded rather than guessed into a YES/NO mapping.

Categories were not used as eligibility filters.

The raw Gamma category field was missing in this inventory, but raw tags are retained for future descriptive analysis.

## What the numbers mean

- **Average prediction** is the average YES probability assigned by Polymarket within a probability range.
- **Observed YES frequency** is the share of those markets that ultimately resolved YES.
- **Gap** is observed YES frequency minus average prediction.
- A negative gap means YES happened less often than predicted.
- A positive gap means YES happened more often than predicted.

## Probability buckets

| Probability range | Markets | Average prediction | Observed YES frequency | Gap |
|---|---:|---:|---:|---:|
| 0% to under 20% | 38,153 | 3.64% | 3.00% | -0.64 percentage points |
| 20% to under 40% | 13,025 | 28.66% | 25.32% | -3.34 percentage points |
| 40% to under 60% | 14,139 | 49.35% | 39.77% | -9.58 percentage points |
| 60% to under 80% | 3,750 | 69.01% | 71.65% | +2.64 percentage points |
| 80% to 100% | 5,969 | 94.64% | 95.31% | +0.67 percentage points |

The low and high probability ranges are relatively close to their observed frequencies.
The middle range shows the largest market-level overprediction of YES.

Here is the 40% to 60% bucket in plain English.
We found 14,139 markets where the forecast put YES somewhere between 40% and 60%.
Averaging those individual forecasts gives 49.4%, so these markets were basically saying “about a coin flip.”
YES actually happened in 39.8% of them, or about 4 out of 10.

## Related-market robustness check

Markets are grouped into Polymarket events, and one event can contain many related markets.

The primary result gives every qualifying market one row of weight.

A simple robustness check selects one deterministic market per event.

| Analysis | Markets | Average prediction | Observed YES frequency | Gap |
|---|---:|---:|---:|---:|
| All qualifying markets | 75,036 | 27.10% | 24.58% | -2.53 percentage points |
| One market per event | 14,678 | 37.13% | 37.98% | +0.84 percentage points |

This changes the sign of the overall gap.

The appropriate conclusion is therefore not that Polymarket has one universal calibration number.

The defensible conclusion is that the market-level result is sensitive to how related markets are weighted, with the clearest mismatch appearing in the middle probability range of the pooled market analysis.

## Method

1. Enumerate the closed Polymarket market inventory through the official Gamma keyset endpoint.
2. Keep canonical YES/NO markets whose verified `closedTime` falls inside the 2025 UTC window.
3. Use the YES token's official CLOB price history.
4. Select the latest observed price at or before 24 hours before `closedTime`.
5. Exclude missing or more-than-168-hour-stale snapshots with explicit reasons.
6. Compare the selected probability with the final YES or NO outcome.

The primary result is descriptive.
It is not a claim about trading profit, causality, universal accuracy, or future performance.

## Limitations

- Related markets from the same event remain separate in the primary analysis.
- The one-market-per-event check shows that weighting choices matter.
- Markets with missing or stale price history are excluded from the final analysis.
- The analysis covers one platform and one completed calendar year.
- The Gamma category field was missing in the collected inventory.
- Named outcomes were excluded rather than mapped heuristically.

## Dashboard

Run the local dashboard with:

```bash
python3 app.py
```

Then open [http://127.0.0.1:8050](http://127.0.0.1:8050).

The dashboard presents the headline result, bucket comparison, robustness check, exclusion summary, limitations, and a small linked evidence sample.

## Reproducibility artifacts

The repository tracks the compact publication outputs used by the README and dashboard.

- `config/analysis.json` contains the approved analytical rules.
- `data/results/summary.json` contains the primary summary.
- `data/results/probability_buckets.csv` contains the primary bucket result.
- `data/results/robustness_one_market_per_event.json` contains the event-level robustness check.
- `data/results/data_quality.json` contains reconciled quality totals.
- `static_dashboard/data.js` contains the generated dashboard payload.

The complete normalized rows, exclusion ledger, raw API responses, and checkpoints remain local evidence artifacts because they are large collection outputs.
They are recorded and hashed in the local freeze artifact at `.hermes/artifacts/polymarket-dataset-freeze.md`.

## Official sources

- [Polymarket markets and events](https://docs.polymarket.com/concepts/markets-events)
- [Gamma keyset market pagination](https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination)
- [CLOB price history](https://docs.polymarket.com/api-reference/markets/get-prices-history)

## Validation

```bash
make validate
```

The current local validation suite passes with 82 tests.
