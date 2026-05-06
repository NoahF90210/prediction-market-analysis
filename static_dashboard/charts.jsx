// Bespoke editorial SVG charts. No Plotly.
// All charts share the same minimalist visual vocabulary:
//   - thin 1px ink axes, no gridlines unless functional
//   - serif numerals for values, sans for labels
//   - one accent color, ink for primary
//   - generous whitespace; no chart junk

const { useRef, useEffect, useState } = React;

// ---------------------------------------------------------------------------
// Hook: ResizeObserver-driven width tracking. Keeps charts responsive without
// listening on window resize globally.
// ---------------------------------------------------------------------------
function useMeasure() {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 600, height: 360 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) setSize((s) => ({ ...s, width }));
      }
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, size];
}

// ---------------------------------------------------------------------------
// Calibration plot — the analytical centerpiece.
// Each bucket is a circle sized by N. Diagonal = perfect calibration.
// Lollipop drops from the bucket to the diagonal to make miscalibration legible.
// ---------------------------------------------------------------------------
function CalibrationChart({ data, accent, ink, paper, muted }) {
  const [ref, { width }] = useMeasure();
  const height = 420;
  const m = { top: 28, right: 32, bottom: 56, left: 56 };
  const w = Math.max(0, width - m.left - m.right);
  const h = height - m.top - m.bottom;
  const x = (v) => m.left + v * w;
  const y = (v) => m.top + h - v * h;

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const maxN = Math.max(...data.map((d) => d.n));
  const r = (n) => 6 + (n / maxN) * 18;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Diagonal — perfect calibration */}
        <line
          x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)}
          stroke={ink} strokeWidth="1" strokeDasharray="2 4" opacity="0.4"
        />

        {/* Tick labels — x */}
        {ticks.map((t) => (
          <g key={`xt-${t}`}>
            <line x1={x(t)} y1={m.top + h} x2={x(t)} y2={m.top + h + 5} stroke={ink} strokeWidth="1" opacity="0.5" />
            <text
              x={x(t)} y={m.top + h + 22}
              textAnchor="middle"
              fontFamily="'JetBrains Mono', monospace"
              fontSize="11" fill={muted}
            >
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        {/* Tick labels — y */}
        {ticks.map((t) => (
          <g key={`yt-${t}`}>
            <line x1={m.left - 5} y1={y(t)} x2={m.left} y2={y(t)} stroke={ink} strokeWidth="1" opacity="0.5" />
            <text
              x={m.left - 10} y={y(t) + 4}
              textAnchor="end"
              fontFamily="'JetBrains Mono', monospace"
              fontSize="11" fill={muted}
            >
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}

        {/* Axes */}
        <line x1={m.left} y1={m.top} x2={m.left} y2={m.top + h} stroke={ink} strokeWidth="1" />
        <line x1={m.left} y1={m.top + h} x2={m.left + w} y2={m.top + h} stroke={ink} strokeWidth="1" />

        {/* Axis labels */}
        <text x={m.left + w / 2} y={height - 6} textAnchor="middle" fontFamily="'Inter Tight', sans-serif" fontSize="11" fill={muted} letterSpacing="0.08em">
          FORECAST PROBABILITY →
        </text>
        <text
          transform={`rotate(-90, 16, ${m.top + h / 2})`}
          x={16} y={m.top + h / 2}
          textAnchor="middle"
          fontFamily="'Inter Tight', sans-serif" fontSize="11" fill={muted}
          letterSpacing="0.08em"
        >
          OBSERVED YES RATE →
        </text>

        {/* Diagonal endpoint label */}
        <text x={x(1) - 4} y={y(1) - 8} textAnchor="end" fontFamily="'Instrument Serif', serif" fontSize="13" fill={muted} fontStyle="italic">
          perfect
        </text>

        {/* Lollipop drops to diagonal */}
        {data.map((d) => (
          <line
            key={`drop-${d.bucket}`}
            x1={x(d.midpoint)} y1={y(d.observed)}
            x2={x(d.midpoint)} y2={y(d.midpoint)}
            stroke={accent} strokeWidth="1" opacity="0.5"
          />
        ))}

        {/* Bucket dots */}
        {data.map((d) => (
          <g key={d.bucket}>
            <circle
              cx={x(d.midpoint)} cy={y(d.observed)}
              r={r(d.n)}
              fill={paper}
              stroke={accent}
              strokeWidth="2"
            />
            <circle
              cx={x(d.midpoint)} cy={y(d.observed)}
              r={Math.max(2, r(d.n) - 5)}
              fill={accent}
            />
          </g>
        ))}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Slope chart — Polymarket vs Kalshi by category.
// Each category gets two dots connected by a line. Order by overall.
// ---------------------------------------------------------------------------
function CategorySlope({ data, accent, ink, muted, paper }) {
  const [ref, { width }] = useMeasure();
  const rowH = 38;
  const m = { top: 44, right: 24, bottom: 16, left: 140 };
  const height = m.top + m.bottom + data.length * rowH;
  const w = Math.max(0, width - m.left - m.right);

  // Sort by combined Brier so worst-on-both is at the bottom.
  const sorted = [...data].sort((a, b) => (a.polymarket + a.kalshi) - (b.polymarket + b.kalshi));
  const allValues = sorted.flatMap((d) => [d.polymarket, d.kalshi]);
  const minV = Math.min(...allValues) * 0.96;
  const maxV = Math.max(...allValues) * 1.02;

  // Reserve outer pixels for value labels.
  const labelPad = 56;
  const barX0 = m.left + labelPad;
  const barW = Math.max(40, w - labelPad * 2);
  const xScale = (v) => barX0 + ((v - minV) / (maxV - minV)) * barW;
  const yScale = (i) => m.top + (i + 0.5) * rowH;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Axis baseline + tick scale */}
        <line x1={barX0} y1={m.top - 14} x2={barX0 + barW} y2={m.top - 14} stroke={ink} strokeWidth="1" opacity="0.25" />
        {[minV, (minV + maxV) / 2, maxV].map((t, i) => (
          <g key={i}>
            <line x1={xScale(t)} y1={m.top - 18} x2={xScale(t)} y2={m.top - 10} stroke={ink} strokeWidth="1" opacity="0.3" />
            <text x={xScale(t)} y={m.top - 24} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={muted}>
              {t.toFixed(3)}
            </text>
          </g>
        ))}
        <text x={barX0 + barW / 2} y={m.top - 38} textAnchor="middle" fontFamily="'Inter Tight', sans-serif" fontSize="10" fill={muted} letterSpacing="0.14em">
          BRIER SCORE — LOWER IS BETTER →
        </text>

        {/* Rows */}
        {sorted.map((d, i) => {
          const cy = yScale(i);
          const xPoly = xScale(d.polymarket);
          const xKal = xScale(d.kalshi);
          // Determine which dot is on the left/right so labels never collide.
          const polyLeft = xPoly <= xKal;
          return (
            <g key={d.category}>
              {/* Category label (left rail) */}
              <text
                x={m.left - 12} y={cy + 5}
                textAnchor="end"
                fontFamily="'Instrument Serif', serif"
                fontSize="17" fill={ink}
              >
                {d.category}
              </text>

              {/* Faint row guide */}
              <line x1={barX0} y1={cy} x2={barX0 + barW} y2={cy} stroke={ink} strokeWidth="1" opacity="0.05" />

              {/* Connecting segment between the two dots */}
              <line
                x1={xPoly} y1={cy} x2={xKal} y2={cy}
                stroke={muted} strokeWidth="1.5" opacity="0.6"
              />

              {/* Polymarket dot */}
              <circle cx={xPoly} cy={cy} r="6" fill={paper} stroke={ink} strokeWidth="2" />
              <circle cx={xPoly} cy={cy} r="3" fill={ink} />

              {/* Kalshi dot */}
              <circle cx={xKal} cy={cy} r="6" fill={paper} stroke={accent} strokeWidth="2" />
              <circle cx={xKal} cy={cy} r="3" fill={accent} />

              {/* Value labels — outer side of each dot */}
              <text
                x={polyLeft ? xPoly - 10 : xPoly + 10}
                y={cy + 4}
                textAnchor={polyLeft ? "end" : "start"}
                fontFamily="'JetBrains Mono', monospace" fontSize="11" fill={ink}
              >
                {d.polymarket.toFixed(3)}
              </text>
              <text
                x={polyLeft ? xKal + 10 : xKal - 10}
                y={cy + 4}
                textAnchor={polyLeft ? "start" : "end"}
                fontFamily="'JetBrains Mono', monospace" fontSize="11" fill={accent}
              >
                {d.kalshi.toFixed(3)}
              </text>
            </g>
          );
        })}

        {/* Legend in lower-right */}
        <g transform={`translate(${barX0 + barW - 200}, ${height - 6})`}>
          <circle cx="0" cy="-4" r="5" fill={paper} stroke={ink} strokeWidth="2" />
          <circle cx="0" cy="-4" r="2.5" fill={ink} />
          <text x="10" y="0" fontFamily="'Inter Tight', sans-serif" fontSize="11" fill={muted} letterSpacing="0.06em">POLYMARKET</text>
          <circle cx="105" cy="-4" r="5" fill={paper} stroke={accent} strokeWidth="2" />
          <circle cx="105" cy="-4" r="2.5" fill={accent} />
          <text x="115" y="0" fontFamily="'Inter Tight', sans-serif" fontSize="11" fill={muted} letterSpacing="0.06em">KALSHI</text>
        </g>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step chart — Brier by lead time / volume bucket.
// Used twice with different data.
// ---------------------------------------------------------------------------
function BucketChart({ data, accent, ink, muted, valueKey = "brier", maxValue }) {
  const [ref, { width }] = useMeasure();
  const height = 280;
  const m = { top: 28, right: 24, bottom: 56, left: 48 };
  const w = Math.max(0, width - m.left - m.right);
  const h = height - m.top - m.bottom;

  const filtered = data.filter((d) => d.bucket !== "unknown");
  const max = maxValue || Math.max(...filtered.map((d) => d[valueKey])) * 1.15;
  const stepW = w / filtered.length;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Y-axis ticks */}
        {[0, 0.05, 0.10, 0.15].filter((t) => t <= max).map((t) => (
          <g key={t}>
            <line x1={m.left} y1={m.top + h - (t / max) * h} x2={m.left + w} y2={m.top + h - (t / max) * h} stroke={ink} strokeWidth="1" opacity="0.08" />
            <text x={m.left - 8} y={m.top + h - (t / max) * h + 4} textAnchor="end" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={muted}>
              {t.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Baseline axis */}
        <line x1={m.left} y1={m.top + h} x2={m.left + w} y2={m.top + h} stroke={ink} strokeWidth="1" />

        {/* Bars (thin verticals + cap) */}
        {filtered.map((d, i) => {
          const cx = m.left + i * stepW + stepW / 2;
          const v = d[valueKey];
          const yTop = m.top + h - (v / max) * h;
          return (
            <g key={d.bucket}>
              {/* thin vertical */}
              <line x1={cx} y1={m.top + h} x2={cx} y2={yTop} stroke={ink} strokeWidth="1" opacity="0.3" />
              {/* cap */}
              <line x1={cx - 18} y1={yTop} x2={cx + 18} y2={yTop} stroke={accent} strokeWidth="3" />
              {/* value label */}
              <text x={cx} y={yTop - 8} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="11" fill={ink}>
                {v.toFixed(3)}
              </text>
              {/* bucket label */}
              <text x={cx} y={m.top + h + 18} textAnchor="middle" fontFamily="'Inter Tight', sans-serif" fontSize="11" fill={muted}>
                {d.bucket}
              </text>
              {/* n label */}
              <text x={cx} y={m.top + h + 34} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={muted} opacity="0.7">
                n={d.n}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Headline bar — visualizes the 53% improvement over the always-50% baseline.
// Two horizontal bars stacked: baseline (gray) vs market (accent).
// ---------------------------------------------------------------------------
function ImprovementBar({ baseline, market, label, accent, ink, muted }) {
  const [ref, { width }] = useMeasure();
  const max = baseline * 1.05;
  // Reserve right-side space for the value+caption labels so they never clip.
  const labelReserve = 130;
  const trackW = Math.max(40, width - labelReserve);
  const baselineW = (baseline / max) * trackW;
  const marketW = (market / max) * trackW;
  const improvement = ((baseline - market) / baseline);

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6 }}>
        <span style={{ fontFamily: "'Inter Tight', sans-serif", fontSize: 11, color: muted, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {label}
        </span>
        <span style={{ fontFamily: "'Instrument Serif', serif", fontSize: 18, color: ink, fontStyle: "italic" }}>
          {(improvement * 100).toFixed(1)}% improvement
        </span>
      </div>
      <svg width="100%" height="58" style={{ display: "block" }}>
        {/* Baseline */}
        <g>
          <rect x="0" y="6" width={baselineW} height="18" fill={muted} opacity="0.18" />
          <text x={baselineW + 8} y="20" fontFamily="'JetBrains Mono', monospace" fontSize="11" fill={muted}>
            {baseline.toFixed(4)} · baseline
          </text>
        </g>
        {/* Market */}
        <g>
          <rect x="0" y="32" width={marketW} height="18" fill={accent} />
          <text x={marketW + 8} y="46" fontFamily="'JetBrains Mono', monospace" fontSize="11" fill={ink}>
            {market.toFixed(4)} · markets
          </text>
        </g>
      </svg>
    </div>
  );
}

// Export to window.
Object.assign(window, {
  CalibrationChart,
  CategorySlope,
  BucketChart,
  ImprovementBar,
  useMeasure,
});
