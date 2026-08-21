# Prediction Market Probability Check

[![Tests](https://github.com/NoahF90210/prediction-market-analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/NoahF90210/prediction-market-analysis/actions/workflows/tests.yml)

> **Current data status: `validated_real_sample`.** The public dashboard uses 500 resolved Polymarket contracts from the frozen 2026 H1 window, with 125 rows passing the pre-result timestamp, provenance, binary-contract, and exclusion checks across 78 event groups.
> Results are descriptive for this bounded sample only.

## The question

> **Were pre-result prediction-market probabilities informative about what happened?**

The portfolio dashboard answers that question with three views:

1. **Probability ranges vs. outcomes** — when markets said 60–80%, how often did the event actually happen?
2. **Simple accuracy and coverage** — how many rows were usable, and how often did the probability point in the correct direction at a 50% threshold?
3. **Searchable source table** — probability, outcome, timestamp, platform, title, inclusion status, and source for every submitted row.

Brier score, log loss, clustered bootstrap intervals, learned baselines, and event-weighted estimands are not required to understand the main product. The repository retains that machinery as an optional research appendix.

## Data status contract

The dashboard always exposes one of three states:

| State | Meaning |
|---|---|
| `fixture_only` | Synthetic rows are being used to test the software. No empirical claim is safe. |
| `data_pending` | A real file was supplied, but no row passed every fail-closed check. |
| `validated_real_sample` | At least one real row passed the normalized contract. Results are descriptive only for that bounded sample. |

Even `validated_real_sample` does **not** support a platform ranking, causal claim, population estimate, or trading-edge claim.

## Current bounded result

The current public build includes 125 of 500 submitted rows, for 25.0% coverage.

The simple 50% direction check is correct for 64.8% of included rows.

The included rows have a 27.2% observed YES rate and a 38.1% average submitted probability.

The unclustered Brier appendix value is 0.162 against an always-50% reference value of 0.250.

These values are descriptive summaries of this bounded Polymarket sample.

They are not evidence that prediction markets are universally accurate, that Polymarket outperforms another platform, or that a trading strategy has an edge.

The source table keeps excluded rows visible with their gate reasons.

## Bounded real-data import

The default portfolio path supports one platform first: **Polymarket**. It accepts a user-supplied normalized `.csv` or `.json` file, validates every row, keeps invalid rows as explicit exclusions, and writes deterministic artifacts.

Required fields for an included row:

| Field | Contract |
|---|---|
| `platform` | Must be `polymarket` |
| `market_id` | Stable market identifier |
| `event_id` | Optional; defaults to `market_id` |
| `title` | Human-readable market question |
| `source_url` | HTTPS market or source URL |
| `source_endpoint` | HTTPS API endpoint or evidence URL; defaults to `source_url` |
| `probability` | Number from 0 through 1 |
| `probability_timestamp` | UTC-compatible timestamp observed before resolution |
| `outcome` | `YES`/`NO`, `1`/`0`, or boolean |
| `resolution_timestamp` | UTC-compatible resolution timestamp |
| `outcome_source` | Resolution source URL or clear source description |
| `retrieved_at` | Optional retrieval timestamp |

Example JSON:

```json
{
  "scope": "Twenty resolved Polymarket markets selected by a documented bounded rule.",
  "rows": [
    {
      "platform": "polymarket",
      "market_id": "12345",
      "event_id": "event-987",
      "title": "Will the event happen?",
      "source_url": "https://polymarket.com/event/example",
      "source_endpoint": "https://gamma-api.polymarket.com/markets/12345",
      "probability": 0.64,
      "probability_timestamp": "2026-06-01T12:00:00Z",
      "outcome": "YES",
      "resolution_timestamp": "2026-06-02T12:00:00Z",
      "outcome_source": "https://polymarket.com/event/example",
      "retrieved_at": "2026-06-03T12:00:00Z"
    }
  ]
}
```

Build a real bounded sample:

```bash
python3 -m src.portfolio.cli import-normalized \
  --input path/to/polymarket_sample.json
```

Generated artifacts:

- `data/derived/portfolio/portfolio_rows.json`
- `data/derived/portfolio/portfolio_rows.csv`
- `data/derived/portfolio/portfolio_summary.json`
- `static_dashboard/data.js`

Each output row includes the input file SHA-256, deterministic build ID, `inclusion_status`, and `exclusion_reasons`.

## Fail-closed checks

A row is excluded rather than guessed when it has:

- a malformed row shape;
- a missing or unsupported platform;
- a missing market ID or title;
- a missing or invalid HTTPS source;
- a missing or invalid probability;
- a missing probability or resolution timestamp;
- a probability timestamp at or after resolution;
- a missing outcome or outcome source;
- a duplicate platform/market identifier.

Excluded rows remain visible in the table and count against coverage.

## Main analysis

For included rows, the compact analysis calculates:

- five fixed probability ranges: 0–20%, 20–40%, 40–60%, 60–80%, and 80–100%;
- the average probability in each range;
- the observed YES rate in each range;
- directional hit rate using a stated 50% threshold;
- submitted, included, and excluded row counts;
- missing-data coverage and exclusion reasons.

The optional technical appendix reports Brier score and the plain always-50% baseline. More complex research methods stay isolated under `src/rebuild/` and are not part of the default public story.

## Reproduce the fixture-only dashboard

```bash
python3 -m src.portfolio.cli build-fixture
```

The fixture source is `data/fixtures/portfolio_normalized.json`. Its probabilities and outcomes are synthetic test values, not empirical findings.

## Run locally

```bash
python3 app.py
```

Open `http://127.0.0.1:8050`.

## Validate

```bash
make validate
```

Validation runs Python compilation, the full test suite, repository claim checks, both deterministic fixture paths, and schema/provenance checks.

## Project structure

### Default portfolio path

- `src/portfolio/contracts.py` — CSV/JSON loading, normalization, timestamps, inclusion status, duplicates, and deterministic build IDs
- `src/portfolio/analysis.py` — probability ranges, observed rates, hit rate, coverage, and optional simple baseline
- `src/portfolio/pipeline.py` — schema validation and deterministic JSON/CSV/dashboard artifacts
- `src/portfolio/cli.py` — `build-fixture` and `import-normalized`
- `schemas/portfolio-market.schema.json` — normalized output contract
- `tests/test_portfolio_pipeline.py` — deterministic and malformed-row coverage
- `static_dashboard/` — compact three-view React dashboard

### Optional research appendix

- `src/rebuild/` — content-addressed API provenance, fixed-horizon snapshot selection, event grouping, clustered uncertainty, and research publication gates
- `data/fixtures/provenance_complete/` — synthetic provenance fixture for the research path
- `docs/research_protocol.md` — advanced protocol details

## Claim boundary

The repository currently supports a software and methodology claim only:

> Built a deterministic Python and React workflow that validates bounded prediction-market rows, fails closed on missing or post-result evidence, summarizes probability ranges against outcomes, reports coverage, and keeps source-level records auditable.

It does not currently support a numerical claim about real market accuracy.
