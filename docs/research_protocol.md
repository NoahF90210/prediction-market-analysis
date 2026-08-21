# Research Protocol: 2026 H1 Prediction-Market Calibration

Protocol ID: `prediction-market-calibration-2026h1-v1`
Schema version: `1.0.0`

## Research question

> Among independently grouped, non-parlay binary contracts that resolved during a fixed six-month observation window and had a verifiable market price 24 hours before trading closed, how well calibrated were Polymarket and Kalshi probabilities, measured with event-weighted Brier score and event-clustered uncertainty?

Platform results are descriptive. A direct platform comparison is out of scope until the same underlying events can be matched across platforms.

## Fixed observation window

The window is **January 1, 2026 00:00:00 UTC (inclusive) through July 1, 2026 00:00:00 UTC (exclusive)**. Membership is determined by `resolved_at`, not by a nominal end date.

This window was frozen on August 14, 2026 because:

1. it is exactly six completed calendar months and ends more than six weeks before collection;
2. Polymarket's public Gamma inventory and CLOB price-history endpoints were reachable for the period;
3. Kalshi's public historical cutoff endpoint reported a June 15, 2026 cutoff, and both historical and current settled-market/trade endpoints were reachable, so the collector can deterministically merge January 1–June 14 historical records with June 15–June 30 current records;
4. the lag reduces the chance that contracts near the window end are still awaiting settlement metadata.

API availability is not evidence quality. Every included row still has to pass the provenance, timing, independence, and leakage gates below.

## Estimand

The primary estimand is the mean contract loss after assigning each `(platform, event_group_id)` total weight one. If an event contributes `k` eligible contracts, each contract receives weight `1/k`. This prevents a many-contract event from dominating a platform estimate.

The primary metrics are:

- event-weighted Brier score;
- event-weighted log loss;
- percentile intervals from resampling whole event groups.

The report must display both contract count and independent event count.

## Forecast definition

For each contract:

1. Define the forecast boundary as the earliest available defensible timestamp in this order: actual trading close, event start, scheduled close, resolution.
2. Set `forecast_target_at = forecast_boundary_at - 24 hours`.
3. Select the latest verifiable trade or sampled market-history price with `forecast_observed_at <= forecast_target_at`.
4. The primary corpus requires snapshot staleness of at most six hours. Sensitivity analyses use one hour, six hours, 24 hours, and 72 hours.
5. Preserve valid probabilities at 0 or 1. Probability-based filtering is prohibited.
6. Metadata bid/ask/last fields observed only after settlement, and terminal settlement prices, are never forecast snapshots.

## Population and identity

Required identities are `platform`, `market_id`, `event_id`, and `event_group_id`; `series_id` is retained when available. Event grouping is platform-native unless a separately reviewed matched-event map exists.

Included contracts must be:

- binary YES/NO contracts;
- resolved inside the fixed window;
- non-parlay and non-multileg;
- non-conditional for the primary analysis;
- linked to immutable market, history, and resolution evidence;
- observed at or before the 24-hour target within the active staleness threshold.

Complementary and mutually exclusive contracts may remain only under the event-total-weight policy. If their relationship cannot be resolved deterministically, they fail closed.

## Liquidity semantics

`cutoff_volume` and `final_volume` are separate fields.

- `cutoff_volume` must be derived from information observed no later than `forecast_target_at`.
- `final_volume` is retained only as descriptive post-period metadata.
- `final_volume` cannot be a selection rule, model feature, or learned-baseline feature.
- Missing cutoff-time volume does not exclude an otherwise valid contract because liquidity is not part of the estimand.

## Provenance contract

Every raw response is serialized canonically, addressed by SHA-256, and retained immutably. The manifest records:

- non-secret endpoint and request parameters;
- retrieval timestamp;
- raw response path and SHA-256;
- byte length;
- raw schema version;
- collector commit;
- deterministic build ID.

Request metadata containing credential-like keys is rejected before writing. Missing raw market or history evidence excludes the row. A hash mismatch invalidates the build.

## Inclusion and exclusion

The machine-readable exclusion enum is defined in `schemas/analysis-contract.schema.json`. Gates accumulate explicit reasons rather than silently dropping rows. Important reasons include missing identity, non-binary, multileg/parlay, conditional, missing resolution time, missing cutoff evidence, snapshot after cutoff, stale snapshot, metadata/terminal fallback, missing provenance, duplicate IDs, unresolved complements, and post-cutoff features.

## Baselines and validation

Required baselines:

- always 0.5;
- historical platform/category prevalence computed only from earlier event groups.

Any learned baseline must use expanding temporal folds with event groups kept intact. Encoders and all preprocessing must be fit inside each training fold. No learned baseline is required for the first release.

## Publication gate

Headline metrics are publishable only when:

- all raw hashes verify;
- every included row passes every gate;
- each platform has at least 50 independent events;
- generated README/dashboard claims exactly match the validated summary artifact;
- validation status is `validated`, not `fixture_only` or `blocked`.

Until then, the dashboard must show methodology and progress only.

## Reproducibility boundary

`tests/fixtures/provenance_complete/` is a deterministic synthetic corpus used to verify the build and evaluation machinery. Fixture metrics are test outputs, never empirical findings. Live raw responses belong under ignored `data/raw/rebuild/`; derived local outputs belong under ignored `data/derived/rebuild/`. The committed dashboard payload contains only project status until a real corpus clears the publication gate.
