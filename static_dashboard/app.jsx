const COLORS = {
  background: "#f5f2ea",
  paper: "#fffdf8",
  ink: "#182019",
  muted: "#657066",
  line: "#d8d7ca",
  forest: "#214e3d",
  teal: "#2f7d6b",
  mint: "#d9eee6",
  coral: "#d9684f",
  coralSoft: "#f8dfd8",
  amber: "#9a6517",
  amberSoft: "#f6e8c8",
};

function pct(value, digits = 0) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function dateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date);
}

function statusLabel(status) {
  return {
    fixture_only: "Fixture only",
    data_pending: "Data pending",
    validated_real_sample: "Validated real sample",
  }[status] || status;
}

function StatusPill({ status }) {
  const real = status === "validated_real_sample";
  const pending = status === "data_pending";
  return (
    <span className={`status-pill ${real ? "status-real" : pending ? "status-pending" : "status-fixture"}`}>
      <span className="status-dot" />
      {statusLabel(status)}
    </span>
  );
}

function SectionHeader({ eyebrow, title, description }) {
  return (
    <div className="section-header">
      <div className="eyebrow">{eyebrow}</div>
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}

function BucketCard({ bucket }) {
  const hasData = bucket.count > 0;
  return (
    <article className="bucket-card">
      <div className="bucket-topline">
        <strong>{bucket.label}</strong>
        <span>{bucket.count} {bucket.count === 1 ? "market" : "markets"}</span>
      </div>
      {hasData ? (
        <>
          <div className="measure">
            <div className="measure-label"><span>Average probability</span><strong>{pct(bucket.average_probability)}</strong></div>
            <div className="track"><span className="bar probability-bar" style={{ width: pct(bucket.average_probability) }} /></div>
          </div>
          <div className="measure">
            <div className="measure-label"><span>Actually resolved YES</span><strong>{pct(bucket.observed_yes_rate)}</strong></div>
            <div className="track"><span className="bar outcome-bar" style={{ width: pct(bucket.observed_yes_rate) }} /></div>
          </div>
        </>
      ) : (
        <div className="empty-bucket">No included rows in this range.</div>
      )}
    </article>
  );
}

function MetricCard({ label, value, note }) {
  return (
    <article className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-note">{note}</div>
    </article>
  );
}

function MarketTable({ rows }) {
  const [query, setQuery] = React.useState("");
  const [status, setStatus] = React.useState("all");
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    const matchesStatus = status === "all" || row.inclusion_status === status;
    const haystack = [row.title, row.market_id, row.platform, row.outcome_source].filter(Boolean).join(" ").toLowerCase();
    return matchesStatus && (!normalizedQuery || haystack.includes(normalizedQuery));
  });

  return (
    <div className="table-card">
      <div className="table-controls">
        <label className="search-box">
          <span>Search markets</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Title, market ID, platform…"
          />
        </label>
        <div className="filter-group" aria-label="Filter by inclusion status">
          {["all", "included", "excluded"].map((value) => (
            <button
              key={value}
              type="button"
              className={status === value ? "active" : ""}
              onClick={() => setStatus(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <div className="row-count">{filtered.length} shown</div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Probability</th>
              <th>Outcome</th>
              <th>Probability timestamp</th>
              <th>Platform</th>
              <th>Market</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.id} className={row.inclusion_status === "excluded" ? "excluded-row" : ""}>
                <td>
                  <span className={`row-status ${row.inclusion_status}`}>{row.inclusion_status}</span>
                  {row.exclusion_reasons.length ? <div className="reason-text">{row.exclusion_reasons.join(", ")}</div> : null}
                </td>
                <td className="number-cell">{pct(row.probability)}</td>
                <td><span className={`outcome ${row.resolution === "YES" ? "yes" : row.resolution === "NO" ? "no" : "unknown"}`}>{row.resolution || "—"}</span></td>
                <td className="date-cell">{dateTime(row.probability_timestamp)}</td>
                <td className="platform-cell">{row.platform || "—"}</td>
                <td>
                  <div className="market-title">{row.title || "Untitled row"}</div>
                  <div className="market-id">{row.market_id || "Missing market ID"}</div>
                </td>
                <td>
                  {row.source_url ? <a href={row.source_url} target="_blank" rel="noreferrer">Open source ↗</a> : "—"}
                </td>
              </tr>
            ))}
            {!filtered.length ? (
              <tr><td colSpan="7" className="empty-table">No rows match this search.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function App() {
  const data = window.DASHBOARD_DATA;
  const summary = data.summary;
  const fixture = data.data_status === "fixture_only";
  const pending = data.data_status === "data_pending";

  return (
    <div className="app-shell">
      <header className="hero">
        <div className="page hero-inner">
          <div className="hero-kicker">
            <span>Prediction Market Analysis</span>
            <StatusPill status={data.data_status} />
          </div>
          <h1>{data.question}</h1>
          <p className="hero-summary">
            Group probabilities into simple ranges, compare them with what actually happened, and keep every source row inspectable.
          </p>
          <div className={`status-banner ${fixture ? "fixture" : pending ? "pending" : "real"}`}>
            <strong>{statusLabel(data.data_status)}.</strong> {data.status_message}
          </div>
          <div className="scope-strip">
            <div><span>Scope</span><strong>{data.scope}</strong></div>
            <div><span>Data boundary</span><strong>{data.source.platform_boundary}</strong></div>
          </div>
        </div>
      </header>

      <main className="page main-content">
        <section>
          <SectionHeader
            eyebrow="View 1 · Probability check"
            title="Do higher probabilities resolve YES more often?"
            description="Each card compares the average probability in a range with the share of included markets that actually resolved YES."
          />
          <div className="legend"><span><i className="legend-probability" /> Average probability</span><span><i className="legend-outcome" /> Observed YES rate</span></div>
          <div className="bucket-grid">
            {data.buckets.map((bucket) => <BucketCard key={bucket.label} bucket={bucket} />)}
          </div>
        </section>

        <section className="section-space">
          <SectionHeader
            eyebrow="View 2 · Accuracy and coverage"
            title="A small descriptive summary"
            description="These numbers describe only the included rows. They are not a platform ranking, causal result, or trading claim."
          />
          <div className="metric-grid">
            <MetricCard
              label="Included markets"
              value={`${summary.included_count} / ${summary.submitted_count}`}
              note="Rows that passed identity, source, probability, outcome, and timestamp checks."
            />
            <MetricCard
              label="Data coverage"
              value={pct(summary.coverage_rate)}
              note="Share of submitted rows usable for this descriptive analysis."
            />
            <MetricCard
              label="Directional hit rate"
              value={pct(summary.directional_hit_rate)}
              note="50% or higher predicts YES; below 50% predicts NO."
            />
            <MetricCard
              label="Observed YES rate"
              value={pct(summary.observed_yes_rate)}
              note="Share of included markets that ultimately resolved YES."
            />
          </div>
          <div className="claim-boundary"><strong>Claim boundary:</strong> {data.claim_boundary}</div>
          {summary.missing_data.length ? (
            <div className="coverage-note">
              <strong>Why rows were excluded:</strong>
              <div className="reason-chips">
                {summary.missing_data.map((item) => <span key={item.reason}>{item.reason.replaceAll("_", " ")} · {item.count}</span>)}
              </div>
            </div>
          ) : null}
        </section>

        <section className="section-space">
          <SectionHeader
            eyebrow="View 3 · Source table"
            title="Inspect every submitted market"
            description="Search by title, market ID, platform, or outcome source. Excluded rows stay visible so coverage is auditable."
          />
          <MarketTable rows={data.rows} />
        </section>

        <section className="section-space appendix-section">
          <details>
            <summary>Optional technical appendix</summary>
            <div className="appendix-body">
              <div>
                <h3>What the main analysis does</h3>
                <ul>
                  <li>{data.method.bucket_definition}</li>
                  <li>{data.method.observed_rate}</li>
                  <li>{data.method.hit_rate}</li>
                  <li>{data.method.coverage}</li>
                </ul>
              </div>
              <div>
                <h3>Brier score</h3>
                <p>{data.technical_appendix.explanation}</p>
                <div className="technical-values">
                  <span>Sample: <strong>{data.technical_appendix.brier_score === null ? "—" : data.technical_appendix.brier_score.toFixed(3)}</strong></span>
                  <span>Always 50%: <strong>{data.technical_appendix.always_50_brier === null ? "—" : data.technical_appendix.always_50_brier.toFixed(3)}</strong></span>
                </div>
              </div>
              <div>
                <h3>Research appendix</h3>
                <p>The repository retains the more conservative provenance, event-grouping, staleness, and clustered-bootstrap machinery as an isolated research path. None of it is required to understand this dashboard.</p>
              </div>
            </div>
          </details>
        </section>

        <footer>
          <span>Build {data.build_id.slice(0, 12)}</span>
          <span>Source SHA-256 {data.source.sha256.slice(0, 12)}</span>
          <span>{data.data_status}</span>
        </footer>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
