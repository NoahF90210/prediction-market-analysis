// Main editorial dashboard.
// Aesthetic: Swiss/print, paper-on-ink-on-paper, single accent.
// Audience: portfolio reviewers — readable, opinionated, restrained.

const { useState, useMemo, useEffect } = React;

// ---------------------------------------------------------------------------
// Tweakable defaults — wrapped in markers so the host can persist edits.
// ---------------------------------------------------------------------------
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "paper",
  "accent": "terracotta",
  "density": "comfortable"
}/*EDITMODE-END*/;

const ACCENT_PALETTES = {
  terracotta: { name: "Terracotta", value: "oklch(0.55 0.13 35)" },
  ink:        { name: "Pure ink",   value: "oklch(0.20 0.01 60)" },
  forest:     { name: "Forest",     value: "oklch(0.42 0.10 145)" },
  prussian:   { name: "Prussian",   value: "oklch(0.42 0.11 245)" },
};

const THEMES = {
  paper: {
    paper:    "#f4f1ea",
    panel:    "#fbf9f3",
    ink:      "#141210",
    inkSoft:  "#3a3530",
    muted:    "#7a7268",
    rule:     "rgba(20, 18, 16, 0.12)",
    ruleSoft: "rgba(20, 18, 16, 0.06)",
  },
  ink: {
    paper:    "#0e0d0b",
    panel:    "#16140f",
    ink:      "#f1ede4",
    inkSoft:  "#cfc8b9",
    muted:    "#8b857a",
    rule:     "rgba(241, 237, 228, 0.14)",
    ruleSoft: "rgba(241, 237, 228, 0.06)",
  },
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
    return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  },
};

// ---------------------------------------------------------------------------
// Section header — small label + serif heading + dek.
// ---------------------------------------------------------------------------
function SectionHeader({ kicker, title, dek, ink, muted, accent }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{
        fontFamily: "'Inter Tight', sans-serif",
        fontSize: 11,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        color: accent,
        fontWeight: 600,
        marginBottom: 12,
      }}>
        <span style={{ display: "inline-block", width: 24, height: 1, background: accent, verticalAlign: "middle", marginRight: 10 }}></span>
        {kicker}
      </div>
      <h2 style={{
        fontFamily: "'Instrument Serif', serif",
        fontSize: 38,
        lineHeight: 1.25,
        margin: 0,
        color: ink,
        fontWeight: 400,
        letterSpacing: "-0.01em",
      }}>
        {title}
      </h2>
      {dek && (
        <p style={{
          fontFamily: "'Inter Tight', sans-serif",
          fontSize: 15,
          lineHeight: 1.55,
          color: muted,
          margin: "30px 0 0",
          maxWidth: 640,
        }}>
          {dek}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat tile — large serif numeral + caption.
// ---------------------------------------------------------------------------
function Stat({ value, label, sublabel, ink, muted, accent, big = false }) {
  return (
    <div>
      <div style={{
        fontFamily: "'Instrument Serif', serif",
        fontSize: big ? 88 : 56,
        lineHeight: 1,
        color: ink,
        fontWeight: 400,
        letterSpacing: "-0.02em",
        fontVariantNumeric: "tabular-nums",
      }}>
        {value}
      </div>
      <div style={{
        fontFamily: "'Inter Tight', sans-serif",
        fontSize: 11,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: accent,
        fontWeight: 600,
        marginTop: 14,
      }}>
        {label}
      </div>
      {sublabel && (
        <div style={{
          fontFamily: "'Inter Tight', sans-serif",
          fontSize: 13,
          lineHeight: 1.5,
          color: muted,
          marginTop: 6,
          maxWidth: 280,
        }}>
          {sublabel}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tweaks panel
// ---------------------------------------------------------------------------
function Tweaks({ tweaks, setTweak }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection title="Theme">
        <TweakRadio
          value={tweaks.theme}
          options={[{ value: "paper", label: "Paper" }, { value: "ink", label: "Ink" }]}
          onChange={(v) => setTweak("theme", v)}
        />
      </TweakSection>
      <TweakSection title="Accent">
        <TweakColor
          value={tweaks.accent}
          options={Object.entries(ACCENT_PALETTES).map(([key, p]) => ({ value: key, color: p.value, label: p.name }))}
          onChange={(v) => setTweak("accent", v)}
        />
      </TweakSection>
      <TweakSection title="Density">
        <TweakRadio
          value={tweaks.density}
          options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]}
          onChange={(v) => setTweak("density", v)}
        />
      </TweakSection>
    </TweaksPanel>
  );
}

// ---------------------------------------------------------------------------
// Filter chip — interactive pill.
// ---------------------------------------------------------------------------
function FilterChip({ label, value, active, onClick, ink, muted, rule, accent, paper }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 14px",
        border: `1px solid ${active ? accent : rule}`,
        background: active ? accent : "transparent",
        color: active ? paper : ink,
        fontFamily: "'Inter Tight', sans-serif",
        fontSize: 13,
        fontWeight: 500,
        cursor: "pointer",
        borderRadius: 999,
        transition: "all 0.15s ease",
      }}
    >
      <span>{label}</span>
      {value != null && (
        <span style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          opacity: 0.7,
          fontVariantNumeric: "tabular-nums",
        }}>
          {value}
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main app
// ---------------------------------------------------------------------------
function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const theme = THEMES[tweaks.theme] || THEMES.paper;
  const accent = ACCENT_PALETTES[tweaks.accent]?.value || ACCENT_PALETTES.terracotta.value;
  const compact = tweaks.density === "compact";

  const data = window.DASHBOARD_DATA;
  const { headline, calibration, leadTime, volume, categoryBreakdown, rows } = data;

  // Filter state — categorical, illustrative.
  const [activeCategories, setActiveCategories] = useState(() =>
    new Set(categoryBreakdown.map((c) => c.category))
  );
  const [activePlatforms, setActivePlatforms] = useState(() => new Set(["polymarket", "kalshi"]));
  const [tableSearch, setTableSearch] = useState("");

  const toggleSet = (set, v) => {
    const next = new Set(set);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    return next;
  };

  // Filtered table view (top 40 by volume after search/platform filter)
  const tableRows = useMemo(() => {
    return rows
      .filter((r) => activePlatforms.has(r.platform))
      .filter((r) => activeCategories.has(r.category))
      .filter((r) => !tableSearch || r.title.toLowerCase().includes(tableSearch.toLowerCase()))
      .sort((a, b) => b.volume - a.volume)
      .slice(0, 10);
  }, [rows, activePlatforms, activeCategories, tableSearch]);

  // ---------------------------------------------------------------------------
  // Style constants derived from theme + density
  // ---------------------------------------------------------------------------
  const wrapperStyle = {
    background: theme.paper,
    color: theme.ink,
    minHeight: "100vh",
    fontFamily: "'Inter Tight', system-ui, sans-serif",
    transition: "background 0.2s ease, color 0.2s ease",
  };

  const containerStyle = {
    maxWidth: 1280,
    margin: "0 auto",
    padding: compact ? "32px 40px" : "56px 56px",
  };

  const ruleStyle = {
    border: 0,
    borderTop: `1px solid ${theme.rule}`,
    margin: compact ? "48px 0" : "72px 0",
  };

  const panelStyle = {
    background: theme.panel,
    border: `1px solid ${theme.rule}`,
    padding: compact ? 24 : 32,
  };

  return (
    <div style={wrapperStyle}>
      <Tweaks tweaks={tweaks} setTweak={setTweak} />

      <div style={containerStyle}>
        {/* ============================================================ */}
        {/* MASTHEAD                                                      */}
        {/* ============================================================ */}
        <header style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          paddingBottom: 18,
          borderBottom: `1px solid ${theme.ink}`,
          marginBottom: compact ? 32 : 56,
        }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
            <div style={{
              width: 14, height: 14,
              background: accent,
              transform: "rotate(45deg)",
              alignSelf: "center",
            }}></div>
            <span style={{
              fontFamily: "'Instrument Serif', serif",
              fontSize: 22,
              letterSpacing: "0.02em",
              fontStyle: "italic",
            }}>
              The Forecast Audit
            </span>
          </div>
          <div style={{
            display: "flex",
            gap: 24,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            color: theme.muted,
            letterSpacing: "0.05em",
          }}>
            <span>VOL. 01 · ISSUE 04</span>
            <span>{fmt.date(headline.last_updated)}</span>
            <span style={{ color: theme.ink }}>—— SCORED N={headline.n_markets}</span>
          </div>
        </header>

        {/* ============================================================ */}
        {/* HERO — the headline finding                                   */}
        {/* ============================================================ */}
        <section>
          <div style={{
            fontFamily: "'Inter Tight', sans-serif",
            fontSize: 11,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: accent,
            fontWeight: 600,
            marginBottom: 24,
          }}>
            The headline finding
          </div>
          <h1 style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: "clamp(56px, 8.5vw, 132px)",
            lineHeight: 0.92,
            margin: 0,
            color: theme.ink,
            fontWeight: 400,
            letterSpacing: "-0.025em",
            textWrap: "pretty",
          }}>
            Liquid prediction markets beat
            an always-<span style={{ color: accent, fontStyle: "italic" }}>fifty-percent</span> baseline
            by <span style={{ fontVariantNumeric: "tabular-nums" }}>{(headline.pct_better_than_50 * 100).toFixed(1)}%</span> on Brier score.
          </h1>

          <div style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr",
            gap: 64,
            marginTop: compact ? 48 : 72,
            alignItems: "start",
          }}>
            <div>
              <p style={{
                fontFamily: "'Instrument Serif', serif",
                fontSize: 22,
                lineHeight: 1.45,
                color: theme.inkSoft,
                margin: 0,
                fontWeight: 400,
                textWrap: "pretty",
              }}>
                Across <strong style={{ color: theme.ink }}>{fmt.count(headline.n_markets)}</strong> resolved binary contracts
                from Polymarket and Kalshi, with a $100k volume floor, market-implied probabilities
                produced an average Brier score of <strong style={{ color: theme.ink, fontVariantNumeric: "tabular-nums" }}>{headline.brier_overall.toFixed(4)}</strong> —
                meaningfully better than coin-flip and category base-rate baselines, but with a
                consistent overshoot in the <em>middle</em> of the probability range.
              </p>

              <div style={{ marginTop: 36, display: "grid", gap: 22 }}>
                <ImprovementBar
                  baseline={headline.baseline_50_brier}
                  market={headline.brier_overall}
                  label="vs. always-50% baseline"
                  accent={accent} ink={theme.ink} muted={theme.muted}
                />
                <ImprovementBar
                  baseline={headline.baseline_category_brier}
                  market={headline.brier_overall}
                  label="vs. category base-rate baseline"
                  accent={accent} ink={theme.ink} muted={theme.muted}
                />
                {headline.baseline_logistic_brier ? (
                  <ImprovementBar
                    baseline={headline.baseline_logistic_brier}
                    market={headline.brier_overall}
                    label="vs. logistic regression on volume + lead time + category (5-fold OOF)"
                    accent={accent} ink={theme.ink} muted={theme.muted}
                  />
                ) : null}
              </div>
            </div>

            <aside style={{
              borderLeft: `1px solid ${theme.rule}`,
              paddingLeft: 36,
              display: "grid",
              gap: 36,
            }}>
              <Stat
                big
                value={headline.brier_overall.toFixed(4)}
                label="Brier Score, all markets"
                sublabel="Lower is better. Penalises misses quadratically."
                ink={theme.ink} muted={theme.muted} accent={accent}
              />
              <Stat
                value={headline.log_loss_overall.toFixed(4)}
                label="Log loss"
                sublabel="Stricter penalty for confident misses."
                ink={theme.ink} muted={theme.muted} accent={accent}
              />
            </aside>
          </div>
        </section>

        <hr style={ruleStyle} />

        {/* ============================================================ */}
        {/* SCOPE                                                         */}
        {/* ============================================================ */}
        <section>
          <SectionHeader
            kicker="01 · Scope"
            title="What this measures, and what it doesn't."
            dek="Forecast quality on liquid, resolved binary contracts. Not trading profitability, not market efficiency, not platform alpha. The point is whether the implied probability matched the eventual outcome."
            ink={theme.ink} muted={theme.muted} accent={accent}
          />
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 0,
            borderTop: `1px solid ${theme.rule}`,
            borderBottom: `1px solid ${theme.rule}`,
          }}>
            {[
              { v: fmt.count(headline.n_markets), l: "scored markets", s: "binary YES/NO, resolved" },
              { v: "$100k", l: "minimum volume", s: "captured 1,133 before scoring filters" },
              { v: "8", l: "categories", s: "metadata-first, audited taxonomy" },
              { v: fmt.money(headline.total_volume), l: "total dollar volume", s: "combined across both platforms" },
            ].map((s, i) => (
              <div key={i} style={{
                padding: compact ? "24px 20px" : "32px 28px",
                borderRight: i < 3 ? `1px solid ${theme.rule}` : "none",
              }}>
                <div style={{
                  fontFamily: "'Instrument Serif', serif",
                  fontSize: 42,
                  lineHeight: 1,
                  color: theme.ink,
                  fontVariantNumeric: "tabular-nums",
                }}>{s.v}</div>
                <div style={{
                  fontFamily: "'Inter Tight', sans-serif",
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                  color: theme.muted,
                  marginTop: 12,
                  fontWeight: 600,
                }}>{s.l}</div>
                <div style={{
                  fontFamily: "'Inter Tight', sans-serif",
                  fontSize: 13,
                  color: theme.muted,
                  marginTop: 6,
                  lineHeight: 1.5,
                }}>{s.s}</div>
              </div>
            ))}
          </div>
        </section>

        <hr style={ruleStyle} />

        {/* ============================================================ */}
        {/* CALIBRATION                                                   */}
        {/* ============================================================ */}
        <section>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1.4fr",
            gap: 56,
            alignItems: "start",
          }}>
            <div>
              <SectionHeader
                kicker="02 · Calibration"
                title="Mid-range buckets sit below the diagonal."
                dek="Each circle is a 10-percentage-point probability bucket; size scales with the number of markets in that bucket. If markets were perfectly calibrated, every dot would land on the dashed line."
                ink={theme.ink} muted={theme.muted} accent={accent}
              />
              <div style={{ marginTop: 28, display: "grid", gap: 20 }}>
                <div style={{ paddingTop: 16, borderTop: `1px solid ${theme.rule}` }}>
                  <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 24, lineHeight: 1.2, color: theme.ink }}>
                    The 30–70% range systematically <em>over</em>-predicts YES.
                  </div>
                  <p style={{ fontFamily: "'Inter Tight', sans-serif", fontSize: 14, lineHeight: 1.6, color: theme.muted, marginTop: 10 }}>
                    Tail buckets (under 10% and over 90%) are well-calibrated. The middle of the range is where uncertainty lives — and where the markets get cocky.
                  </p>
                </div>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr",
                  gap: "8px 20px",
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12,
                  color: theme.inkSoft,
                  alignItems: "center",
                }}>
                  <span style={{
                    width: 14, height: 14, borderRadius: 999,
                    border: `2px solid ${accent}`, background: theme.paper,
                    boxShadow: `inset 0 0 0 3px ${accent}`,
                  }}></span>
                  <span>observed bucket (size = N markets)</span>
                  <span style={{ width: 24, height: 0, borderTop: `1px dashed ${theme.ink}`, opacity: 0.5 }}></span>
                  <span>perfect calibration</span>
                </div>
              </div>
            </div>

            <div style={panelStyle}>
              <CalibrationChart
                data={calibration}
                accent={accent}
                ink={theme.ink}
                paper={theme.panel}
                muted={theme.muted}
              />
            </div>
          </div>
        </section>

        <hr style={ruleStyle} />

        {/* ============================================================ */}
        {/* PLATFORM COMPARISON                                           */}
        {/* ============================================================ */}
        <section>
          <SectionHeader
            kicker="03 · Platform comparison"
            title="Polymarket leads on the headline number, but the bootstrap intervals overlap."
            dek="By category, by Brier score. Lower is better. The platform gap is real — and small enough that the confidence intervals warn against over-claiming."
            ink={theme.ink} muted={theme.muted} accent={accent}
          />

          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 32,
            marginBottom: 40,
          }}>
            {[
              {
                name: "Polymarket",
                brier: headline.brier_polymarket,
                ci: headline.polymarket_ci,
                n: headline.n_polymarket,
                source: "history-based",
                color: theme.ink,
                subBrier: null,
                subN: null,
                subCi: null,
                subLabel: null,
              },
              {
                name: "Kalshi",
                brier: headline.brier_kalshi,
                ci: headline.kalshi_ci,
                n: headline.n_kalshi,
                source: "snapshot fallback (mostly)",
                color: accent,
                subBrier: headline.brier_kalshi_history_only,
                subN: headline.n_kalshi_history,
                subCi: headline.kalshi_history_ci,
                subLabel: "history-only subset",
              },
            ].map((p) => (
              <div key={p.name} style={{
                ...panelStyle,
                padding: compact ? 24 : 32,
                position: "relative",
              }}>
                <div style={{
                  position: "absolute", top: 0, left: 0,
                  width: 4, height: "100%", background: p.color,
                }}></div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <h3 style={{
                    fontFamily: "'Instrument Serif', serif",
                    fontSize: 28, margin: 0, fontWeight: 400,
                  }}>
                    {p.name}
                  </h3>
                  <span style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11, color: theme.muted, letterSpacing: "0.05em",
                  }}>
                    n = {fmt.count(p.n)} · {p.source}
                  </span>
                </div>
                <div style={{
                  fontFamily: "'Instrument Serif', serif",
                  fontSize: 72, lineHeight: 1,
                  marginTop: 20, color: theme.ink,
                  fontVariantNumeric: "tabular-nums",
                }}>
                  {p.brier.toFixed(4)}
                </div>
                <div style={{
                  fontFamily: "'Inter Tight', sans-serif",
                  fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase",
                  color: theme.muted, fontWeight: 600, marginTop: 14,
                }}>
                  Brier score
                </div>
                <div style={{
                  marginTop: 20, paddingTop: 14,
                  borderTop: `1px solid ${theme.rule}`,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12, color: theme.inkSoft,
                }}>
                  95% CI: [{p.ci[0].toFixed(3)}, {p.ci[1].toFixed(3)}]
                </div>
                {p.name === "Kalshi" ? (
                  <div style={{
                    marginTop: 14, paddingTop: 14,
                    borderTop: `1px dashed ${theme.rule}`,
                  }}>
                    <div style={{
                      fontFamily: "'Inter Tight', sans-serif",
                      fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase",
                      color: accent, fontWeight: 700,
                    }}>
                      Methodology caveat
                    </div>
                    {p.subBrier != null && p.subN > 0 ? (
                      <>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 8 }}>
                          <span style={{
                            fontFamily: "'Instrument Serif', serif",
                            fontSize: 32, color: theme.ink,
                            fontVariantNumeric: "tabular-nums",
                          }}>
                            {p.subBrier.toFixed(4)}
                          </span>
                          <span style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: 11, color: theme.muted,
                          }}>
                            apples-to-apples · n = {fmt.count(p.subN)}
                            {p.subCi && p.subCi[0] != null ? ` · 95% CI [${p.subCi[0].toFixed(3)}, ${p.subCi[1].toFixed(3)}]` : ""}
                          </span>
                        </div>
                        <div style={{
                          marginTop: 8,
                          fontFamily: "'Inter Tight', sans-serif",
                          fontSize: 12, color: theme.inkSoft, lineHeight: 1.45,
                        }}>
                          Restricting to Kalshi rows with cached pre-resolution price history removes the
                          settlement-snapshot rows that arguably measure convergence rather than skill.
                        </div>
                      </>
                    ) : (
                      <div style={{
                        marginTop: 8,
                        fontFamily: "'Inter Tight', sans-serif",
                        fontSize: 13, color: theme.inkSoft, lineHeight: 1.5,
                      }}>
                        All {fmt.count(p.n)} Kalshi rows in this build use a non-trivial snapshot from the
                        cached settled-market record (not full pre-resolution history). That snapshot is
                        sometimes close to the settlement price, so the Kalshi number partly reflects
                        convergence rather than pure forecast skill. Treat the cross-platform comparison
                        as directional until full Kalshi history is backfilled.
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          <div style={panelStyle}>
            <div style={{
              fontFamily: "'Inter Tight', sans-serif",
              fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase",
              color: theme.muted, fontWeight: 600, marginBottom: 18,
            }}>
              By category
            </div>
            <CategorySlope
              data={categoryBreakdown}
              accent={accent}
              ink={theme.ink}
              muted={theme.muted}
              paper={theme.panel}
            />
          </div>
        </section>

        <hr style={ruleStyle} />

        {/* ============================================================ */}
        {/* STRUCTURAL FACTORS                                            */}
        {/* ============================================================ */}
        <section>
          <SectionHeader
            kicker="04 · Structural factors"
            title="Longer markets and bigger markets forecast better."
            dek="Both lead time and dollar volume correlate with lower Brier error. The relationship is associational, not causal — but it's consistent with the intuition that liquidity and time give the market room to find a price."
            ink={theme.ink} muted={theme.muted} accent={accent}
          />
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 32,
          }}>
            <div style={panelStyle}>
              <div style={{
                fontFamily: "'Inter Tight', sans-serif",
                fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase",
                color: theme.muted, fontWeight: 600, marginBottom: 8,
              }}>
                Lead time → Brier
              </div>
              <div style={{
                fontFamily: "'Instrument Serif', serif", fontSize: 22, lineHeight: 1.3,
                marginBottom: 18, color: theme.ink,
              }}>
                Markets open <em>30+ days</em> before resolution score best.
              </div>
              <BucketChart
                data={leadTime}
                accent={accent}
                ink={theme.ink}
                muted={theme.muted}
              />
            </div>
            <div style={panelStyle}>
              <div style={{
                fontFamily: "'Inter Tight', sans-serif",
                fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase",
                color: theme.muted, fontWeight: 600, marginBottom: 8,
              }}>
                Volume → Brier
              </div>
              <div style={{
                fontFamily: "'Instrument Serif', serif", fontSize: 22, lineHeight: 1.3,
                marginBottom: 18, color: theme.ink,
              }}>
                Brier falls monotonically as volume rises.
              </div>
              <BucketChart
                data={volume}
                accent={accent}
                ink={theme.ink}
                muted={theme.muted}
              />
            </div>
          </div>
        </section>

        <hr style={ruleStyle} />

        {/* ============================================================ */}
        {/* MARKET-LEVEL TABLE                                            */}
        {/* ============================================================ */}
        <section>
          <SectionHeader
            kicker="05 · Spot check"
            title="Top 10 by volume, in the current slice."
            dek="The interesting question is rarely the average. Filter by platform and category, search by title, and read the row-level Brier to see where the average comes from."
            ink={theme.ink} muted={theme.muted} accent={accent}
          />

          {/* Filter row */}
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: 18,
            alignItems: "center",
          }}>
            <span style={{
              fontFamily: "'Inter Tight', sans-serif",
              fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase",
              color: theme.muted, fontWeight: 600, marginRight: 4,
            }}>Platform</span>
            {["polymarket", "kalshi"].map((p) => (
              <FilterChip
                key={p}
                label={p}
                active={activePlatforms.has(p)}
                onClick={() => setActivePlatforms(toggleSet(activePlatforms, p))}
                ink={theme.ink} muted={theme.muted} rule={theme.rule}
                accent={accent} paper={theme.paper}
              />
            ))}
            <span style={{ width: 1, height: 18, background: theme.rule, margin: "0 8px" }}></span>
            <span style={{
              fontFamily: "'Inter Tight', sans-serif",
              fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase",
              color: theme.muted, fontWeight: 600, marginRight: 4,
            }}>Category</span>
            {categoryBreakdown.map((c) => (
              <FilterChip
                key={c.category}
                label={c.category}
                active={activeCategories.has(c.category)}
                onClick={() => setActiveCategories(toggleSet(activeCategories, c.category))}
                ink={theme.ink} muted={theme.muted} rule={theme.rule}
                accent={accent} paper={theme.paper}
              />
            ))}
          </div>

          <div style={{ marginBottom: 18 }}>
            <input
              type="search"
              placeholder="Search market titles…"
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              style={{
                width: "100%",
                padding: "12px 16px",
                background: "transparent",
                border: 0,
                borderBottom: `1px solid ${theme.rule}`,
                color: theme.ink,
                fontFamily: "'Instrument Serif', serif",
                fontSize: 18,
                outline: "none",
              }}
            />
          </div>

          <div style={{
            border: `1px solid ${theme.rule}`,
            background: theme.panel,
          }}>
            <table style={{
              width: "100%",
              borderCollapse: "collapse",
              fontFamily: "'Inter Tight', sans-serif",
              fontSize: 14,
            }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${theme.ink}` }}>
                  {["Market", "Platform", "Category", "Forecast", "Result", "Brier", "Volume"].map((h, i) => (
                    <th key={h} style={{
                      textAlign: i >= 3 ? "right" : "left",
                      padding: "14px 18px",
                      fontFamily: "'Inter Tight', sans-serif",
                      fontSize: 10,
                      letterSpacing: "0.16em",
                      textTransform: "uppercase",
                      color: theme.muted,
                      fontWeight: 600,
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{
                      padding: 32, textAlign: "center", color: theme.muted,
                      fontFamily: "'Instrument Serif', serif", fontSize: 18, fontStyle: "italic",
                    }}>
                      No markets match the current filters.
                    </td>
                  </tr>
                ) : tableRows.map((r) => (
                  <tr key={r.id} style={{ borderBottom: `1px solid ${theme.ruleSoft}` }}>
                    <td style={{
                      padding: "14px 18px",
                      fontFamily: "'Instrument Serif', serif", fontSize: 16, color: theme.ink,
                      maxWidth: 380,
                    }}>
                      {r.title}
                    </td>
                    <td style={{ padding: "14px 18px", color: theme.muted, fontSize: 12, letterSpacing: "0.05em" }}>
                      {r.platform}
                    </td>
                    <td style={{ padding: "14px 18px", color: theme.inkSoft, fontStyle: "italic", fontFamily: "'Instrument Serif', serif" }}>
                      {r.category}
                    </td>
                    <td style={{
                      padding: "14px 18px", textAlign: "right",
                      fontFamily: "'JetBrains Mono', monospace", color: theme.ink,
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {fmt.pct(r.forecast_prob)}
                    </td>
                    <td style={{
                      padding: "14px 18px", textAlign: "right",
                      fontFamily: "'JetBrains Mono', monospace",
                      color: r.resolution === "YES" ? accent : theme.muted,
                      fontWeight: 600,
                    }}>
                      {r.resolution}
                    </td>
                    <td style={{
                      padding: "14px 18px", textAlign: "right",
                      fontFamily: "'JetBrains Mono', monospace", color: theme.ink,
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {r.brier.toFixed(3)}
                    </td>
                    <td style={{
                      padding: "14px 18px", textAlign: "right",
                      fontFamily: "'JetBrains Mono', monospace", color: theme.inkSoft,
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {fmt.money(r.volume)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <hr style={ruleStyle} />

        {/* ============================================================ */}
        {/* CAVEATS                                                       */}
        {/* ============================================================ */}
        <section>
          <SectionHeader
            kicker="06 · Caveats"
            title="Where this analysis is weakest."
            ink={theme.ink} muted={theme.muted} accent={accent}
          />
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 0,
            borderTop: `1px solid ${theme.rule}`,
          }}>
            {[
              {
                t: "Asymmetric data quality",
                b: "Polymarket rows are history-based. Most Kalshi rows rely on snapshot fallback from settled-market records. Cross-platform claims are directional, not definitive.",
              },
              {
                t: "Associational regression",
                b: "Higher volume correlates with lower Brier error. That doesn't prove liquidity causes accuracy — both could be downstream of market structure or category mix.",
              },
              {
                t: "Forecast definition",
                b: "Polymarket uses the last YES price between 0.02 and 0.98. Kalshi uses the best non-trivial snapshot when full history isn't cached.",
              },
            ].map((c, i) => (
              <div key={i} style={{
                padding: compact ? "24px 24px 24px 0" : "32px 32px 32px 0",
                borderRight: i < 2 ? `1px solid ${theme.rule}` : "none",
                paddingRight: i < 2 ? (compact ? 24 : 32) : 0,
                paddingLeft: i > 0 ? (compact ? 24 : 32) : 0,
              }}>
                <div style={{
                  fontFamily: "'Instrument Serif', serif",
                  fontSize: 22, lineHeight: 1.3, color: theme.ink, marginBottom: 12,
                }}>
                  {c.t}
                </div>
                <div style={{
                  fontFamily: "'Inter Tight', sans-serif",
                  fontSize: 14, lineHeight: 1.6, color: theme.muted,
                }}>
                  {c.b}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ============================================================ */}
        {/* COLOPHON                                                      */}
        {/* ============================================================ */}
        <footer style={{
          marginTop: compact ? 56 : 96,
          paddingTop: 24,
          borderTop: `1px solid ${theme.ink}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          letterSpacing: "0.05em",
          color: theme.muted,
        }}>
          <span>—— PREDICTION MARKET ACCURACY · METHODOLOGY-FIRST</span>
          <span>BRIER · LOG-LOSS · CALIBRATION · BOOTSTRAP CI</span>
          <span style={{ color: theme.ink }}>END.</span>
        </footer>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
