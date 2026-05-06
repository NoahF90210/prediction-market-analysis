// Mock dataset shaped to match README headline numbers:
// 906 scored markets, 365 Polymarket / 541 Kalshi
// Overall Brier 0.1185, log loss 0.3547
// Polymarket Brier 0.1127, Kalshi Brier 0.1223
// Beats 50% baseline by 53.0% on Brier, beats category base-rate by 46.9%

window.DASHBOARD_DATA = (function () {
  // Seeded RNG so the same numbers come back every load.
  let seed = 42;
  const rand = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
  const randn = () => {
    // Box-Muller
    let u = 0, v = 0;
    while (u === 0) u = rand();
    while (v === 0) v = rand();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  };
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

  const CATEGORIES = [
    { name: "sports",       weight: 0.42, brierTarget: 0.118, baseRate: 0.51 },
    { name: "elections",    weight: 0.14, brierTarget: 0.105, baseRate: 0.42 },
    { name: "politics",     weight: 0.10, brierTarget: 0.131, baseRate: 0.38 },
    { name: "geopolitics",  weight: 0.07, brierTarget: 0.142, baseRate: 0.34 },
    { name: "crypto",       weight: 0.09, brierTarget: 0.124, baseRate: 0.46 },
    { name: "commodities",  weight: 0.06, brierTarget: 0.119, baseRate: 0.49 },
    { name: "finance",      weight: 0.07, brierTarget: 0.115, baseRate: 0.47 },
    { name: "culture",      weight: 0.05, brierTarget: 0.137, baseRate: 0.41 },
  ];

  const PLATFORMS = [
    { name: "polymarket", count: 365, brierTarget: 0.1127, source: "history" },
    { name: "kalshi",     count: 541, brierTarget: 0.1223, source: "snapshot_fallback", historyShare: 0.18 },
  ];

  const SAMPLE_TITLES = {
    sports: [
      "Will the Lakers win the NBA Finals?",
      "Will Manchester City win the Premier League?",
      "Will the Chiefs reach the Super Bowl?",
      "Will Djokovic win the US Open?",
      "Will Real Madrid win La Liga?",
      "Will the Yankees make the World Series?",
      "Will Verstappen win the F1 championship?",
      "Will Liverpool finish top 4?",
      "Will the Eagles win the NFC East?",
      "Will Iga Swiatek win the French Open?"
    ],
    elections: [
      "Will Democrats hold the Senate in 2026?",
      "Will Republicans flip the House majority?",
      "Will Newsom win the gubernatorial primary?",
      "Will the Tory party win the next UK election?",
      "Will Macron's party hold a majority?",
      "Will the incumbent win the German federal election?"
    ],
    politics: [
      "Will the Supreme Court hear the antitrust case?",
      "Will Congress pass the appropriations bill by Q3?",
      "Will the President sign the trade agreement?",
      "Will the EU approve the AI act amendments?",
      "Will the new tariffs take effect this quarter?"
    ],
    geopolitics: [
      "Will a ceasefire be announced before year end?",
      "Will OPEC cut production at the next meeting?",
      "Will the trade summit conclude with an agreement?",
      "Will sanctions on the central bank be lifted?",
      "Will the territorial dispute reach UN mediation?"
    ],
    crypto: [
      "Will BTC close above $80,000 by month end?",
      "Will ETH reach $5,000 this quarter?",
      "Will the SEC approve a SOL ETF?",
      "Will stablecoin regulation pass this session?",
      "Will a major exchange file for IPO this year?"
    ],
    commodities: [
      "Will WTI crude close above $90 this month?",
      "Will gold break $2,500 in Q2?",
      "Will natural gas drop below $2 by July?",
      "Will copper reach a new all-time high this year?",
      "Will wheat futures close above $7 this month?"
    ],
    finance: [
      "Will the Fed cut rates by 25 bps in March?",
      "Will the S&P 500 close above 6,000 in 2026?",
      "Will inflation print below 3% next month?",
      "Will unemployment rise above 4.5% this quarter?",
      "Will the 10-year yield close above 5% in Q1?"
    ],
    culture: [
      "Will the album debut at #1 on Billboard?",
      "Will the film cross $1B at the global box office?",
      "Will the show win Best Drama at the Emmys?",
      "Will the artist headline Coachella next year?",
      "Will the franchise announce a sequel by Q4?"
    ],
  };

  function pickCategory() {
    const r = rand();
    let acc = 0;
    for (const c of CATEGORIES) {
      acc += c.weight;
      if (r <= acc) return c;
    }
    return CATEGORIES[0];
  }

  function pickTitle(category) {
    const pool = SAMPLE_TITLES[category] || SAMPLE_TITLES.sports;
    return pool[Math.floor(rand() * pool.length)];
  }

  function pickVolume() {
    // Long-tail volume distribution, $100k floor.
    const r = rand();
    if (r < 0.55) return 100_000 + rand() * 150_000;
    if (r < 0.85) return 250_000 + rand() * 750_000;
    if (r < 0.97) return 1_000_000 + rand() * 4_000_000;
    return 5_000_000 + rand() * 20_000_000;
  }

  function pickDuration() {
    const r = rand();
    if (r < 0.08) return rand() * 0.9 + 0.1; // <1 day
    if (r < 0.32) return 1 + rand() * 6;     // 1-7 days
    if (r < 0.70) return 7 + rand() * 23;    // 7-30 days
    if (r < 0.95) return 30 + rand() * 120;  // 30+ days
    return null;                              // unknown
  }

  // Generate a single market.
  function generateMarket(platform, idx) {
    const cat = pickCategory();
    const baseRate = cat.baseRate;
    // Underlying truth: did YES happen?
    const yesProb = clamp(baseRate + randn() * 0.18, 0.02, 0.98);
    const outcome = rand() < yesProb ? 1 : 0;

    // Forecast with calibration noise around true probability,
    // tuned so per-platform Brier hits the target.
    const platformNoise = platform.name === "polymarket" ? 0.20 : 0.235;
    let forecast = clamp(yesProb + randn() * platformNoise * 0.5, 0.005, 0.995);
    // Slight tendency to overestimate YES in mid-range (matches README finding)
    if (forecast > 0.3 && forecast < 0.75) forecast = clamp(forecast + 0.03, 0.005, 0.995);

    const volume = pickVolume();
    const days = pickDuration();
    const now = Date.now();
    const closeTime = new Date(now - rand() * 90 * 86400000);
    const openTime = days != null ? new Date(closeTime.getTime() - days * 86400000) : null;

    let source = platform.source;
    if (platform.name === "kalshi" && rand() < platform.historyShare) {
      source = "history";
    }

    return {
      id: `${platform.name}_${idx}`,
      platform: platform.name,
      category: cat.name,
      title: pickTitle(cat.name),
      forecast_prob: forecast,
      resolution: outcome ? "YES" : "NO",
      outcome,
      brier: (forecast - outcome) ** 2,
      log_loss: -((outcome * Math.log(clamp(forecast, 1e-6, 1 - 1e-6))) +
                  ((1 - outcome) * Math.log(1 - clamp(forecast, 1e-6, 1 - 1e-6)))),
      volume,
      days_to_resolution: days,
      open_time: openTime,
      close_time: closeTime,
      forecast_source: source,
    };
  }

  const rows = [];
  for (const p of PLATFORMS) {
    for (let i = 0; i < p.count; i++) rows.push(generateMarket(p, i));
  }

  // Headline numbers — bake in the README values so cards aren't drifting.
  const HEADLINE = {
    n_markets: 906,
    n_polymarket: 365,
    n_kalshi: 541,
    brier_overall: 0.1185,
    brier_polymarket: 0.1127,
    brier_kalshi: 0.1223,
    log_loss_overall: 0.3547,
    baseline_50_brier: 0.2521,        // implies 53.0% improvement
    baseline_category_brier: 0.2231,  // implies 46.9% improvement
    pct_better_than_50: 0.530,
    pct_better_than_category: 0.469,
    polymarket_ci: [0.098, 0.128],
    kalshi_ci: [0.107, 0.138],
    avg_forecast: 0.481,
    median_lead_time_days: 14.2,
    total_volume: 4.82e9,
    last_updated: "2026-04-28T16:42:00Z",
  };

  // Hand-tuned calibration buckets that match the README-described pattern
  // (mid-range buckets sit a bit below the diagonal).
  const CALIBRATION = [
    { bucket: "0–10%",   midpoint: 0.05, observed: 0.041, n: 198 },
    { bucket: "10–20%",  midpoint: 0.15, observed: 0.122, n: 122 },
    { bucket: "20–30%",  midpoint: 0.25, observed: 0.218, n: 95 },
    { bucket: "30–40%",  midpoint: 0.35, observed: 0.307, n: 78 },
    { bucket: "40–50%",  midpoint: 0.45, observed: 0.392, n: 71 },
    { bucket: "50–60%",  midpoint: 0.55, observed: 0.498, n: 69 },
    { bucket: "60–70%",  midpoint: 0.65, observed: 0.612, n: 74 },
    { bucket: "70–80%",  midpoint: 0.75, observed: 0.731, n: 81 },
    { bucket: "80–90%",  midpoint: 0.85, observed: 0.841, n: 96 },
    { bucket: "90–100%", midpoint: 0.95, observed: 0.962, n: 122 },
  ];

  // Lead-time × brier (matches "longer markets associated with lower error").
  const LEAD_TIME = [
    { bucket: "<1 day",   brier: 0.142, n: 71  },
    { bucket: "1–7 days", brier: 0.131, n: 226 },
    { bucket: "7–30 days",brier: 0.118, n: 348 },
    { bucket: "30+ days", brier: 0.097, n: 244 },
    { bucket: "unknown",  brier: 0.139, n: 17  },
  ];

  // Volume × brier (matches "higher-volume associated with lower error").
  const VOLUME = [
    { bucket: "$100k–$250k", brier: 0.131, n: 488 },
    { bucket: "$250k–$1M",   brier: 0.119, n: 264 },
    { bucket: "$1M–$5M",     brier: 0.108, n: 122 },
    { bucket: "$5M+",        brier: 0.094, n: 32  },
  ];

  // Category × platform Brier (used in the dual-bar chart).
  const CATEGORY_BREAKDOWN = [
    { category: "sports",       polymarket: 0.108, kalshi: 0.119, n_poly: 168, n_kalshi: 217 },
    { category: "elections",    polymarket: 0.094, kalshi: 0.116, n_poly: 52,  n_kalshi: 78  },
    { category: "politics",     polymarket: 0.122, kalshi: 0.139, n_poly: 38,  n_kalshi: 56  },
    { category: "geopolitics",  polymarket: 0.131, kalshi: 0.151, n_poly: 24,  n_kalshi: 41  },
    { category: "crypto",       polymarket: 0.117, kalshi: 0.131, n_poly: 35,  n_kalshi: 47  },
    { category: "commodities",  polymarket: 0.111, kalshi: 0.124, n_poly: 18,  n_kalshi: 36  },
    { category: "finance",      polymarket: 0.106, kalshi: 0.121, n_poly: 22,  n_kalshi: 41  },
    { category: "culture",      polymarket: 0.128, kalshi: 0.144, n_poly: 8,   n_kalshi: 25  },
  ];

  return {
    rows,
    headline: HEADLINE,
    calibration: CALIBRATION,
    leadTime: LEAD_TIME,
    volume: VOLUME,
    categoryBreakdown: CATEGORY_BREAKDOWN,
  };
})();
