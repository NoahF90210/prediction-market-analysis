# Prediction Market Rebuild Handoff

## Current state

The analytical layer has been restarted around `prediction-market-calibration-2026h1-v1`.

Implemented:

- fixed 2026 H1 protocol and JSON Schemas;
- content-addressed raw response store, SHA-256 manifest, secret-metadata rejection, and deterministic build ID;
- public Polymarket and Kalshi collectors with an explicit Kalshi authentication handoff;
- fail-closed normalization for identity, binary status, resolution time, cutoff timing, staleness, provenance, multileg/parlay, conditional, complement/related role, duplicates, and post-cutoff features;
- event-total weighting and a deterministic one-contract sensitivity policy;
- event-weighted Brier/log loss, event-clustered bootstrap, always-0.5 baseline, prior-only prevalence baseline, temporal event-safe folds, and staleness/selection sensitivities;
- committed synthetic provenance-complete fixture corpus and deterministic build artifacts;
- methodology-only dashboard and rewritten README with no legacy numerical claims;
- `make validate` repository gate and CI integration (52 tests passing at handoff).
- real evaluation summaries are deliberately hard-blocked from `validated` status until a trusted manual-review verifier and atomic claims publisher are implemented.

## Real versus fixture data

- `data/fixtures/provenance_complete/` is synthetic and committed. It tests software only.
- `data/raw/rebuild*` is real public API material, local and ignored.
- `data/derived/rebuild/` is generated locally and ignored.
- `static_dashboard/data.js` is a status payload, not an analysis payload.

## Safe collection performed

On August 14, 2026:

- Polymarket public market inventory and price-history APIs returned HTTP success. The final one-page smoke run stored one inventory response but did not reach the January–June window because the complete collector starts from the newest closed markets.
- Kalshi public historical cutoff, market, and trade APIs returned HTTP success. A safety-capped run retained two 2026 H1 candidate markets and their trade-history responses; neither had a qualifying timestamped trade at the 24-hour target, so both fail closed.

No authenticated endpoint was required and no secret value was read or printed.

## August 17, 2026 full-collection attempt

The documented uncapped command was executed. It did not produce a valid corpus manifest:

- Polymarket offset pagination failed at offset 2,100 with HTTP 422 and an API instruction to use `/markets/keyset`. The collector was updated to the official `after_cursor` keyset endpoint and now retries transient 5xx responses.
- A subsequent uncapped Kalshi run exceeded 20 minutes while still scanning inventory. Before termination it had written 3,228 unique market-inventory pages containing 3,228,000 rows (8.9 GB) whose settlement timestamps covered only June 5–17, 2026. It had not reached history collection or emitted a manifest/candidate handoff.
- The incomplete ignored Kalshi directory was removed after recording the counts. No orphan collector process remains.

This establishes a concrete scalability blocker: exhaustive row-by-row collection is not operationally safe for the high-frequency inventory, and collecting trade history for millions of contracts is infeasible. The data must be deterministically sharded and prefiltered using protocol-safe fields before history retrieval, with checkpoint/resume and inventory-completeness accounting.

## Remaining work/blockers

1. Implement resumable date/cursor shards and an inventory ledger that proves complete coverage without retaining duplicate multi-gigabyte pages.
2. Add protocol-safe pre-history filters for markets that were not open 24 hours before close, explicit MVE/parlay records, and other deterministically ineligible contracts; preserve exclusion counts and provenance rather than silently dropping them.
3. Run those shards for both platforms and merge manifests deterministically.
4. Manually audit event grouping and contract relationship flags on the resulting eligible real corpus.
5. Confirm at least the predeclared independent-event minimum per platform.
6. Implement the trusted real-build verifier and atomic claims publisher; the current evaluator intentionally cannot emit `validated` for real data.
7. Only after that validation path passes, generate numerical README/dashboard claims from the verified summary.

Exact safe command now: `make validate`. The Makefile defaults to `python3` so this gate works from a clean macOS shell without a `python` alias. Do **not** rerun the uncapped collection until checkpointed sharding/prefiltering is implemented; the uncapped command is the documented blocker reproduction, not the next production step.

## Numerical claim safety

No empirical numerical claim is safe. Fixture metrics are test values and must not be published.

## Resume point

Run `make validate`, inspect `.rpiv/artifacts/prediction-market-rebuild-verification.md`, then decide whether to launch the uncapped full public collection. Do not publish, push, deploy, or edit résumé/personal-site repositories from this handoff.
