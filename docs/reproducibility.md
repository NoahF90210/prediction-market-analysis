# Reproducibility and Environment

## Supported environment

- Python: `3.11`
- Operating systems: Linux/macOS
- Dependency versions: pinned in `requirements.txt`
- Locale/timezone: all protocol and analytical timestamps are normalized to UTC

Create an isolated environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The rebuild modules do not open `.env`. Optional legacy integrations read credentials only from the process environment. Validation never prints credential values.

## Deterministic fixture boundary

The committed fixture corpus is under `data/fixtures/provenance_complete/`:

- `manifest.json` — deterministic build identity and immutable response index;
- `candidate_records.json` — normalized collector handoff with provenance references;
- `raw/` — content-addressed synthetic market and history responses.

Run:

```bash
python -m src.rebuild.cli build-fixture
```

The command validates the protocol schema, manifest schema, every raw hash, every analysis-row schema, and the evaluation-summary schema before writing local artifacts under `data/derived/rebuild/`. Running it twice with the same source produces byte-identical JSON and CSV outputs.

Fixture outputs are labeled `fixture_only`. They validate the software, not the research result.

## Repository validation

Run the complete local gate:

```bash
make validate
```

This executes:

1. Python bytecode compilation for `src/`, `tests/`, and `app.py`;
2. the full pytest suite;
3. tracked-secret boundary checks;
4. quarantined-claim and dashboard-status checks;
5. two independent fixture builds with SHA-256 comparison;
6. a final deterministic fixture build in `data/derived/rebuild/`.

## Public API collection

Safety-capped smoke commands:

```bash
python -m src.rebuild.cli collect --platform polymarket \
  --output data/raw/rebuild-smoke-polymarket --max-pages 1 --max-markets 2

python -m src.rebuild.cli collect --platform kalshi \
  --output data/raw/rebuild-smoke-kalshi --max-pages 1 --max-markets 2
```

The former uncapped command is now a recorded blocker reproduction and must not be rerun: it produced 3,228 Kalshi pages / 3,228,000 rows / 8.9 GB while covering only June 5–17, 2026 before timeout.

The precise future interface to implement and review is:

```bash
python -m src.rebuild.cli collect-sharded --platform both \
  --output data/raw/rebuild-sharded --shard-days 1 --resume
```

`collect-sharded` is not available yet. It must checkpoint cursors, emit a deterministic inventory ledger, preserve exclusion counts, and collect history only after protocol-safe prefilters. Until then, run `make validate`; do not launch unbounded collection.

Polymarket collection paginates the complete closed market inventory in descending close-time order and filters locally by verified resolution timestamp. It does not use nominal end-date filters as population membership evidence.

Kalshi collection records the live historical cutoff, merges historical and current settled inventories, filters locally by settlement timestamp, and chooses the historical or current trade endpoint based on the forecast target.

## Authentication handoff

The checked public endpoints did not require private credentials on August 14, 2026. If Kalshi returns HTTP 401 or 403, collection stops with `CredentialRequiredError`. To continue, provide a `KalshiAuthenticator` implementation whose `headers(method, api_path)` method returns signed `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP`, and `KALSHI-ACCESS-SIGNATURE` headers. Keep key material outside git and never pass private keys on the command line.

No fallback data is generated when authentication is unavailable.

## Live-data publication sequence

A real build is not publishable merely because collection finishes. The remaining sequence is:

1. verify manifest hashes;
2. normalize and inspect every exclusion reason;
3. audit event groups, complements, related sets, multileg, and conditional flags;
4. confirm every included snapshot timestamp and staleness;
5. reach the predeclared independent-event minimum per platform;
6. run sensitivity analyses;
7. implement and run the trusted real-build verifier and atomic claims publisher (the current evaluator intentionally hard-blocks real summaries as `blocked`);
8. let that publisher generate README/dashboard claims from one verified summary;
9. run `make validate` again.

## Dashboard

Serve the current non-result dashboard with:

```bash
python app.py
```

The static payload intentionally omits metric arrays and row-level results while validation status is blocked.
