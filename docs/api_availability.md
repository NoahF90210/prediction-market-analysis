# API Availability Record

Checked without private credentials on **August 14, 2026**.

## Polymarket

- Gamma closed-event inventory: `https://gamma-api.polymarket.com/events`
- CLOB price history: `https://clob.polymarket.com/prices-history`
- Official price-history reference: `https://docs.polymarket.com/api-reference/markets/get-prices-history`

The inventory endpoint returned resolved market records with `closedTime`, `umaEndDate`, `umaResolutionStatus`, binary outcomes, token IDs, and final volume fields. The collector filters locally by resolution timestamp because nominal `endDate` is not a reliable resolution timestamp.

## Kalshi

- Historical cutoff: `https://api.elections.kalshi.com/trade-api/v2/historical/cutoff`
- Historical markets/trades: `https://api.elections.kalshi.com/trade-api/v2/historical/markets` and `/historical/trades`
- Current markets/trades: `https://api.elections.kalshi.com/trade-api/v2/markets` and `/markets/trades`
- Official references:
  - `https://docs.kalshi.com/api-reference/historical/get-historical-cutoff-timestamps`
  - `https://docs.kalshi.com/api-reference/historical/get-historical-markets`
  - `https://docs.kalshi.com/api-reference/historical/get-historical-trades`

The cutoff response reported `2026-06-15T00:00:00Z` for settled markets and trades. The rebuild therefore merges historical endpoints before that cutoff with current endpoints on and after it, then filters locally to the frozen 2026 H1 resolution window. Public smoke requests returned HTTP 200 without reading repository credentials. Collectors still support an explicit credential-required failure if platform policy changes.
