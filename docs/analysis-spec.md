# Polymarket Calibration Rebuild Specification

Status: Phase 1 draft for Noah review.

## Research question

When Polymarket assigns a probability to a binary outcome, does that outcome happen about that often?

This is a descriptive calibration question, not a claim about trading profit, causal accuracy, or future performance.

## Observation period

The first period is January 1, 2025 00:00:00 UTC inclusive through January 1, 2026 00:00:00 UTC exclusive.

Membership is determined by the verified resolution timestamp, not only by the nominal market end date.

## Definitions

An **event** is Polymarket's container for one or more related markets.

A **market** is one Polymarket market ID representing one binary question and its YES and NO outcome tokens.

A **qualifying resolved binary market** is a market with a closed/resolved state, a credible resolution timestamp inside the period, exactly two outcomes that can be mapped to YES and NO, a valid YES token, and an auditable final outcome.

The unit of analysis is one row per unique Polymarket market ID.

The event ID is retained so related markets can be identified, but related markets are not collapsed in the primary market-level summary.

## Inclusion rules

A market is included when all of the following hold:

1. It is from Polymarket's official Gamma API.
2. It is closed and has a resolved binary outcome.
3. Its verified resolution timestamp is inside the observation period.
4. Its outcome and YES-token mappings are unambiguous.
5. Its CLOB history contains a usable YES price at or before the 24-hour cutoff.
6. The selected price is no more than 168 hours older than that cutoff.
7. Its source record and public market URL are retained.

Sports markets and proposition markets are not excluded by topic.
They must satisfy the same objective rules as every other market.

Category and tag fields are retained for coverage diagnostics and optional descriptive breakdowns, but they are not eligibility filters and do not define the headline result.
The primary analysis pools all included canonical YES/NO markets across categories.

## Exclusion rules

Exclude a candidate for a named reason when it is non-binary, unresolved, outside the period, missing a credible resolution timestamp, missing a YES token, missing usable price history, has only post-cutoff history, has a snapshot older than the maximum age, has an ambiguous outcome, or is a duplicate market ID.

No excluded candidate is silently dropped.

## Resolution timestamp hierarchy

Use the following hierarchy and record the selected field:

1. `closedTime` when it is present and represents the platform's actual closure/resolution time.
2. `umaEndDate` only when the real audit establishes that it is a final resolution timestamp for the record.
3. `endDate` only as a documented fallback when no stronger verified resolution timestamp exists.

The audit must flag disagreements between these fields.
Nominal `endDate` is not automatically treated as the outcome timestamp because the live API contains records where it differs materially from `closedTime`.

## Outcome derivation

The final outcome must be verified from the resolved market record and public market page.
For standard YES/NO markets, YES maps to 1 and NO maps to 0.
For two named outcomes, the winning outcome is mapped to YES only when the market question and public record establish that mapping unambiguously.
Terminal prices are evidence of settlement, not forecast snapshots.

## Forecast snapshot

For each market, define `snapshot_cutoff` as the verified resolution timestamp minus 24 hours.
Query the official CLOB `prices-history` endpoint for the YES token with explicit `startTs`, `endTs`, and `fidelity` parameters.
Select the latest history point whose timestamp is at or before the cutoff.

A point after the cutoff is not eligible.
A point more than 168 hours before the cutoff is excluded as too stale.
Prices must be numeric and within [0, 1].

## Duplicate and related-event rules

Deduplicate by Polymarket market ID.
Preserve one row per valid market.
Retain event ID and event title for grouping and sensitivity checks.
Markets in the same event remain separate observations in the primary output, with the related-market limitation disclosed.

## Probability buckets

Use fixed half-open ranges [0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), and [0.8, 1.0], with 1.0 included in the final bucket.

## Primary outputs

For each bucket, report market count, unique event count, average predicted probability, observed YES frequency, and the percentage-point gap.

Report overall market and event counts and retain the Brier score as a secondary methodology metric.

## Limitations

The result is descriptive for one platform and one completed year.
Related markets can make market-level rows statistically dependent.
The CLOB history is an observed market price, not a complete measure of every trader's information.
Markets with missing or stale history are excluded and their counts must remain visible.
Resolution metadata can contain inconsistent nominal dates, so the chosen timestamp and fallback logic must be auditable.
The analysis does not establish universal accuracy, causality, or a trading edge.

## Official sources

- Gamma market discovery: https://docs.polymarket.com/market-data/discover-markets
- Gamma keyset pagination: https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination
- Markets and events: https://docs.polymarket.com/concepts/markets-events
- CLOB price history: https://docs.polymarket.com/api-reference/markets/get-prices-history
