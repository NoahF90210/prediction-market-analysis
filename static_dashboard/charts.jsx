// Standard analytics SVG charts.
// Visual vocabulary: thin axes, faint horizontal gridlines, single accent color,
// fixed y-axis scales for cross-chart comparison, sample sizes in labels.

const { useRef, useEffect, useState } = React;

// ---------------------------------------------------------------------------
// Hook: ResizeObserver-driven width tracking.
// ---------------------------------------------------------------------------
function useMeasure() {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 600, height: 320 });
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

const FONT_SANS = "'Inter Tight', system-ui, sans-serif";
const FONT_MONO = "'JetBrains Mono', monospace";

// ---------------------------------------------------------------------------
// Calibration plot — reliability diagram with diagonal of perfect calibration.
// ---------------------------------------------------------------------------
function CalibrationChart({ data, accent, ink, surface, muted, border }) {
  const [ref, { width }] = useMeasure();
  const height = 360;
  const m = { top: 16, right: 24, bottom: 44, left: 48 };
  const w = Math.max(0, width - m.left - m.right);
  const h = height - m.top - m.bottom;
  const x = (v) => m.left + v * w;
  const y = (v) => m.top + h - v * h;

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const maxN = Math.max(...data.map((d) => d.n));
  const r = (n) => 4 + (n / maxN) * 10;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Gridlines */}
        {ticks.map((t) => (
          <g key={`g-${t}`}>
            <line x1={x(0)} y1={y(t)} x2={x(1)} y2={y(t)} stroke={border} strokeWidth="1" />
            <line x1={x(t)} y1={m.top} x2={x(t)} y2={m.top + h} stroke={border} strokeWidth="1" />
          </g>
        ))}

        {/* Diagonal — perfect calibration */}
        <line
          x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)}
          stroke={muted} strokeWidth="1.5" strokeDasharray="4 4"
        />
        <text x={x(0.97)} y={y(0.97) - 6} textAnchor="end" fontFamily={FONT_SANS} fontSize="11" fill={muted}>
          perfect calibration
        </text>

        {/* Tick labels */}
        {ticks.map((t) => (
          <text
            key={`xt-${t}`}
            x={x(t)} y={m.top + h + 18}
            textAnchor="middle"
            fontFamily={FONT_MONO}
            fontSize="11" fill={muted}
          >
            {Math.round(t * 100)}%
          </text>
        ))}
        {ticks.map((t) => (
          <text
            key={`yt-${t}`}
            x={m.left - 8} y={y(t) + 4}
            textAnchor="end"
            fontFamily={FONT_MONO}
            fontSize="11" fill={muted}
          >
            {Math.round(t * 100)}%
          </text>
        ))}

        {/* Axes */}
        <line x1={m.left} y1={m.top} x2={m.left} y2={m.top + h} stroke={ink} strokeWidth="1" />
        <line x1={m.left} y1={m.top + h} x2={m.left + w} y2={m.top + h} stroke={ink} strokeWidth="1" />

        {/* Axis labels */}
        <text x={m.left + w / 2} y={height - 4} textAnchor="middle" fontFamily={FONT_SANS} fontSize="11" fill={ink} fontWeight="500">
          Forecast probability
        </text>
        <text
          transform={`rotate(-90, 12, ${m.top + h / 2})`}
          x={12} y={m.top + h / 2}
          textAnchor="middle"
          fontFamily={FONT_SANS} fontSize="11" fill={ink} fontWeight="500"
        >
          Observed YES rate
        </text>

        {/* Bucket dots — outline + fill, line drop to diagonal */}
        {data.map((d) => (
          <line
            key={`drop-${d.bucket}`}
            x1={x(d.midpoint)} y1={y(d.observed)}
            x2={x(d.midpoint)} y2={y(d.midpoint)}
            stroke={accent} strokeWidth="1" opacity="0.35"
          />
        ))}
        {data.map((d) => (
          <g key={d.bucket}>
            <circle
              cx={x(d.midpoint)} cy={y(d.observed)}
              r={r(d.n)}
              fill={accent}
              fillOpacity="0.85"
              stroke={surface}
              strokeWidth="1.5"
            />
          </g>
        ))}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Platform interval chart — Brier point estimate ± 95% CI.
// Horizontal: each platform is a row with a thick whisker.
// ---------------------------------------------------------------------------
function PlatformIntervalChart({ platforms, ink, muted, accent, border }) {
  const [ref, { width }] = useMeasure();
  const rowH = 56;
  const m = { top: 32, right: 32, bottom: 36, left: 130 };
  const height = m.top + m.bottom + platforms.length * rowH;
  const w = Math.max(0, width - m.left - m.right);

  const allValues = platforms.flatMap((p) => [p.ci[0], p.ci[1], p.brier]);
  const minV = Math.min(...allValues, 0);
  const maxV = Math.max(...allValues) * 1.04;
  const xScale = (v) => m.left + ((v - minV) / (maxV - minV)) * w;
  const yScale = (i) => m.top + (i + 0.5) * rowH;

  const ticks = niceTicks(minV, maxV, 5);

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Vertical gridlines + tick labels */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={xScale(t)} y1={m.top} x2={xScale(t)} y2={m.top + platforms.length * rowH} stroke={border} strokeWidth="1" />
            <text x={xScale(t)} y={m.top + platforms.length * rowH + 18} textAnchor="middle" fontFamily={FONT_MONO} fontSize="11" fill={muted}>
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <text x={m.left + w / 2} y={height - 4} textAnchor="middle" fontFamily={FONT_SANS} fontSize="11" fill={ink} fontWeight="500">
          Brier score (lower is better)
        </text>

        {/* Rows */}
        {platforms.map((p, i) => {
          const cy = yScale(i);
          const x0 = xScale(p.ci[0]);
          const x1 = xScale(p.ci[1]);
          const xm = xScale(p.brier);
          return (
            <g key={p.name}>
              {/* Label */}
              <text
                x={m.left - 12} y={cy + 5}
                textAnchor="end"
                fontFamily={FONT_SANS} fontSize="13" fill={ink} fontWeight="500"
              >
                {p.name}
              </text>
              <text
                x={m.left - 12} y={cy + 20}
                textAnchor="end"
                fontFamily={FONT_MONO} fontSize="11" fill={muted}
              >
                n = {p.n.toLocaleString()}
              </text>

              {/* CI bar */}
              <line x1={x0} y1={cy} x2={x1} y2={cy} stroke={accent} strokeWidth="3" opacity="0.35" />
              <line x1={x0} y1={cy - 7} x2={x0} y2={cy + 7} stroke={accent} strokeWidth="2" />
              <line x1={x1} y1={cy - 7} x2={x1} y2={cy + 7} stroke={accent} strokeWidth="2" />

              {/* Point estimate */}
              <circle cx={xm} cy={cy} r="6" fill={accent} stroke="#fff" strokeWidth="2" />

              {/* Value labels */}
              <text x={xm} y={cy - 12} textAnchor="middle" fontFamily={FONT_MONO} fontSize="11" fill={ink} fontWeight="600">
                {p.brier.toFixed(4)}
              </text>
              <text x={x0} y={cy + 22} textAnchor="middle" fontFamily={FONT_MONO} fontSize="10" fill={muted}>
                {p.ci[0].toFixed(3)}
              </text>
              <text x={x1} y={cy + 22} textAnchor="middle" fontFamily={FONT_MONO} fontSize="10" fill={muted}>
                {p.ci[1].toFixed(3)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Category bars — grouped bar chart, Polymarket vs Kalshi per category.
// ---------------------------------------------------------------------------
function CategoryBars({ data, ink, muted, accent, border }) {
  const [ref, { width }] = useMeasure();
  const m = { top: 28, right: 24, bottom: 56, left: 56 };
  const groupH = 56;
  const height = m.top + m.bottom + data.length * groupH;
  const w = Math.max(0, width - m.left - m.right);

  const allValues = data.flatMap((d) => [d.polymarket, d.kalshi]);
  const max = Math.max(...allValues, 0.05) * 1.15;

  const ticks = niceTicks(0, max, 5);
  const barH = 12;
  const seriesGap = 4;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Vertical gridlines */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={m.left + (t / max) * w} y1={m.top} x2={m.left + (t / max) * w} y2={m.top + data.length * groupH} stroke={border} strokeWidth="1" />
            <text x={m.left + (t / max) * w} y={m.top + data.length * groupH + 18} textAnchor="middle" fontFamily={FONT_MONO} fontSize="11" fill={muted}>
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <text x={m.left + w / 2} y={height - 6} textAnchor="middle" fontFamily={FONT_SANS} fontSize="11" fill={ink} fontWeight="500">
          Brier score
        </text>

        {/* Y axis line */}
        <line x1={m.left} y1={m.top} x2={m.left} y2={m.top + data.length * groupH} stroke={ink} strokeWidth="1" />

        {data.map((d, i) => {
          const yTop = m.top + i * groupH + 8;
          const polyW = (d.polymarket / max) * w;
          const kalW = (d.kalshi / max) * w;
          return (
            <g key={d.category}>
              {/* Category label */}
              <text
                x={m.left - 10} y={yTop + barH + (seriesGap / 2)}
                textAnchor="end"
                fontFamily={FONT_SANS} fontSize="13" fill={ink} fontWeight="500"
                style={{ textTransform: "capitalize" }}
              >
                {d.category}
              </text>

              {/* Polymarket bar */}
              <rect x={m.left} y={yTop} width={polyW} height={barH} fill={ink} fillOpacity="0.85" />
              <text x={m.left + polyW + 6} y={yTop + barH - 2} fontFamily={FONT_MONO} fontSize="11" fill={ink}>
                {d.polymarket.toFixed(3)} <tspan fill={muted}>· n={d.n_polym}</tspan>
              </text>
              <text x={m.left - 10} y={yTop + barH - 2} textAnchor="end" fontFamily={FONT_SANS} fontSize="10" fill={muted} style={{ display: "none" }}>
                Polymarket
              </text>

              {/* Kalshi bar */}
              <rect x={m.left} y={yTop + barH + seriesGap} width={kalW} height={barH} fill={accent} />
              <text x={m.left + kalW + 6} y={yTop + barH + seriesGap + barH - 2} fontFamily={FONT_MONO} fontSize="11" fill={ink}>
                {d.kalshi.toFixed(3)} <tspan fill={muted}>· n={d.n_kalsh}</tspan>
              </text>
            </g>
          );
        })}

        {/* Legend */}
        <g transform={`translate(${m.left}, ${m.top - 14})`}>
          <rect x="0" y="-9" width="14" height="10" fill={ink} fillOpacity="0.85" />
          <text x="20" y="0" fontFamily={FONT_SANS} fontSize="11" fill={muted}>Polymarket</text>
          <rect x="100" y="-9" width="14" height="10" fill={accent} />
          <text x="120" y="0" fontFamily={FONT_SANS} fontSize="11" fill={muted}>Kalshi</text>
        </g>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bucket bar chart — Brier by bucket. Used for lead time and volume.
// Supports a fixed yMax so bars are comparable across charts.
// ---------------------------------------------------------------------------
function BucketChart({ data, accent, ink, muted, border, yMax }) {
  const [ref, { width }] = useMeasure();
  const height = 280;
  const m = { top: 18, right: 16, bottom: 56, left: 44 };
  const w = Math.max(0, width - m.left - m.right);
  const h = height - m.top - m.bottom;

  const filtered = data.filter((d) => d.bucket !== "unknown");
  const dataMax = Math.max(...filtered.map((d) => d.brier));
  const max = yMax || dataMax * 1.15;
  const stepW = w / filtered.length;
  const barW = Math.min(48, stepW * 0.6);
  const ticks = niceTicks(0, max, 5);

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Y gridlines */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={m.left} y1={m.top + h - (t / max) * h} x2={m.left + w} y2={m.top + h - (t / max) * h} stroke={border} strokeWidth="1" />
            <text x={m.left - 8} y={m.top + h - (t / max) * h + 4} textAnchor="end" fontFamily={FONT_MONO} fontSize="11" fill={muted}>
              {t.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Y axis + baseline */}
        <line x1={m.left} y1={m.top} x2={m.left} y2={m.top + h} stroke={ink} strokeWidth="1" />
        <line x1={m.left} y1={m.top + h} x2={m.left + w} y2={m.top + h} stroke={ink} strokeWidth="1" />

        {filtered.map((d, i) => {
          const cx = m.left + i * stepW + stepW / 2;
          const v = d.brier;
          const yTop = m.top + h - (v / max) * h;
          return (
            <g key={d.bucket}>
              <rect
                x={cx - barW / 2} y={yTop}
                width={barW} height={m.top + h - yTop}
                fill={accent}
                rx="2"
              />
              <text x={cx} y={yTop - 6} textAnchor="middle" fontFamily={FONT_MONO} fontSize="11" fill={ink} fontWeight="600">
                {v.toFixed(3)}
              </text>
              <text x={cx} y={m.top + h + 18} textAnchor="middle" fontFamily={FONT_SANS} fontSize="11" fill={ink}>
                {d.bucket}
              </text>
              <text x={cx} y={m.top + h + 34} textAnchor="middle" fontFamily={FONT_MONO} fontSize="10" fill={muted}>
                n = {d.n}
              </text>
            </g>
          );
        })}

        {/* Y axis label */}
        <text
          transform={`rotate(-90, 10, ${m.top + h / 2})`}
          x={10} y={m.top + h / 2}
          textAnchor="middle"
          fontFamily={FONT_SANS} fontSize="11" fill={ink} fontWeight="500"
        >
          Mean Brier
        </text>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Improvement bar — paired horizontal bars for market vs baseline Brier.
// ---------------------------------------------------------------------------
function ImprovementBar({ baseline, market, label, accent, ink, muted, border }) {
  const [ref, { width }] = useMeasure();
  const labelReserve = 160;
  const trackW = Math.max(40, width - labelReserve);
  const max = baseline * 1.05;
  const baselineW = (baseline / max) * trackW;
  const marketW = (market / max) * trackW;
  const improvement = ((baseline - market) / baseline);
  const improvementColor = improvement >= 0 ? "#15803d" : "#b91c1c";
  const improvementWord = improvement >= 0 ? "better" : "worse";

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, marginBottom: 4 }}>
        <span style={{ fontFamily: FONT_SANS, fontSize: 12, color: ink, fontWeight: 500 }}>
          {label}
        </span>
        <span style={{
          fontFamily: FONT_MONO,
          fontSize: 12,
          color: improvementColor,
          fontWeight: 600,
          fontVariantNumeric: "tabular-nums",
        }}>
          {Math.abs(improvement * 100).toFixed(1)}% {improvementWord}
        </span>
      </div>
      <svg width="100%" height="46" style={{ display: "block" }}>
        {/* Baseline */}
        <g>
          <rect x="0" y="4" width={baselineW} height="14" fill={muted} fillOpacity="0.25" />
          <text x={baselineW + 8} y="15" fontFamily={FONT_MONO} fontSize="11" fill={muted}>
            {baseline.toFixed(4)} · baseline
          </text>
        </g>
        {/* Market */}
        <g>
          <rect x="0" y="24" width={marketW} height="14" fill={accent} />
          <text x={marketW + 8} y="35" fontFamily={FONT_MONO} fontSize="11" fill={ink}>
            {market.toFixed(4)} · markets
          </text>
        </g>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function niceTicks(min, max, count = 5) {
  if (max <= min) return [min];
  const range = max - min;
  const rough = range / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  let step;
  if (norm < 1.5) step = 1 * mag;
  else if (norm < 3) step = 2 * mag;
  else if (norm < 7) step = 5 * mag;
  else step = 10 * mag;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

// Export to window.
Object.assign(window, {
  CalibrationChart,
  PlatformIntervalChart,
  CategoryBars,
  BucketChart,
  ImprovementBar,
  useMeasure,
});
