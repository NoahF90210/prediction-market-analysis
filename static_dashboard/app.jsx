// Analytics dashboard for prediction market accuracy.
// Compact header, KPI row, methodology + interpretation panels, calibration chart,
// platform CI chart, structural-factor bar charts, filterable + sortable audit table.

const { useState, useMemo, useEffect } = React;

const THEME = {
  bg:        "#f8fafc",
  surface:   "#ffffff",
  surfaceAlt:"#f1f5f9",
  border:    "#e2e8f0",
  borderStrong: "#cbd5e1",
  ink:       "#0f172a",
  inkSoft:   "#334155",
  muted:     "#64748b",
  mutedSoft: "#94a3b8",
  accent:    "#2563eb",
  accentSoft:"#dbeafe",
  good:      "#15803d",
  warn:      "#b45309",
};

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------
const fmt = {
  num: (v, d = 3) => Number.isFinite(v) ? v.toFixed(d) : "—",
  pct: (v, d = 1) => Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : "—",
  money: (v) => {
    if (!Number.isFinite(v)) return "—";
    if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
    if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
    return `$${v.toFixed(0)}`;
  },
  count: (v) => v.toLocaleString(),
  date: (v) => {
    const d = new Date(v);
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  },
};

const PLATFORM_ORDER = ["polymarket", "kalshi"];

const setsEqual = (a, b) => (
  a.size === b.size && [...a].every((value) => b.has(value))
);

// ---------------------------------------------------------------------------
// KPI card — compact, single-row metric block.
// ---------------------------------------------------------------------------
function KpiCard({ label, value, sublabel, hint, accent }) {
  return (
    <div style={{
      background: THEME.surface,
      border: `1px solid ${THEME.border}`,
      borderRadius: 6,
      padding: "14px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 4,
      minWidth: 0,
    }}>
      <div style={{
        fontSize: 11,
        color: THEME.muted,
        fontWeight: 500,
        letterSpacing: "0.02em",
        textTransform: "uppercase",
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 22,
        lineHeight: 1.1,
        color: accent || THEME.ink,
        fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
      }}>
        {value}
      </div>
      {sublabel && (
        <div style={{ fontSize: 12, color: THEME.muted }}>{sublabel}</div>
      )}
      {hint && (
        <div style={{ fontSize: 11, color: THEME.mutedSoft, marginTop: 2 }}>{hint}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section header — small, compact, no decorative kickers.
// ---------------------------------------------------------------------------
function SectionHeader({ title, subtitle, right }) {
  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "flex-end",
      gap: 16,
      marginBottom: 12,
    }}>
      <div style={{ minWidth: 0 }}>
        <h2 style={{
          fontSize: 16,
          fontWeight: 600,
          color: THEME.ink,
          margin: 0,
          letterSpacing: "-0.005em",
        }}>{title}</h2>
        {subtitle && (
          <div style={{ fontSize: 13, color: THEME.muted, marginTop: 4, lineHeight: 1.5 }}>
            {subtitle}
          </div>
        )}
      </div>
      {right}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card — neutral surface with thin border.
// ---------------------------------------------------------------------------
function Card({ children, padding = 16, style }) {
  return (
    <div style={{
      background: THEME.surface,
      border: `1px solid ${THEME.border}`,
      borderRadius: 6,
      padding,
      ...style,
    }}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter chip — a small tappable pill.
// ---------------------------------------------------------------------------
function FilterChip({ label, count, active, onClick }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "5px 10px",
        border: `1px solid ${active ? THEME.accent : THEME.border}`,
        background: active ? THEME.accent : THEME.surface,
        color: active ? "#fff" : THEME.inkSoft,
        fontSize: 12,
        fontWeight: 500,
        cursor: "pointer",
        borderRadius: 4,
        textTransform: "capitalize",
      }}
    >
      <span>{label}</span>
      {count != null && (
        <span style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          opacity: 0.85,
          fontVariantNumeric: "tabular-nums",
        }}>
          {count}
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main app
// ---------------------------------------------------------------------------
function App() {
  const compact = false;

  const data = window.DASHBOARD_DATA;
  const { headline, calibration, leadTime, volume, categoryBreakdown, rows } = data;

  // Derive truths from data so claims stay honest.
  const platformCounts = useMemo(() => {
    const m = {};
    for (const r of rows) m[r.platform] = (m[r.platform] || 0) + 1;
    return m;
  }, [rows]);

  const platformOptions = useMemo(() => {
    const known = PLATFORM_ORDER.filter((p) => platformCounts[p]);
    const extra = Object.keys(platformCounts)
      .filter((p) => !PLATFORM_ORDER.includes(p))
      .sort((a, b) => platformCounts[b] - platformCounts[a]);
    return [...known, ...extra];
  }, [platformCounts]);

  const categoryCounts = useMemo(() => {
    const m = {};
    for (const r of rows) m[r.category] = (m[r.category] || 0) + 1;
    return m;
  }, [rows]);

  const distinctCategories = useMemo(() => (
    Object.keys(categoryCounts).sort((a, b) => categoryCounts[b] - categoryCounts[a])
  ), [categoryCounts]);

  const kalshiHistoryShare = headline.kalshi_history_share ?? 0;
  const brierImprovement50 = headline.pct_better_than_50 ?? (
    (headline.baseline_50_brier - headline.brier_overall) / headline.baseline_50_brier
  );
  const gbmImprovement = headline.pct_better_than_gbm ?? (
    (headline.baseline_gbm_brier - headline.brier_overall) / headline.baseline_gbm_brier
  );

  // Categories with enough sample on at least one side; used in the by-category chart
  // so a single n=1 row can't dominate the comparison.
  const MIN_CAT_N = 10;
  const categoryBreakdownRobust = useMemo(() => (
    categoryBreakdown
      .map((d) => ({
        ...d,
        polymarketShown: (d.n_polym ?? 0) >= MIN_CAT_N,
        kalshiShown:     (d.n_kalsh ?? 0) >= MIN_CAT_N,
      }))
      .filter((d) => d.polymarketShown || d.kalshiShown)
  ), [categoryBreakdown]);
  const sparseCategoryNotes = useMemo(() => (
    categoryBreakdown
      .flatMap((d) => {
        const notes = [];
        if ((d.n_polym ?? 0) < MIN_CAT_N) notes.push(`Polymarket · ${d.category} (n=${d.n_polym ?? 0})`);
        if ((d.n_kalsh ?? 0) < MIN_CAT_N) notes.push(`Kalshi · ${d.category} (n=${d.n_kalsh ?? 0})`);
        return notes;
      })
  ), [categoryBreakdown]);

  // Filter state
  const [activePlatforms, setActivePlatforms] = useState(() => new Set(platformOptions));
  const [activeCategories, setActiveCategories] = useState(() => new Set(distinctCategories));
  const [tableSearch, setTableSearch] = useState("");
  const [sortKey, setSortKey] = useState("brier");
  const [sortDir, setSortDir] = useState("desc");
  const [tableLimit, setTableLimit] = useState(25);

  const activePlatformRows = useMemo(() => (
    rows.filter((r) => activePlatforms.has(r.platform))
  ), [rows, activePlatforms]);

  const categoryCountsForActivePlatforms = useMemo(() => {
    const m = {};
    for (const r of activePlatformRows) m[r.category] = (m[r.category] || 0) + 1;
    return m;
  }, [activePlatformRows]);

  const visibleCategories = useMemo(() => (
    distinctCategories.filter((c) => (categoryCountsForActivePlatforms[c] || 0) > 0)
  ), [distinctCategories, categoryCountsForActivePlatforms]);

  const visibleCategorySet = useMemo(() => new Set(visibleCategories), [visibleCategories]);

  const allPlatformsSelected = platformOptions.length > 0
    && platformOptions.every((p) => activePlatforms.has(p));

  const allVisibleCategoriesSelected = visibleCategories.length > 0
    && visibleCategories.every((c) => activeCategories.has(c));

  const categoriesForPlatforms = (platformSet) => {
    const counts = {};
    for (const r of rows) {
      if (platformSet.has(r.platform)) counts[r.category] = (counts[r.category] || 0) + 1;
    }
    return distinctCategories.filter((c) => (counts[c] || 0) > 0);
  };

  const updatePlatformFilter = (nextPlatforms) => {
    const currentVisible = categoriesForPlatforms(activePlatforms);
    const nextVisible = categoriesForPlatforms(nextPlatforms);
    const currentWasAllCategories = currentVisible.length > 0
      && currentVisible.every((c) => activeCategories.has(c));
    const selectedNextCategories = new Set([...activeCategories].filter((c) => nextVisible.includes(c)));

    setActivePlatforms(nextPlatforms);
    setActiveCategories(
      currentWasAllCategories || selectedNextCategories.size === 0
        ? new Set(nextVisible)
        : selectedNextCategories
    );
  };

  const selectAllPlatforms = () => {
    updatePlatformFilter(new Set(platformOptions));
  };

  const selectPlatform = (platform) => {
    updatePlatformFilter(new Set([platform]));
  };

  const selectAllCategories = () => {
    setActiveCategories(new Set(visibleCategories));
  };

  const toggleCategory = (category) => {
    setActiveCategories((prev) => {
      const selectedVisible = new Set([...prev].filter((c) => visibleCategorySet.has(c)));
      const hadAllVisible = visibleCategories.length > 0
        && visibleCategories.every((c) => selectedVisible.has(c));

      if (hadAllVisible) return new Set([category]);
      if (selectedVisible.has(category)) selectedVisible.delete(category);
      else selectedVisible.add(category);
      return selectedVisible.size ? selectedVisible : new Set(visibleCategories);
    });
  };

  const resetAuditFilters = () => {
    setActivePlatforms(new Set(platformOptions));
    setActiveCategories(new Set(distinctCategories));
    setTableSearch("");
    setTableLimit(25);
  };

  useEffect(() => {
    setActivePlatforms((prev) => {
      const valid = new Set([...prev].filter((p) => platformOptions.includes(p)));
      const next = valid.size ? valid : new Set(platformOptions);
      return setsEqual(prev, next) ? prev : next;
    });
  }, [platformOptions]);

  useEffect(() => {
    setActiveCategories((prev) => {
      const valid = new Set([...prev].filter((c) => distinctCategories.includes(c)));
      const next = valid.size ? valid : new Set(distinctCategories);
      return setsEqual(prev, next) ? prev : next;
    });
  }, [distinctCategories]);

  useEffect(() => {
    setTableLimit(25);
  }, [activePlatforms, activeCategories, tableSearch, sortKey, sortDir]);

  // Filtered population, used both for the row count and the table.
  const filteredRows = useMemo(() => {
    return activePlatformRows
      .filter((r) => activeCategories.has(r.category))
      .filter((r) => !tableSearch || r.title.toLowerCase().includes(tableSearch.toLowerCase()));
  }, [activePlatformRows, activeCategories, tableSearch]);

  const sortedRows = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const key = sortKey;
    const arr = [...filteredRows];
    arr.sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      if (typeof av === "string") return dir * av.localeCompare(bv);
      return dir * ((av ?? 0) - (bv ?? 0));
    });
    return arr;
  }, [filteredRows, sortKey, sortDir]);

  const tableRows = sortedRows.slice(0, tableLimit);

  const onSort = (key) => {
    if (key === sortKey) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  // Aggregate Brier on the filtered slice so users can see how filters move the metric.
  const filteredBrier = useMemo(() => {
    if (!filteredRows.length) return null;
    const sum = filteredRows.reduce((s, r) => s + (r.brier ?? 0), 0);
    return sum / filteredRows.length;
  }, [filteredRows]);

  // ---------------------------------------------------------------------------
  // Layout primitives
  // ---------------------------------------------------------------------------
  const wrapperStyle = {
    background: THEME.bg,
    color: THEME.ink,
    minHeight: "100vh",
    fontFamily: "'Inter Tight', system-ui, sans-serif",
    fontSize: 14,
  };

  const containerStyle = {
    maxWidth: 1280,
    margin: "0 auto",
    padding: compact ? "16px 24px" : "24px 32px",
  };

  const sectionGap = compact ? 24 : 32;

  return (
    <div style={wrapperStyle}>
      {/* ============================================================ */}
      {/* HEADER                                                        */}
      {/* ============================================================ */}
      <header style={{
        background: `linear-gradient(135deg, ${THEME.surface} 0%, ${THEME.surface} 58%, ${THEME.accentSoft} 100%)`,
        borderBottom: `1px solid ${THEME.border}`,
      }}>
        <div style={{ ...containerStyle, padding: compact ? "18px 24px" : "34px 32px 28px" }}>
          <div className="hero-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.7fr) minmax(280px, 0.8fr)", gap: 24, alignItems: "stretch" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "5px 9px",
                border: `1px solid ${THEME.border}`,
                borderRadius: 999,
                background: "rgba(255,255,255,0.75)",
                fontSize: 11,
                fontWeight: 700,
                color: THEME.accent,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                marginBottom: 14,
              }}>
                Public forecast audit
              </div>
              <h1 style={{
                fontSize: "clamp(30px, 5vw, 42px)",
                lineHeight: 1.02,
                fontWeight: 700,
                margin: 0,
                color: THEME.ink,
                letterSpacing: "-0.04em",
                maxWidth: 850,
              }}>
                Were prediction markets accurate before outcomes were known?
              </h1>
              <div style={{ fontSize: 17, color: THEME.inkSoft, marginTop: 14, maxWidth: 840, lineHeight: 1.55 }}>
                This dashboard scores {fmt.count(headline.n_markets)} resolved, $100k+ volume contracts using the last non-trivial YES price at least 30 minutes before close. Market probabilities scored {headline.brier_overall.toFixed(4)} Brier, {fmt.pct(brierImprovement50)} lower error than an always-50% forecast in this sports-heavy sample.
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 18 }}>
                {[
                  ["#methodology", "Understand the pre-close rule"],
                  ["#calibration", "Check calibration"],
                  ["#contracts", "Audit contracts"],
                ].map(([href, label]) => (
                  <a
                    key={href}
                    href={href}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "8px 11px",
                      borderRadius: 6,
                      border: `1px solid ${THEME.borderStrong}`,
                      background: THEME.surface,
                      color: THEME.inkSoft,
                      textDecoration: "none",
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    {label}
                  </a>
                ))}
              </div>
            </div>
            <div style={{
              background: "rgba(255,255,255,0.84)",
              border: `1px solid ${THEME.borderStrong}`,
              borderRadius: 10,
              padding: 18,
              boxShadow: "0 18px 45px rgba(15, 23, 42, 0.08)",
              fontFamily: "'JetBrains Mono', monospace",
              display: "grid",
              gap: 14,
            }}>
              <div style={{ fontFamily: "'Inter Tight', sans-serif", fontSize: 12, fontWeight: 700, color: THEME.muted, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Current build
              </div>
              {[
                ["Contracts", fmt.count(headline.n_markets)],
                ["Scored volume", fmt.money(headline.total_volume)],
                ["Forecast horizon", "30m pre-close"],
                ["GBM baseline lift", fmt.pct(gbmImprovement)],
              ].map(([label, value]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 18, alignItems: "baseline", borderTop: `1px solid ${THEME.border}`, paddingTop: 10 }}>
                  <span style={{ fontSize: 11, color: THEME.muted, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</span>
                  <span style={{ fontSize: 18, color: THEME.ink, fontWeight: 700, textAlign: "right" }}>{value}</span>
                </div>
              ))}
              <div style={{ fontFamily: "'Inter Tight', sans-serif", fontSize: 12, color: THEME.muted, lineHeight: 1.45 }}>
                Updated {fmt.date(headline.last_updated)}. Results are strongest for liquid, sports-heavy markets; sparse categories are flagged below.
              </div>
            </div>
          </div>
        </div>
      </header>

      <div style={containerStyle}>
        {/* ============================================================ */}
        {/* KPI ROW                                                       */}
        {/* ============================================================ */}
        <section style={{ marginTop: sectionGap }}>
          <div className="grid-kpi">
            <KpiCard
              label="Markets scored"
              value={fmt.count(headline.n_markets)}
              sublabel={`from ${fmt.count(headline.n_captured)} captured`}
            />
            <KpiCard
              label="Brier (overall)"
              value={headline.brier_overall.toFixed(4)}
              sublabel="lower is better"
              accent={THEME.accent}
            />
            <KpiCard
              label="Log loss"
              value={headline.log_loss_overall.toFixed(4)}
              sublabel="lower is better"
            />
            <KpiCard
              label="Brier · Polymarket"
              value={headline.brier_polymarket.toFixed(4)}
              sublabel={`n = ${fmt.count(headline.n_polymarket)}`}
            />
            <KpiCard
              label="Brier · Kalshi"
              value={headline.brier_kalshi.toFixed(4)}
              sublabel={`n = ${fmt.count(headline.n_kalshi)}`}
            />
            <KpiCard
              label="Total volume"
              value={fmt.money(headline.total_volume)}
              sublabel="combined platforms"
            />
          </div>
        </section>

        {/* ============================================================ */}
        {/* KEY FINDINGS                                                  */}
        {/* ============================================================ */}
        <section style={{ marginTop: sectionGap }}>
          <Card padding={compact ? 14 : 18}>
            <div style={{ fontSize: 12, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 10 }}>
              Key findings
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 8, fontSize: 13.5, color: THEME.inkSoft, lineHeight: 1.55 }}>
              <li>
                <span style={{ color: THEME.accent, fontWeight: 600, marginRight: 6 }}>·</span>
                Market-implied probabilities beat the always-50% baseline by {(headline.pct_better_than_50 * 100).toFixed(1)}% on Brier and the gradient-boosted baseline on volume + lead time + category + platform by {((headline.pct_better_than_gbm ?? 0) * 100).toFixed(1)}%.
              </li>
              <li>
                <span style={{ color: THEME.accent, fontWeight: 600, marginRight: 6 }}>·</span>
                Polymarket has a lower point Brier ({headline.brier_polymarket.toFixed(4)}) than Kalshi ({headline.brier_kalshi.toFixed(4)}), but the 95% bootstrap CIs overlap, so the platform gap is not statistically distinguishable in this sample.
              </li>
              <li>
                <span style={{ color: THEME.accent, fontWeight: 600, marginRight: 6 }}>·</span>
                Calibration is strongest at the extremes (&lt;20% and &gt;80% buckets sit on the diagonal); mid-range buckets show mild overconfidence on the YES side.
              </li>
              <li>
                <span style={{ color: THEME.accent, fontWeight: 600, marginRight: 6 }}>·</span>
                Higher volume and longer lead time are associated with lower Brier error in this dataset; the design is observational, so causal claims are not made.
              </li>
            </ul>
          </Card>
        </section>

        {/* ============================================================ */}
        {/* METHODOLOGY + LIMITATIONS                                     */}
        {/* ============================================================ */}
        <section id="methodology" style={{ marginTop: sectionGap }} className="grid-2">
          <Card padding={compact ? 14 : 18}>
            <div style={{ fontSize: 12, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 10 }}>
              Methodology
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 8, fontSize: 13, color: THEME.inkSoft, lineHeight: 1.5 }}>
              <li><strong style={{ color: THEME.ink }}>Dataset.</strong> Resolved binary YES/NO markets from Polymarket and Kalshi, with the current sample heavily sports-weighted.</li>
              <li><strong style={{ color: THEME.ink }}>Volume threshold.</strong> ≥ $100k traded volume; {fmt.count(headline.n_markets)} of {fmt.count(headline.n_captured)} captured contracts qualify.</li>
              <li><strong style={{ color: THEME.ink }}>Forecast definition.</strong> Last non-trivial YES price (between 0.02 and 0.98) observed at least 30 minutes before close.</li>
              <li><strong style={{ color: THEME.ink }}>Metrics.</strong> Brier score, log loss, reliability buckets (10pp), and 95% CIs from a non-parametric bootstrap.</li>
              <li><strong style={{ color: THEME.ink }}>Baselines.</strong> Always-50%, category base rate, logistic regression and gradient-boosted trees on volume + lead time + category (5-fold OOF).</li>
            </ul>
          </Card>
          <Card padding={compact ? 14 : 18}>
            <div style={{ fontSize: 12, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 10 }}>
              Interpretation notes
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 8, fontSize: 13, color: THEME.inkSoft, lineHeight: 1.5 }}>
              <li><strong style={{ color: THEME.ink }}>Associational, not causal.</strong> Volume and lead time are <em>associated with</em> lower Brier error; the design does not identify causal effects.</li>
              <li><strong style={{ color: THEME.ink }}>Selection on liquidity.</strong> The $100k floor selects markets with active price discovery; performance on illiquid contracts is out of scope.</li>
              <li>
                <strong style={{ color: THEME.ink }}>Coverage.</strong> {(() => {
                  const total = distinctCategories.reduce((s, c) => s + (categoryCounts[c] || 0), 0);
                  const parts = distinctCategories.map((c) => `${c} (${categoryCounts[c]}, ${((categoryCounts[c] / total) * 100).toFixed(0)}%)`);
                  return `${distinctCategories.length} categor${distinctCategories.length === 1 ? "y" : "ies"} represented: ${parts.join(", ")}.`;
                })()} Sports dominates the sample, so global claims are heavily weighted by that category.
              </li>
              <li><strong style={{ color: THEME.ink }}>Forecast source.</strong> Kalshi history coverage is {(kalshiHistoryShare * 100).toFixed(0)}% in this build; non-history rows are explicitly tagged in source and quality fields.</li>
              <li><strong style={{ color: THEME.ink }}>Sparse subgroups.</strong> Some categories have very small samples (e.g. finance n={categoryCounts.finance ?? 0}, geopolitics n={categoryCounts.geopolitics ?? 0}, politics n={categoryCounts.politics ?? 0}); subgroup comparisons there are unreliable and are flagged or hidden in the visuals below.</li>
              <li><strong style={{ color: THEME.ink }}>Bucket noise.</strong> Mid-range calibration buckets contain ~50–90 markets; reliability deviations are directional, not statistically definitive.</li>
            </ul>
          </Card>
        </section>

        {/* ============================================================ */}
        {/* BASELINE COMPARISON                                           */}
        {/* ============================================================ */}
        <section style={{ marginTop: sectionGap }}>
          <SectionHeader
            title="Performance vs. baselines"
            subtitle="Brier score of market-implied probabilities against four naive and learned baselines. Each row pairs the market score with a baseline; the percent shows the market's relative Brier improvement."
          />
          <Card padding={compact ? 14 : 20}>
            <div style={{ display: "grid", gap: 14 }}>
              <ImprovementBar
                baseline={headline.baseline_50_brier}
                market={headline.brier_overall}
                label="vs. always-50% baseline"
                accent={THEME.accent} ink={THEME.ink} muted={THEME.muted} border={THEME.border}
              />
              <ImprovementBar
                baseline={headline.baseline_category_brier}
                market={headline.brier_overall}
                label="vs. category base-rate baseline"
                accent={THEME.accent} ink={THEME.ink} muted={THEME.muted} border={THEME.border}
              />
              {headline.baseline_logistic_brier ? (
                <ImprovementBar
                  baseline={headline.baseline_logistic_brier}
                  market={headline.brier_overall}
                  label="vs. logistic regression (5-fold OOF) on volume + lead time + category"
                  accent={THEME.accent} ink={THEME.ink} muted={THEME.muted} border={THEME.border}
                />
              ) : null}
              {headline.baseline_gbm_brier ? (
                <ImprovementBar
                  baseline={headline.baseline_gbm_brier}
                  market={headline.brier_overall}
                  label="vs. gradient-boosted trees (5-fold OOF) on volume + lead time + category + platform"
                  accent={THEME.accent} ink={THEME.ink} muted={THEME.muted} border={THEME.border}
                />
              ) : null}
            </div>
          </Card>
        </section>

        {/* ============================================================ */}
        {/* CALIBRATION                                                   */}
        {/* ============================================================ */}
        <section id="calibration" style={{ marginTop: sectionGap }}>
          <SectionHeader
            title="Calibration"
            subtitle="Reliability diagram: each point is a 10-percentage-point forecast bucket. The diagonal marks perfect calibration; circle size scales with markets per bucket."
          />
          <div className="grid-cal">
            <Card padding={compact ? 14 : 18}>
              <CalibrationChart
                data={calibration}
                accent={THEME.accent}
                ink={THEME.ink}
                surface={THEME.surface}
                muted={THEME.muted}
                border={THEME.border}
              />
            </Card>
            <Card padding={compact ? 14 : 18}>
              <div style={{ fontSize: 12, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 8 }}>
                Interpretation
              </div>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: THEME.inkSoft }}>
                Calibration is strongest in the extreme probability buckets (&lt;20% and &gt;80%), where points sit close to the diagonal. The 40–60% buckets show mild overconfidence on the YES side: realized YES rates run several points below the forecast probabilities. With ~50–90 markets per mid-range bucket, the deviation is directionally consistent but not statistically conclusive.
              </p>
              <table style={{
                width: "100%",
                marginTop: 12,
                borderCollapse: "collapse",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
              }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${THEME.border}`, color: THEME.muted, textAlign: "right" }}>
                    <th style={{ textAlign: "left", padding: "6px 4px", fontWeight: 500 }}>Bucket</th>
                    <th style={{ padding: "6px 4px", fontWeight: 500 }}>n</th>
                    <th style={{ padding: "6px 4px", fontWeight: 500 }}>Observed</th>
                    <th style={{ padding: "6px 4px", fontWeight: 500 }}>Gap</th>
                  </tr>
                </thead>
                <tbody>
                  {calibration.map((d) => {
                    const gap = d.observed - d.midpoint;
                    return (
                      <tr key={d.bucket} style={{ borderBottom: `1px solid ${THEME.border}` }}>
                        <td style={{ padding: "5px 4px", color: THEME.ink }}>{d.bucket}</td>
                        <td style={{ padding: "5px 4px", textAlign: "right", color: THEME.inkSoft }}>{d.n}</td>
                        <td style={{ padding: "5px 4px", textAlign: "right", color: THEME.inkSoft, fontVariantNumeric: "tabular-nums" }}>{(d.observed * 100).toFixed(1)}%</td>
                        <td style={{ padding: "5px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: Math.abs(gap) < 0.02 ? THEME.muted : (gap > 0 ? THEME.good : THEME.warn) }}>
                          {(gap > 0 ? "+" : "")}{(gap * 100).toFixed(1)}pp
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          </div>
        </section>

        {/* ============================================================ */}
        {/* PLATFORM COMPARISON                                           */}
        {/* ============================================================ */}
        <section id="contracts" style={{ marginTop: sectionGap }}>
          <SectionHeader
            title="Platform comparison"
            subtitle="Brier score with 95% bootstrap confidence intervals. Interpret platform differences cautiously because the sample is sports-heavy."
          />
          <Card padding={compact ? 14 : 20}>
            <PlatformIntervalChart
              platforms={[
                { name: "Polymarket", brier: headline.brier_polymarket, ci: headline.polymarket_ci, n: headline.n_polymarket },
                { name: "Kalshi",     brier: headline.brier_kalshi,     ci: headline.kalshi_ci,     n: headline.n_kalshi },
              ]}
              ink={THEME.ink} muted={THEME.muted} accent={THEME.accent} border={THEME.border}
            />
            <div style={{ marginTop: 14, fontSize: 12, color: THEME.muted, lineHeight: 1.55 }}>
              The point estimates differ but the 95% intervals overlap, so the platform-level gap is not statistically distinguishable in this sample.
            </div>
          </Card>

          {categoryBreakdownRobust.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <SectionHeader
                title="By category"
                subtitle={`Per-category Brier on each platform. Bars are shown only where n ≥ ${MIN_CAT_N} on that platform; sparse cells are listed below.`}
              />
              <Card padding={compact ? 14 : 18}>
                <CategoryBars
                  data={categoryBreakdownRobust}
                  ink={THEME.ink} muted={THEME.muted} accent={THEME.accent} border={THEME.border}
                />
                {sparseCategoryNotes.length > 0 && (
                  <div style={{
                    marginTop: 12,
                    paddingTop: 10,
                    borderTop: `1px solid ${THEME.border}`,
                    fontSize: 12,
                    color: THEME.muted,
                    lineHeight: 1.5,
                  }}>
                    <strong style={{ color: THEME.warn }}>Low n, not plotted:</strong> {sparseCategoryNotes.join(" · ")}. Single-digit samples are too small to support a platform-vs-platform comparison.
                  </div>
                )}
              </Card>
            </div>
          )}
        </section>

        {/* ============================================================ */}
        {/* STRUCTURAL FACTORS                                            */}
        {/* ============================================================ */}
        <section style={{ marginTop: sectionGap }}>
          <SectionHeader
            title="Structural factors"
            subtitle="Brier score by lead time and dollar volume buckets. Both are associated with lower error; the design is observational, so causal claims are not made."
          />
          <div className="grid-bucket">
            <Card padding={compact ? 14 : 18}>
              <div style={{ fontSize: 12, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 4 }}>
                Lead time → Brier
              </div>
              <div style={{ fontSize: 12, color: THEME.muted, marginBottom: 10 }}>
                Markets open ≥30 days before resolution show the lowest mean Brier in this sample.
              </div>
              <BucketChart
                data={leadTime}
                ink={THEME.ink} muted={THEME.muted} accent={THEME.accent} border={THEME.border}
                yMax={0.20}
              />
            </Card>
            <Card padding={compact ? 14 : 18}>
              <div style={{ fontSize: 12, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 4 }}>
                Volume → Brier
              </div>
              <div style={{ fontSize: 12, color: THEME.muted, marginBottom: 10 }}>
                Mean Brier declines monotonically across volume buckets in this sample.
              </div>
              <BucketChart
                data={volume}
                ink={THEME.ink} muted={THEME.muted} accent={THEME.accent} border={THEME.border}
                yMax={0.20}
              />
            </Card>
          </div>
        </section>

        {/* ============================================================ */}
        {/* MARKET-LEVEL TABLE                                            */}
        {/* ============================================================ */}
        <section style={{ marginTop: sectionGap }}>
          <SectionHeader
            title="Row-level audit"
            subtitle="Filterable, sortable view of individual contracts. Defaults to the worst-Brier rows so tails are visible up front."
            right={
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: THEME.muted, textAlign: "right" }}>
                {fmt.count(filteredRows.length)} of {fmt.count(rows.length)} rows
                <div>sorted by {sortKey} {sortDir === "asc" ? "↑" : "↓"}</div>
                {filteredBrier != null && filteredRows.length !== rows.length && (
                  <div>filtered Brier {filteredBrier.toFixed(4)}</div>
                )}
              </div>
            }
          />

          {/* Sticky filter bar */}
          <div style={{
            position: "sticky",
            top: 0,
            zIndex: 5,
            background: THEME.bg,
            paddingTop: 6,
            paddingBottom: 8,
            borderBottom: `1px solid ${THEME.border}`,
            marginBottom: 12,
          }}>
            <div className="filter-bar">
              <span style={{ fontSize: 11, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginRight: 4 }}>
                Platform
              </span>
              <FilterChip
                label="all"
                count={rows.length}
                active={allPlatformsSelected}
                onClick={selectAllPlatforms}
              />
              {platformOptions.map((p) => (
                <FilterChip
                  key={p}
                  label={p}
                  count={platformCounts[p]}
                  active={activePlatforms.size === 1 && activePlatforms.has(p)}
                  onClick={() => selectPlatform(p)}
                />
              ))}
              <span style={{ width: 1, height: 20, background: THEME.border, margin: "0 6px" }}></span>
              <span style={{ fontSize: 11, fontWeight: 600, color: THEME.muted, letterSpacing: "0.04em", textTransform: "uppercase", marginRight: 4 }}>
                Category
              </span>
              <FilterChip
                label="all"
                count={activePlatformRows.length}
                active={allVisibleCategoriesSelected}
                onClick={selectAllCategories}
              />
              {visibleCategories.map((c) => (
                <FilterChip
                  key={c}
                  label={`${c}${(categoryCountsForActivePlatforms[c] ?? 0) < MIN_CAT_N ? " · low n" : ""}`}
                  count={categoryCountsForActivePlatforms[c]}
                  active={!allVisibleCategoriesSelected && activeCategories.has(c)}
                  onClick={() => toggleCategory(c)}
                />
              ))}
              <span className="spacer" />
              <input
                className="filter-search"
                type="search"
                placeholder="Search title…"
                value={tableSearch}
                onChange={(e) => setTableSearch(e.target.value)}
                style={{
                  width: 240,
                  padding: "6px 10px",
                  background: THEME.surface,
                  border: `1px solid ${THEME.border}`,
                  borderRadius: 4,
                  color: THEME.ink,
                  fontFamily: "'Inter Tight', sans-serif",
                  fontSize: 13,
                  outline: "none",
                }}
              />
            </div>
          </div>

          <Card padding={0} style={{ overflow: "hidden" }}>
            <div className="table-scroll">
            <table style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13,
              fontFamily: "'Inter Tight', sans-serif",
            }}>
              <thead>
                <tr style={{ background: THEME.surfaceAlt, borderBottom: `1px solid ${THEME.border}` }}>
                  {[
                    { k: "title", l: "Market", align: "left" },
                    { k: "platform", l: "Platform", align: "left" },
                    { k: "category", l: "Category", align: "left" },
                    { k: "forecast_prob", l: "Forecast", align: "right" },
                    { k: "resolution", l: "Result", align: "right" },
                    { k: "brier", l: "Brier", align: "right" },
                    { k: "volume", l: "Volume", align: "right" },
                    { k: "days_to_resolution", l: "Lead time (d)", align: "right" },
                    { k: "forecast_source", l: "Source", align: "left" },
                  ].map(({ k, l, align }) => (
                    <th
                      key={k}
                      onClick={() => onSort(k)}
                      style={{
                        textAlign: align,
                        padding: "10px 14px",
                        fontSize: 11,
                        letterSpacing: "0.04em",
                        textTransform: "uppercase",
                        color: THEME.muted,
                        fontWeight: 600,
                        cursor: "pointer",
                        userSelect: "none",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {l}
                      {sortKey === k && (
                        <span style={{ marginLeft: 4, color: THEME.accent }}>
                          {sortDir === "asc" ? "↑" : "↓"}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.length === 0 ? (
                  <tr>
                    <td colSpan="9" style={{ padding: 28, textAlign: "center", color: THEME.muted }}>
                      <div>No rows match the current filters.</div>
                      <button
                        type="button"
                        onClick={resetAuditFilters}
                        style={{
                          marginTop: 10,
                          background: THEME.surface,
                          border: `1px solid ${THEME.border}`,
                          borderRadius: 4,
                          padding: "6px 14px",
                          fontSize: 12,
                          color: THEME.inkSoft,
                          cursor: "pointer",
                        }}
                      >
                        Reset filters
                      </button>
                    </td>
                  </tr>
                ) : tableRows.map((r) => (
                  <tr key={r.id} style={{ borderBottom: `1px solid ${THEME.border}` }}>
                    <td style={{ padding: "9px 14px", color: THEME.ink, maxWidth: 420, lineHeight: 1.4 }}>
                      {r.title}
                    </td>
                    <td style={{ padding: "9px 14px", color: THEME.inkSoft, textTransform: "capitalize" }}>
                      {r.platform}
                    </td>
                    <td style={{ padding: "9px 14px", color: THEME.inkSoft, textTransform: "capitalize" }}>
                      {r.category}
                    </td>
                    <td style={{ padding: "9px 14px", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: THEME.ink, fontVariantNumeric: "tabular-nums" }}>
                      {fmt.pct(r.forecast_prob)}
                    </td>
                    <td style={{ padding: "9px 14px", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: r.resolution === "YES" ? THEME.good : THEME.warn, fontWeight: 600 }}>
                      {r.resolution}
                    </td>
                    <td style={{ padding: "9px 14px", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: THEME.ink, fontVariantNumeric: "tabular-nums" }}>
                      {r.brier.toFixed(3)}
                    </td>
                    <td style={{ padding: "9px 14px", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: THEME.inkSoft, fontVariantNumeric: "tabular-nums" }}>
                      {fmt.money(r.volume)}
                    </td>
                    <td style={{ padding: "9px 14px", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: THEME.inkSoft, fontVariantNumeric: "tabular-nums" }}>
                      {Number.isFinite(r.days_to_resolution) ? r.days_to_resolution.toFixed(1) : "—"}
                    </td>
                    <td style={{ padding: "9px 14px", color: THEME.muted, fontSize: 12 }}>
                      {r.forecast_source || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {sortedRows.length > tableLimit && (
              <div style={{ padding: 10, textAlign: "center", borderTop: `1px solid ${THEME.border}`, background: THEME.surfaceAlt }}>
                <button
                  onClick={() => setTableLimit(tableLimit + 50)}
                  style={{
                    background: THEME.surface,
                    border: `1px solid ${THEME.border}`,
                    borderRadius: 4,
                    padding: "6px 14px",
                    fontSize: 12,
                    color: THEME.inkSoft,
                    cursor: "pointer",
                    marginRight: 8,
                  }}
                >
                  Show 50 more
                </button>
                <button
                  onClick={() => setTableLimit(sortedRows.length)}
                  style={{
                    background: THEME.surface,
                    border: `1px solid ${THEME.border}`,
                    borderRadius: 4,
                    padding: "6px 14px",
                    fontSize: 12,
                    color: THEME.inkSoft,
                    cursor: "pointer",
                  }}
                >
                  Show all ({fmt.count(sortedRows.length)})
                </button>
              </div>
            )}
          </Card>
        </section>

        {/* ============================================================ */}
        {/* FOOTER                                                        */}
        {/* ============================================================ */}
        <footer style={{
          marginTop: sectionGap * 1.5,
          paddingTop: 16,
          paddingBottom: 24,
          borderTop: `1px solid ${THEME.border}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          color: THEME.muted,
          gap: 12,
          flexWrap: "wrap",
        }}>
          <span>Prediction market accuracy · methodology-first evaluation</span>
          <span>Brier · log loss · reliability buckets · bootstrap CI</span>
        </footer>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
