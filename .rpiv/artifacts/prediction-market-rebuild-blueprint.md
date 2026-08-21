# Prediction Market Rebuild Blueprint

## Objective

Restart the analytical layer around `prediction-market-calibration-2026h1-v1` without carrying forward any numerical claim from the quarantined 769-row payload.

## Locked decisions

- Observation window: `2026-01-01T00:00:00Z` inclusive to `2026-07-01T00:00:00Z` exclusive, using `resolved_at`.
- Forecast horizon: 24 hours before the earliest defensible boundary.
- Primary staleness cap: six hours; sensitivities at one hour, six hours, 24 hours, and 72 hours.
- Primary dependence policy: each `(platform, event_group_id)` receives total weight one.
- Sensitivity selection: one lexicographically predeclared market ID per event.
- Primary inference: event-clustered bootstrap.
- Platform estimates: descriptive only.
- Dashboard: methodology/progress state until a real corpus passes the publication gate.

## Implementation slices

1. **Protocol and schemas**
   - Add `config/research_protocol.json`.
   - Add JSON Schemas for protocol, raw manifests, analysis contracts, and evaluation summaries.
   - Document API-window rationale, timestamp semantics, leakage rules, and publication gate.

2. **Immutable collection**
   - Add content-addressed raw storage and manifest hashing.
   - Add public Polymarket Gamma/CLOB and Kalshi current/historical adapters.
   - Reject secret-like request metadata.
   - Require timestamped history; never score terminal/metadata fallbacks.

3. **Normalization and gates**
   - Normalize platform records into the analysis contract.
   - Detect multileg/parlay and conditional markets conservatively.
   - Require event identity, binary resolution, cutoff ordering, source hashes, and duplicate-free IDs.
   - Separate cutoff volume from final volume.

4. **Evaluation**
   - Implement event-total weights, Brier/log loss, event-clustered intervals, 0.5 baseline, prior-only prevalence baseline, temporal event-group folds, and sensitivity summaries.

5. **Reproducible fixture build**
   - Commit a small synthetic provenance-complete fixture corpus.
   - Generate deterministic analysis CSV/JSON and validate its hashes and schemas.
   - Provide one validation command.

6. **Dashboard and claims**
   - Replace stale `static_dashboard/data.js` with a non-result status payload.
   - Render protocol, completed gates, blockers, and the real/fixture boundary.
   - Add claim-consistency tests that prohibit unsafe historical numbers.

7. **Verification and handoff**
   - Run the full test suite, static compilation, deterministic fixture rebuild, safe public API smoke collection, and secret-boundary checks.
   - Record exact commands, outputs, changed files, blockers, and claim safety.

## Acceptance criteria

- No tracked credential or secret value.
- No old result number displayed as evidence.
- Every included fixture row traces to hashed raw market and history records.
- Missing timestamp/provenance fails closed with an explicit reason.
- Event count is reported beside contract count.
- Event-clustered intervals resample event groups, never rows.
- A clean clone can run `make validate` and reproduce fixture artifacts deterministically.
- Live collection can stop honestly with an exact credential handoff if a platform endpoint requires authentication.
