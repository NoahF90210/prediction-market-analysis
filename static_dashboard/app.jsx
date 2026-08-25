const data = window.DASHBOARD_DATA;

function pct(value, digits = 1) {
  if (value === null || value === undefined) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function pp(value, digits = 2) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)} pp`;
}

function dateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC", timeZoneName: "short",
  }).format(date);
}

function SectionHead({ title, description }) {
  return <div className="section-head"><div><h2>{title}</h2><p>{description}</p></div></div>;
}

function Metric({ label, value, note }) {
  return <article className="card"><div className="card-label">{label}</div><div className="card-value">{value}</div><div className="card-note">{note}</div></article>;
}

function BucketChart() {
  const chartRef = React.useRef(null);
  React.useEffect(() => {
    if (!chartRef.current || !window.Plotly) return undefined;
    const buckets = data.buckets;
    const labels = buckets.map((item) => item.label);
    const ticktext = buckets.map((item) => `${item.label}<br>n = ${item.count.toLocaleString()}`);
    const traces = [
      {
        x: buckets.map((item) => item.label),
        y: buckets.map((item) => item.average_probability),
        name: "Average prediction",
        type: "bar",
        marker: { color: "#2E5CFF" },
        customdata: buckets.map((item) => [item.count, item.gap]),
        hovertemplate: "%{y:.1%}<extra>Average prediction</extra>",
      },
      {
        x: buckets.map((item) => item.label),
        y: buckets.map((item) => item.observed_yes_rate),
        name: "Observed YES",
        type: "bar",
        marker: { color: "#d9684f" },
        customdata: buckets.map((item) => [item.count, item.gap]),
        hovertemplate: "%{y:.1%}<br>Gap: %{customdata[1]:+.1%}<extra>Observed YES</extra>",
      },
    ];
    const layout = {
      barmode: "group",
      bargap: 0.28,
      bargroupgap: 0.08,
      margin: { l: 58, r: 24, t: 18, b: 82 },
      paper_bgcolor: "#fffdf8",
      plot_bgcolor: "#fffdf8",
      font: { family: "Georgia, Times New Roman, serif", color: "#182019" },
      legend: { orientation: "h", y: 1.12, x: 0, font: { size: 12 } },
      xaxis: { title: "Forecast range for YES", tickmode: "array", tickvals: labels, ticktext, fixedrange: true },
      yaxis: { title: "Share of markets resolving YES", range: [0, 1], tickformat: ".0%", fixedrange: true, gridcolor: "#d8d7ca" },
      hovermode: "x unified",
    };
    window.Plotly.newPlot(chartRef.current, traces, layout, { responsive: true, displayModeBar: false });
    return () => window.Plotly.purge(chartRef.current);
  }, []);
  return <div className="chart-shell"><div ref={chartRef} id="bucket-chart" role="img" aria-label="Grouped bar chart comparing average predicted YES probability with observed YES frequency by forecast range" /><p className="chart-caption">The shared 0% to 100% scale makes the height of each prediction and outcome bar directly comparable.</p></div>;
}

function Bucket({ item }) {
  return <article className="bucket">
    <div className="bucket-head"><strong>{item.label}</strong><span>{item.count.toLocaleString()} markets</span></div>
    <div className="bar-chart" aria-label={`${item.label}: average prediction ${pct(item.average_probability)}, observed YES ${pct(item.observed_yes_rate)}`}>
      <div className="bar-axis"><span>100%</span><span>50%</span><span>0%</span></div>
      <div className="bar-plot"><div className="bar-columns">
        <div className="bar-column"><strong>{pct(item.average_probability)}</strong><div className="bar-track"><span className="vertical-bar prediction" style={{ height: pct(item.average_probability) }} /></div><span>Predicted</span></div>
        <div className="bar-column"><strong>{pct(item.observed_yes_rate)}</strong><div className="bar-track"><span className="vertical-bar outcome" style={{ height: pct(item.observed_yes_rate) }} /></div><span>Actual YES</span></div>
      </div></div>
    </div>
    <div className={`gap ${item.gap < 0 ? "negative" : "positive"}`}>Gap: {pp(item.gap)}</div>
  </article>;
}

function Robustness({ item }) {
  return <div className="robust-column">
    <h3>{item.title}</h3>
    <p>{item.description}</p>
    <div className="robust-stat">
      <span>Markets<strong>{item.included_count.toLocaleString()}</strong></span>
      <span>Average prediction<strong>{pct(item.average_probability)}</strong></span>
      <span>Observed YES<strong>{pct(item.observed_yes_rate)}</strong></span>
    </div>
    <div className={`gap ${item.gap < 0 ? "negative" : "positive"}`}>Gap: {pp(item.gap)}</div>
  </div>;
}

function EvidenceTable() {
  return <div className="evidence">
    <div className="evidence-head"><div><div className="eyebrow">Evidence sample</div><h3>Real rows behind the result</h3></div><p>This is a small linked sample, not the full 75,036-row dataset.</p></div>
    <div className="table-scroll"><table><thead><tr><th>Market</th><th>Prediction</th><th>Outcome</th><th>Resolved</th><th>Source</th></tr></thead><tbody>
      {data.evidence_sample.map((row) => <tr key={row.market_id}><td><div className="market-title">{row.title}</div><div className="market-id">{row.market_id} · {row.bucket}</div></td><td className="probability">{pct(row.probability)}</td><td><span className={`outcome ${row.resolution === "YES" ? "yes" : "no"}`}>{row.resolution}</span></td><td className="date">{dateTime(row.resolution_timestamp)}</td><td><a href={row.market_url} target="_blank" rel="noreferrer">Open market ↗</a></td></tr>)}
    </tbody></table></div>
  </div>;
}

function App() {
  const s = data.summary;
  const r = data.robustness;
  return <>
    <header className="hero"><div className="page hero-inner">
      <div className="kicker"><a className="brand-lockup" href="https://polymarket.com" target="_blank" rel="noreferrer"><img src="polymarket-icon-white.png" alt="" /><span>Polymarket</span></a><span className="project-label">Prediction Market Analysis by Noah Feldman</span></div>
      <div className="scope"><div><span>Observation window</span><strong>January 1 through December 31, 2025 UTC</strong></div><div><span>Included</span><strong>{s.included_count.toLocaleString()} markets · {s.event_count.toLocaleString()} events</strong></div></div>
    </div></header>
    <main className="page">
      <section><SectionHead title="Do 24-hour probabilities match what happened?" description="Across the full market-level sample, Polymarket's average YES probability was 27.1%, and YES happened 24.6% of the time. The cards below show exactly where that comparison comes from." /><div className="cards"><Metric label="Average prediction" value={pct(s.average_probability, 1)} note="The average YES probability assigned before resolution." /><Metric label="Observed YES" value={pct(s.observed_yes_rate, 1)} note="How often those markets actually finished YES." /><Metric label="Overall gap" value={pp(s.gap, 1)} note="Observed YES minus predicted YES." /><Metric label="Included markets" value={s.included_count.toLocaleString()} note={`${s.event_count.toLocaleString()} unique Polymarket events represented.`} /></div></section>
      <section><SectionHead title="Probability ranges versus outcomes" description="A bucket is just a group of markets whose individual YES forecasts fell inside the same range. We average those forecasts, then count how often the markets actually resolved YES." /><div className="plain-explainer"><strong>Example:</strong> the 40% to 60% bucket contains 14,139 markets. Their individual forecasts averaged 49.4%, so they were basically saying “about a coin flip.” YES actually happened in 39.8% of them, or about 4 out of 10.</div><BucketChart /></section>
      <section><SectionHead title="Related markets change the weighting" description="One event can contain many related markets. The primary view weights every market equally, while the check below selects one deterministic market per event." /><div className="robustness"><Robustness item={{ title: "All markets", description: "Primary market-level view. Every included market contributes one row.", included_count: s.included_count, average_probability: s.average_probability, observed_yes_rate: s.observed_yes_rate, gap: s.gap }} /><Robustness item={{ title: "One per event", description: "Robustness check using the lexicographically smallest market ID within each event.", included_count: r.included_count, average_probability: r.average_probability, observed_yes_rate: r.observed_yes_rate, gap: r.gap }} /></div><div className="note"><strong>How to read this:</strong> the overall gap changes from {pp(s.gap)} to {pp(r.gap)} when related-market concentration is reduced. Treat the result as a descriptive market-level analysis, not an event-independent estimate.</div></section>
      <section><SectionHead title="Inspect the underlying rows" description="Every included row has a market ID, event ID, pre-result probability timestamp, resolution timestamp, and linked Polymarket source." /><EvidenceTable /></section>
      <section><SectionHead title="What this does and does not claim" description="The project is intentionally simple: get the timing and outcome definitions right, then compare predicted probabilities with what happened." /><details><summary>Open methodology and limitations</summary><div className="details-body"><div><h3>Method</h3><ul><li>{data.method.snapshot}</li><li>{data.method.buckets}</li><li>{data.method.gap}</li><li>{data.method.outcome}</li></ul></div><div><h3>Coverage</h3><p>{s.included_count.toLocaleString()} of {s.submitted_count.toLocaleString()} YES/NO candidates had usable price history.</p><p>{data.exclusions.map((item) => `${item.count.toLocaleString()} ${item.reason}`).join("; ")}.</p></div><div><h3>Limitations</h3><ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div></div></details></section>
      <footer><span>Frozen dataset {data.build_id.slice(0, 12)}</span><span>Source SHA-256 {data.source.sha256.slice(0, 12)}</span><span>Local verified build</span></footer>
    </main>
  </>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
