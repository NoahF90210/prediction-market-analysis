const DATA_URL = "../data/cleaned/accuracy_markets.csv";
const state = {
  rows: [],
  platform: new Set(),
  category: new Set(),
  sourceMode: "all",
  metricMode: "brier",
};

const els = {
  platformFilter: document.querySelector("#platformFilter"),
  categoryFilter: document.querySelector("#categoryFilter"),
  volumeFilter: document.querySelector("#volumeFilter"),
  volumeOutput: document.querySelector("#volumeOutput"),
  probMin: document.querySelector("#probMin"),
  probMax: document.querySelector("#probMax"),
  searchBox: document.querySelector("#searchBox"),
  resetFilters: document.querySelector("#resetFilters"),
  sourceMode: document.querySelector("#sourceMode"),
  metricMode: document.querySelector("#metricMode"),
  dataFreshness: document.querySelector("#dataFreshness"),
  activeScope: document.querySelector("#activeScope"),
  qualitySummary: document.querySelector("#qualitySummary"),
  qualityChips: document.querySelector("#qualityChips"),
  metricMarkets: document.querySelector("#metricMarkets"),
  metricBrier: document.querySelector("#metricBrier"),
  metricForecast: document.querySelector("#metricForecast"),
  metricLogLoss: document.querySelector("#metricLogLoss"),
  metricLeadTime: document.querySelector("#metricLeadTime"),
  metricVolume: document.querySelector("#metricVolume"),
  activeFilters: document.querySelector("#activeFilters"),
  comparisonSubtitle: document.querySelector("#comparisonSubtitle"),
  comparisonCards: document.querySelector("#comparisonCards"),
  sampleWarning: document.querySelector("#sampleWarning"),
  findingCards: document.querySelector("#findingCards"),
  sourceSummary: document.querySelector("#sourceSummary"),
  brierLegend: document.querySelector("#brierLegend"),
  calibrationLegend: document.querySelector("#calibrationLegend"),
  durationLegend: document.querySelector("#durationLegend"),
  brierChart: document.querySelector("#brierChart"),
  calibrationChart: document.querySelector("#calibrationChart"),
  durationChart: document.querySelector("#durationChart"),
  volumeChart: document.querySelector("#volumeChart"),
  primaryChartTitle: document.querySelector("#primaryChartTitle"),
  primaryChartSubtitle: document.querySelector("#primaryChartSubtitle"),
  primaryAxisNote: document.querySelector("#primaryAxisNote"),
  marketRows: document.querySelector("#marketRows"),
};

const DURATION_ORDER = ["<1 day", "1-7 days", "7-30 days", "30+ days", "unknown"];
const VOLUME_ORDER = ["$100k-$250k", "$250k-$1m", "$1m-$5m", "$5m+", "unknown"];

function parseCsv(text) {
  const rows = [];
  let field = "";
  let row = [];
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"' && quoted && next === '"') {
      field += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(field);
      field = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(field);
      if (row.some((value) => value.length)) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  const headers = rows.shift();
  return rows.map((values) => Object.fromEntries(headers.map((header, i) => [header, values[i] ?? ""])));
}

function formatTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Updated time unavailable";
  return `Updated ${date.toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function prepareRows(rows) {
  return rows.map((row) => {
    const forecast = toNumber(row.forecast_prob);
    const outcome = row.resolution === "YES" ? 1 : 0;
    const clipped = Math.min(1 - 1e-6, Math.max(1e-6, forecast));
    const openTime = row.open_time ? new Date(row.open_time) : null;
    const closeTime = row.close_time ? new Date(row.close_time) : null;
    const daysToResolution = openTime && closeTime ? (closeTime - openTime) / 86400000 : null;
    return {
      ...row,
      forecast_prob: forecast,
      volume: toNumber(row.volume),
      outcome,
      brier: (forecast - outcome) ** 2,
      log_loss: -((outcome * Math.log(clipped)) + ((1 - outcome) * Math.log(1 - clipped))),
      days_to_resolution: Number.isFinite(daysToResolution) ? daysToResolution : null,
      duration_bucket: durationBucket(daysToResolution),
      volume_bucket: volumeBucket(toNumber(row.volume)),
    };
  });
}

function durationBucket(days) {
  if (!Number.isFinite(days)) return "unknown";
  if (days < 1) return "<1 day";
  if (days < 7) return "1-7 days";
  if (days < 30) return "7-30 days";
  return "30+ days";
}

function volumeBucket(volume) {
  if (!Number.isFinite(volume)) return "unknown";
  if (volume < 250000) return "$100k-$250k";
  if (volume < 1000000) return "$250k-$1m";
  if (volume < 5000000) return "$1m-$5m";
  return "$5m+";
}

function money(value) {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function percent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function number(value, digits = 3) {
  return Number.isFinite(value) ? value.toFixed(digits) : "n/a";
}

function leadTime(value) {
  if (!Number.isFinite(value)) return "n/a";
  if (value < 1) return `${(value * 24).toFixed(1)}h`;
  return `${value.toFixed(1)}d`;
}

function mean(rows, key) {
  if (!rows.length) return 0;
  return rows.reduce((sum, row) => sum + row[key], 0) / rows.length;
}

function groupBy(rows, keys) {
  const map = new Map();
  rows.forEach((row) => {
    const id = keys.map((key) => row[key]).join("|");
    if (!map.has(id)) {
      map.set(id, { rows: [], values: Object.fromEntries(keys.map((key) => [key, row[key]])) });
    }
    map.get(id).rows.push(row);
  });
  return [...map.values()].map((group) => ({
    ...group.values,
    n: group.rows.length,
    brier: mean(group.rows, "brier"),
    logLoss: mean(group.rows, "log_loss"),
    avgForecast: mean(group.rows, "forecast_prob"),
    observedYes: mean(group.rows, "outcome"),
    calibrationGap: Math.abs(mean(group.rows, "forecast_prob") - mean(group.rows, "outcome")),
    avgLeadTime: mean(group.rows.filter((row) => Number.isFinite(row.days_to_resolution)), "days_to_resolution"),
    avgVolume: mean(group.rows, "volume"),
  }));
}

function metricLabel(mode) {
  if (mode === "log_loss") return "Log Loss";
  if (mode === "calibration_gap") return "Calibration Gap";
  return "Brier Score";
}

function metricDirection(mode) {
  return "Lower is better.";
}

function sourceModeLabel(mode) {
  if (mode === "history") return "exact history";
  if (mode === "snapshot_fallback") return "approximate fallback";
  return "all rows";
}

function metricValue(row, mode) {
  if (mode === "log_loss") return row.logLoss ?? row.log_loss ?? 0;
  if (mode === "calibration_gap") {
    const observed = row.observedYes ?? row.outcome ?? 0;
    const forecast = row.avgForecast ?? row.forecast_prob ?? 0;
    return Math.abs(forecast - observed);
  }
  return row.brier ?? 0;
}

function sampleWithReplacement(rows) {
  const sample = [];
  for (let i = 0; i < rows.length; i += 1) {
    sample.push(rows[Math.floor(Math.random() * rows.length)]);
  }
  return sample;
}

function bootstrapCI(rows, mode, iterations = 250) {
  if (!rows.length) return null;
  const stats = [];
  for (let i = 0; i < iterations; i += 1) {
    const sample = sampleWithReplacement(rows);
    stats.push(metricValue(groupBy(sample, [])[0] || sample[0], mode));
  }
  stats.sort((a, b) => a - b);
  const lower = stats[Math.floor(iterations * 0.025)];
  const upper = stats[Math.floor(iterations * 0.975)];
  return { lower, upper };
}

function fillSelect(select, values) {
  select.innerHTML = "";
  values.forEach((value) => {
    const label = document.createElement("label");
    label.className = "check-item";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = true;
    const span = document.createElement("span");
    span.textContent = value;
    label.append(input, span);
    select.append(label);
  });
}

function selectedValues(select) {
  return new Set(
    [...select.querySelectorAll('input[type="checkbox"]:checked')].map((input) => input.value)
  );
}

function setDefaults() {
  const platforms = [...new Set(state.rows.map((row) => row.platform))].sort();
  const categories = [...new Set(state.rows.map((row) => row.category))].sort();
  const maxVolume = Math.max(...state.rows.map((row) => row.volume));
  fillSelect(els.platformFilter, platforms);
  fillSelect(els.categoryFilter, categories);
  els.volumeFilter.max = String(Math.ceil(maxVolume / 100000) * 100000);
  els.volumeFilter.value = "100000";
  els.probMin.value = "0";
  els.probMax.value = "100";
  els.searchBox.value = "";
}

function filteredRows() {
  const platforms = selectedValues(els.platformFilter);
  const categories = selectedValues(els.categoryFilter);
  const minVolume = toNumber(els.volumeFilter.value);
  const minProb = Math.max(0, Math.min(100, toNumber(els.probMin.value))) / 100;
  const maxProb = Math.max(0, Math.min(100, toNumber(els.probMax.value))) / 100;
  const search = els.searchBox.value.trim().toLowerCase();
  els.volumeOutput.value = `${money(minVolume)}+`;
  return state.rows.filter((row) => {
    const matchesSearch = !search || row.title.toLowerCase().includes(search);
    const matchesSource = state.sourceMode === "all" || row.forecast_source === state.sourceMode;
    return (
      platforms.has(row.platform) &&
      categories.has(row.category) &&
      matchesSource &&
      row.volume >= minVolume &&
      row.forecast_prob >= Math.min(minProb, maxProb) &&
      row.forecast_prob <= Math.max(minProb, maxProb) &&
      matchesSearch
    );
  });
}

function setSvgSize(svg) {
  const box = svg.getBoundingClientRect();
  const width = Math.max(320, Math.floor(box.width));
  const height = Math.max(320, Math.floor(box.height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  return { width, height };
}

function clearSvg(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  return el;
}

function drawBrierChart(rows) {
  const svg = els.brierChart;
  clearSvg(svg);
  const { width, height } = setSvgSize(svg);
  const margin = { top: 24, right: 24, bottom: 54, left: 56 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;
  const mode = state.metricMode;
  const data = groupBy(rows, ["category", "platform"]).sort((a, b) => a.category.localeCompare(b.category));
  if (!data.length) return;
  const maxMetric = Math.max(0.1, ...data.map((d) => metricValue(d, mode))) * 1.15;
  const categories = [...new Set(data.map((d) => d.category))];
  const platforms = [...new Set(data.map((d) => d.platform))];
  const groupW = chartW / categories.length;
  const barW = Math.min(56, (groupW - 28) / platforms.length);

  svg.append(svgEl("line", { x1: margin.left, y1: margin.top + chartH, x2: width - margin.right, y2: margin.top + chartH, class: "axis" }));
  svg.append(svgEl("line", { x1: margin.left, y1: margin.top, x2: margin.left, y2: margin.top + chartH, class: "axis" }));

  for (let i = 0; i <= 4; i += 1) {
    const value = (maxMetric / 4) * i;
    const y = margin.top + chartH - (value / maxMetric) * chartH;
    svg.append(svgEl("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "grid-line" }));
    const label = svgEl("text", { x: margin.left - 10, y: y + 4, "text-anchor": "end", class: "tick-label" });
    label.textContent = value.toFixed(2);
    svg.append(label);
  }

  categories.forEach((category, catIndex) => {
    const cx = margin.left + catIndex * groupW + groupW / 2;
    const label = svgEl("text", { x: cx, y: height - 18, "text-anchor": "middle", class: "tick-label" });
    label.textContent = category;
    svg.append(label);

    platforms.forEach((platform, platformIndex) => {
      const point = data.find((d) => d.category === category && d.platform === platform);
      if (!point) return;
      const x = cx - ((platforms.length * barW) / 2) + platformIndex * barW + 4;
      const barH = (metricValue(point, mode) / maxMetric) * chartH;
      const y = margin.top + chartH - barH;
      const className = platform === "kalshi" ? "bar-elections" : "bar-sports";
      svg.append(svgEl("rect", {
        x, y, width: barW - 8, height: barH, rx: 4,
        class: className,
      }));
      const value = svgEl("text", { x: x + (barW - 8) / 2, y: y - 7, "text-anchor": "middle", class: "tick-label" });
      value.textContent = number(metricValue(point, mode));
      svg.append(value);
    });
  });
}

function calibrationRows(rows) {
  const buckets = Array.from({ length: 10 }, (_, i) => ({
    low: i / 10,
    high: (i + 1) / 10,
    rows: [],
  }));
  rows.forEach((row) => {
    const index = Math.min(9, Math.floor(row.forecast_prob * 10));
    buckets[index].rows.push(row);
  });
  return buckets.filter((bucket) => bucket.rows.length).map((bucket) => ({
    label: `${Math.round(bucket.low * 100)}-${Math.round(bucket.high * 100)}%`,
    n: bucket.rows.length,
    avgForecast: mean(bucket.rows, "forecast_prob"),
    observedYes: mean(bucket.rows, "outcome"),
  }));
}

function drawCalibrationChart(rows) {
  const svg = els.calibrationChart;
  clearSvg(svg);
  const { width, height } = setSvgSize(svg);
  const margin = { top: 24, right: 28, bottom: 48, left: 54 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;
  const x = (value) => margin.left + value * chartW;
  const y = (value) => margin.top + chartH - value * chartH;
  const data = calibrationRows(rows);

  for (let i = 0; i <= 5; i += 1) {
    const value = i / 5;
    svg.append(svgEl("line", { x1: x(0), y1: y(value), x2: x(1), y2: y(value), class: "grid-line" }));
    svg.append(svgEl("line", { x1: x(value), y1: y(0), x2: x(value), y2: y(1), class: "grid-line" }));
    const yLabel = svgEl("text", { x: margin.left - 10, y: y(value) + 4, "text-anchor": "end", class: "tick-label" });
    yLabel.textContent = `${Math.round(value * 100)}%`;
    svg.append(yLabel);
    const xLabel = svgEl("text", { x: x(value), y: height - 18, "text-anchor": "middle", class: "tick-label" });
    xLabel.textContent = `${Math.round(value * 100)}%`;
    svg.append(xLabel);
  }
  svg.append(svgEl("line", { x1: x(0), y1: y(0), x2: x(1), y2: y(1), class: "diagonal" }));

  data.forEach((point) => {
    const radius = Math.max(6, Math.sqrt(point.n) * 1.6);
    const dot = svgEl("circle", {
      cx: x(point.avgForecast),
      cy: y(point.observedYes),
      r: radius,
      class: "dot",
    });
    dot.append(svgEl("title"));
    dot.firstChild.textContent = `${point.label}: ${point.n} markets, forecast ${percent(point.avgForecast)}, observed ${percent(point.observedYes)}`;
    svg.append(dot);
  });
}

function renderMetrics(rows) {
  const totalVolume = rows.reduce((sum, row) => sum + row.volume, 0);
  const leadTimeRows = rows.filter((row) => Number.isFinite(row.days_to_resolution));
  els.metricMarkets.textContent = rows.length.toLocaleString();
  els.metricBrier.textContent = rows.length ? mean(rows, "brier").toFixed(3) : "n/a";
  els.metricForecast.textContent = rows.length ? percent(mean(rows, "forecast_prob")) : "n/a";
  els.metricLogLoss.textContent = rows.length ? number(mean(rows, "log_loss")) : "n/a";
  els.metricLeadTime.textContent = leadTimeRows.length ? leadTime(mean(leadTimeRows, "days_to_resolution")) : "n/a";
  els.metricVolume.textContent = money(totalVolume);
}

function renderScope(rows) {
  const platforms = [...new Set(rows.map((row) => row.platform))];
  const categories = [...new Set(rows.map((row) => row.category))];
  els.activeScope.textContent = `${platforms.join(" + ")} | ${categories.join(" + ")} | ${rows.length.toLocaleString()} markets`;
}

function renderQuality(rows) {
  const allHistory = rows.filter((row) => row.forecast_source === "history").length;
  const allFallback = rows.filter((row) => row.forecast_source === "snapshot_fallback").length;
  els.qualitySummary.textContent = state.sourceMode === "all"
    ? "This view mixes exact history-based forecasts with Kalshi snapshot fallback rows. Cross-platform comparisons are informative, but not fully apples-to-apples."
    : state.sourceMode === "history"
      ? "This view is restricted to history-based forecasts only, which is the most methodologically comparable slice."
      : "This view isolates snapshot fallback rows. Use it to inspect approximate coverage rather than make the strongest platform claims.";
  els.qualityChips.innerHTML = "";
  [
    `History-based rows: ${allHistory.toLocaleString()}`,
    `Fallback rows: ${allFallback.toLocaleString()}`,
    `Source mode: ${sourceModeLabel(state.sourceMode)}`
  ].forEach((text) => {
    const el = document.createElement("span");
    el.className = "quality-chip";
    el.textContent = text;
    els.qualityChips.append(el);
  });
}

function renderActiveFilters(rows) {
  const chips = [
    `Platforms: ${[...selectedValues(els.platformFilter)].join(", ")}`,
    `Categories: ${[...selectedValues(els.categoryFilter)].join(", ")}`,
    `Volume: ${els.volumeOutput.value}`,
    `Forecast probability: ${els.probMin.value}% to ${els.probMax.value}%`,
    `Data confidence: ${sourceModeLabel(state.sourceMode)}`,
    `Metric: ${metricLabel(state.metricMode)}`,
  ];
  if (els.searchBox.value.trim()) chips.push(`Search: ${els.searchBox.value.trim()}`);
  if (!rows.length) chips.push("No rows in current slice");
  els.activeFilters.innerHTML = "";
  chips.forEach((text) => {
    const el = document.createElement("span");
    el.className = "filter-chip";
    el.textContent = text;
    els.activeFilters.append(el);
  });
}

function renderComparison(rows) {
  const mode = state.metricMode;
  const platformGroups = groupBy(rows, ["platform"]).sort((a, b) => metricValue(a, mode) - metricValue(b, mode));
  els.comparisonCards.innerHTML = "";
  els.sampleWarning.textContent = "";
  if (!platformGroups.length) {
    els.comparisonSubtitle.textContent = "No rows in the current filtered slice.";
    return;
  }

  const cards = platformGroups.map((group) => {
    const platformRows = rows.filter((row) => row.platform === group.platform);
    const ci = bootstrapCI(platformRows, mode);
    return { ...group, ci };
  });

  if (cards.length >= 2) {
    const best = cards[0];
    const next = cards[1];
    els.comparisonSubtitle.textContent = `${best.platform} currently leads on ${metricLabel(mode).toLowerCase()} in this filtered view: ${number(metricValue(best, mode))} versus ${number(metricValue(next, mode))}.`;
  } else {
    els.comparisonSubtitle.textContent = `Only ${cards[0].platform} is present in the current filtered view.`;
  }

  cards.forEach((card) => {
    const el = document.createElement("article");
    el.className = "comparison-card";
    const ciText = card.ci ? `${number(card.ci.lower)} to ${number(card.ci.upper)}` : "n/a";
    el.innerHTML = `
      <span>${card.platform}</span>
      <strong>${number(metricValue(card, mode))}</strong>
      <p>${metricLabel(mode)} with ${card.n.toLocaleString()} markets. Bootstrap 95% CI: ${ciText}.</p>
    `;
    els.comparisonCards.append(el);
  });

  const warnings = [];
  if (rows.length < 100) warnings.push(`Only ${rows.length} markets are in this slice, so comparisons will be noisy.`);
  cards.forEach((card) => {
    if (card.n < 50) warnings.push(`${card.platform} has only ${card.n} markets in the current view.`);
  });
  if (state.sourceMode === "all" && rows.some((row) => row.forecast_source === "snapshot_fallback")) {
    warnings.push("This slice mixes exact history rows with fallback rows, so cross-platform comparisons should be treated as directional.");
  }
  els.sampleWarning.textContent = warnings.join(" ");
}

function renderFindings(rows) {
  const findings = [];
  const platformGroups = groupBy(rows, ["platform"]).sort((a, b) => a.brier - b.brier);
  if (platformGroups.length >= 2) {
    const best = platformGroups[0];
    const worst = platformGroups[platformGroups.length - 1];
    findings.push({
      label: "Platform comparison",
      value: `${best.platform} leads`,
      body: `${best.platform} has the lower Brier score in the current view, ${number(best.brier)} versus ${number(worst.brier)} for ${worst.platform}.`,
    });
  }

  const durationGroups = groupBy(rows, ["duration_bucket"])
    .filter((group) => group.duration_bucket !== "unknown")
    .sort((a, b) => DURATION_ORDER.indexOf(a.duration_bucket) - DURATION_ORDER.indexOf(b.duration_bucket));
  if (durationGroups.length) {
    const bestDuration = [...durationGroups].sort((a, b) => a.brier - b.brier)[0];
    findings.push({
      label: "Lead-time pattern",
      value: bestDuration.duration_bucket,
      body: `Markets in the ${bestDuration.duration_bucket} bucket have the lowest Brier score in the current view at ${number(bestDuration.brier)}.`,
    });
  }

  const sourceGroups = groupBy(rows, ["platform", "forecast_source"]).sort((a, b) => b.n - a.n);
  if (sourceGroups.length) {
    const largest = sourceGroups[0];
    findings.push({
      label: "Coverage note",
      value: `${largest.n.toLocaleString()} rows`,
      body: `The largest source slice is ${largest.platform} with ${largest.forecast_source || "unknown"} forecasts, which matters when comparing methodological confidence across platforms.`,
    });
  }

  const calibrationGroups = groupBy(rows, ["platform"]).sort((a, b) => a.calibrationGap - b.calibrationGap);
  if (calibrationGroups.length) {
    const bestCal = calibrationGroups[0];
    findings.push({
      label: "Calibration gap",
      value: percent(bestCal.calibrationGap),
      body: `${bestCal.platform} has the smallest absolute gap between average forecast and observed YES rate in the current view.`,
    });
  }

  els.findingCards.innerHTML = "";
  findings.forEach((finding) => {
    const card = document.createElement("article");
    card.className = "finding-card";
    card.innerHTML = `
      <span>${finding.label}</span>
      <strong>${finding.value}</strong>
      <p>${finding.body}</p>
    `;
    els.findingCards.append(card);
  });
}

function renderSources(rows) {
  const groups = groupBy(rows, ["platform", "forecast_source"]).sort((a, b) => b.n - a.n);
  els.sourceSummary.innerHTML = "";
  groups.forEach((group) => {
    const pill = document.createElement("article");
    pill.className = "source-pill";
    pill.innerHTML = `
      <span>${group.platform} · ${group.forecast_source || "unknown"}</span>
      <strong>${group.n.toLocaleString()}</strong>
    `;
    els.sourceSummary.append(pill);
  });
}

function renderLegend(container, items) {
  if (!container) return;
  container.innerHTML = "";
  items.forEach((item) => {
    const el = document.createElement("div");
    el.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = item.dot ? "legend-swatch legend-dot" : "legend-swatch";
    swatch.style.background = item.color;
    if (item.size) {
      swatch.style.width = `${item.size}px`;
      swatch.style.height = `${item.size}px`;
    }
    const text = document.createElement("span");
    text.textContent = item.label;
    el.append(swatch, text);
    container.append(el);
  });
}

function drawGroupedBarChart(svg, rows, key, orderedLabels, titleMetric) {
  clearSvg(svg);
  const { width, height } = setSvgSize(svg);
  const margin = { top: 24, right: 24, bottom: 54, left: 56 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;
  const data = groupBy(rows, [key]).filter((group) => group[key] !== "unknown");
  if (!data.length) return;
  data.sort((a, b) => orderedLabels.indexOf(a[key]) - orderedLabels.indexOf(b[key]));
  const maxValue = Math.max(0.25, ...data.map((d) => d.brier)) * 1.15;
  const groupW = chartW / data.length;

  svg.append(svgEl("line", { x1: margin.left, y1: margin.top + chartH, x2: width - margin.right, y2: margin.top + chartH, class: "axis" }));
  svg.append(svgEl("line", { x1: margin.left, y1: margin.top, x2: margin.left, y2: margin.top + chartH, class: "axis" }));

  for (let i = 0; i <= 4; i += 1) {
    const value = (maxValue / 4) * i;
    const y = margin.top + chartH - (value / maxValue) * chartH;
    svg.append(svgEl("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "grid-line" }));
    const label = svgEl("text", { x: margin.left - 10, y: y + 4, "text-anchor": "end", class: "tick-label" });
    label.textContent = value.toFixed(2);
    svg.append(label);
  }

  data.forEach((point, index) => {
    const x = margin.left + index * groupW + groupW * 0.2;
    const barW = groupW * 0.6;
    const barH = (point.brier / maxValue) * chartH;
    const y = margin.top + chartH - barH;
    const rect = svgEl("rect", {
      x, y, width: barW, height: barH, rx: 4,
      class: index % 2 === 0 ? "bar-sports" : "bar-elections",
    });
    const title = svgEl("title");
    title.textContent = `${point[key]}: ${titleMetric(point)}`;
    rect.append(title);
    svg.append(rect);
    const value = svgEl("text", { x: x + barW / 2, y: y - 7, "text-anchor": "middle", class: "tick-label" });
    value.textContent = point.brier.toFixed(3);
    svg.append(value);
    const label = svgEl("text", { x: x + barW / 2, y: height - 18, "text-anchor": "middle", class: "tick-label" });
    label.textContent = point[key];
    svg.append(label);
  });
}

const COLORS = {
  polymarket: "#2563eb",
  kalshi: "#14b8a6",
  teal: "#14b8a6",
  slate: "#334155",
  amber: "#f59e0b",
  rose: "#f43f5e",
  grid: "#e2e8f0",
};

const plotConfig = {
  displayModeBar: false,
  responsive: true,
};

function plotLayout(extra = {}) {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { t: 18, r: 20, b: 58, l: 58 },
    font: {
      family: "Avenir Next, Segoe UI, Helvetica Neue, Arial, sans-serif",
      color: "#334155",
      size: 12,
    },
    hoverlabel: {
      bgcolor: "#0f172a",
      bordercolor: "#0f172a",
      font: { color: "#ffffff" },
    },
    legend: {
      orientation: "h",
      x: 0,
      y: 1.16,
      xanchor: "left",
      yanchor: "top",
      font: { size: 12 },
    },
    xaxis: {
      automargin: true,
      tickfont: { color: "#64748b" },
      gridcolor: "rgba(226, 232, 240, 0)",
      zeroline: false,
      linecolor: COLORS.grid,
    },
    yaxis: {
      rangemode: "tozero",
      tickfont: { color: "#64748b" },
      gridcolor: COLORS.grid,
      zeroline: false,
      linecolor: COLORS.grid,
    },
    bargap: 0.32,
    bargroupgap: 0.12,
    ...extra,
  };
}

function emptyPlot(container, message = "No markets match the current filters.") {
  if (!window.Plotly) {
    container.innerHTML = `<div class="plot-empty">Plotly could not load. Check your connection and refresh the dashboard.</div>`;
    return;
  }
  Plotly.react(
    container,
    [],
    plotLayout({
      annotations: [{
        text: message,
        x: 0.5,
        y: 0.5,
        xref: "paper",
        yref: "paper",
        showarrow: false,
        font: { color: "#64748b", size: 14 },
      }],
      xaxis: { visible: false },
      yaxis: { visible: false },
    }),
    plotConfig
  );
}

function canPlot(container) {
  if (window.Plotly) return true;
  emptyPlot(container);
  return false;
}

function drawBrierChart(rows) {
  const container = els.brierChart;
  if (!canPlot(container)) return;
  const mode = state.metricMode;
  const data = groupBy(rows, ["category", "platform"]).sort((a, b) => a.category.localeCompare(b.category));
  if (!data.length) {
    emptyPlot(container);
    return;
  }

  const categories = [...new Set(data.map((row) => row.category))];
  const platforms = [...new Set(data.map((row) => row.platform))].sort();
  const traces = platforms.map((platform) => ({
    type: "bar",
    name: platform,
    x: categories,
    y: categories.map((category) => {
      const point = data.find((row) => row.category === category && row.platform === platform);
      return point ? metricValue(point, mode) : null;
    }),
    customdata: categories.map((category) => {
      const point = data.find((row) => row.category === category && row.platform === platform);
      return point ? [point.n, percent(point.avgForecast), percent(point.observedYes)] : [0, "n/a", "n/a"];
    }),
    marker: {
      color: COLORS[platform] || COLORS.slate,
      line: { color: "rgba(15, 23, 42, 0.10)", width: 1 },
    },
    hovertemplate:
      "<b>%{x}</b><br>" +
      `${metricLabel(mode)}: %{y:.3f}<br>` +
      "Markets: %{customdata[0]:,}<br>" +
      "Avg forecast: %{customdata[1]}<br>" +
      "Observed YES: %{customdata[2]}<extra>%{fullData.name}</extra>",
  }));

  Plotly.react(
    container,
    traces,
    plotLayout({
      barmode: "group",
      yaxis: {
        ...plotLayout().yaxis,
        title: metricLabel(mode),
      },
    }),
    plotConfig
  );
}

function drawCalibrationChart(rows) {
  const container = els.calibrationChart;
  if (!canPlot(container)) return;
  const data = calibrationRows(rows);
  if (!data.length) {
    emptyPlot(container);
    return;
  }

  const traces = [
    {
      type: "scatter",
      mode: "lines",
      name: "Perfect calibration",
      x: [0, 1],
      y: [0, 1],
      line: { color: "#0f172a", width: 2, dash: "dash" },
      hoverinfo: "skip",
    },
    {
      type: "scatter",
      mode: "markers+lines",
      name: "Observed buckets",
      x: data.map((point) => point.avgForecast),
      y: data.map((point) => point.observedYes),
      text: data.map((point) => point.label),
      customdata: data.map((point) => [point.n]),
      marker: {
        color: data.map((point) => point.observedYes - point.avgForecast),
        colorscale: [
          [0, COLORS.rose],
          [0.5, COLORS.amber],
          [1, COLORS.teal],
        ],
        cmin: -0.4,
        cmax: 0.4,
        size: data.map((point) => Math.max(12, Math.min(42, Math.sqrt(point.n) * 2.8))),
        opacity: 0.86,
        line: { color: "#ffffff", width: 2 },
      },
      line: { color: "rgba(37, 99, 235, 0.34)", width: 2 },
      hovertemplate:
        "<b>%{text}</b><br>" +
        "Avg forecast: %{x:.1%}<br>" +
        "Observed YES: %{y:.1%}<br>" +
        "Markets: %{customdata[0]:,}<extra></extra>",
    },
  ];

  Plotly.react(
    container,
    traces,
    plotLayout({
      xaxis: {
        ...plotLayout().xaxis,
        title: "Average forecast probability",
        range: [0, 1],
        tickformat: ".0%",
        gridcolor: COLORS.grid,
      },
      yaxis: {
        ...plotLayout().yaxis,
        title: "Observed YES rate",
        range: [0, 1],
        tickformat: ".0%",
      },
    }),
    plotConfig
  );
}

function drawGroupedBarChart(container, rows, key, orderedLabels, titleMetric) {
  if (!canPlot(container)) return;
  const data = groupBy(rows, [key])
    .filter((group) => group[key] !== "unknown")
    .sort((a, b) => orderedLabels.indexOf(a[key]) - orderedLabels.indexOf(b[key]));

  if (!data.length) {
    emptyPlot(container);
    return;
  }

  Plotly.react(
    container,
    [{
      type: "bar",
      x: data.map((point) => point[key]),
      y: data.map((point) => point.brier),
      text: data.map((point) => point.brier.toFixed(3)),
      textposition: "outside",
      cliponaxis: false,
      customdata: data.map((point) => [point.n, titleMetric(point)]),
      marker: {
        color: data.map((_, index) => index % 2 === 0 ? COLORS.polymarket : COLORS.kalshi),
        line: { color: "rgba(15, 23, 42, 0.10)", width: 1 },
      },
      hovertemplate:
        "<b>%{x}</b><br>" +
        "Brier score: %{y:.3f}<br>" +
        "Markets: %{customdata[0]:,}<br>" +
        "%{customdata[1]}<extra></extra>",
    }],
    plotLayout({
      showlegend: false,
      yaxis: {
        ...plotLayout().yaxis,
        title: "Average Brier score",
      },
    }),
    plotConfig
  );
}

function renderTable(rows) {
  const visible = rows.sort((a, b) => b.volume - a.volume).slice(0, 250);
  els.marketRows.innerHTML = "";
  if (!visible.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td class="empty" colspan="8">No markets match the current filters.</td>`;
    els.marketRows.append(row);
    return;
  }
  visible.forEach((market) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${market.platform}</td>
      <td>${market.category}</td>
      <td>${market.title}</td>
      <td>${market.resolution}</td>
      <td>${percent(market.forecast_prob)}</td>
      <td>${market.forecast_source || "unknown"}</td>
      <td>${market.brier.toFixed(3)}</td>
      <td>${money(market.volume)}</td>
    `;
    els.marketRows.append(row);
  });
}

function render() {
  const rows = filteredRows();
  renderScope(rows);
  renderQuality(rows);
  renderMetrics(rows);
  renderActiveFilters(rows);
  renderComparison(rows);
  renderFindings(rows);
  renderSources(rows);
  els.primaryChartTitle.textContent = metricLabel(state.metricMode);
  els.primaryChartSubtitle.textContent = "Platform comparison by category.";
  els.primaryAxisNote.textContent = `Y-axis: average ${metricLabel(state.metricMode).toLowerCase()}. X-axis: market category. ${metricDirection(state.metricMode)}`;
  drawBrierChart(rows);
  drawCalibrationChart(rows);
  drawGroupedBarChart(
    els.durationChart,
    rows,
    "duration_bucket",
    DURATION_ORDER,
    (point) => `${point.n} markets, Brier ${number(point.brier)}, lead time ${leadTime(point.avgLeadTime)}`
  );
  drawGroupedBarChart(
    els.volumeChart,
    rows,
    "volume_bucket",
    VOLUME_ORDER,
    (point) => `${point.n} markets, Brier ${number(point.brier)}, avg volume ${money(point.avgVolume)}`
  );
  renderTable(rows);
}

function addListeners() {
  [
    els.volumeFilter,
    els.probMin,
    els.probMax,
    els.searchBox,
  ].forEach((el) => el.addEventListener("input", render));
  [els.platformFilter, els.categoryFilter].forEach((el) => el.addEventListener("change", render));
  els.sourceMode.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-source-mode]");
    if (!button) return;
    state.sourceMode = button.dataset.sourceMode;
    [...els.sourceMode.querySelectorAll("button")].forEach((item) => item.classList.toggle("is-active", item === button));
    render();
  });
  els.metricMode.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-metric-mode]");
    if (!button) return;
    state.metricMode = button.dataset.metricMode;
    [...els.metricMode.querySelectorAll("button")].forEach((item) => item.classList.toggle("is-active", item === button));
    render();
  });
  els.resetFilters.addEventListener("click", () => {
    setDefaults();
    state.sourceMode = "all";
    state.metricMode = "brier";
    [...els.sourceMode.querySelectorAll("button")].forEach((item) => item.classList.toggle("is-active", item.dataset.sourceMode === "all"));
    [...els.metricMode.querySelectorAll("button")].forEach((item) => item.classList.toggle("is-active", item.dataset.metricMode === "brier"));
    render();
  });
  window.addEventListener("resize", render);
}

async function init() {
  const response = await fetch(DATA_URL);
  const text = await response.text();
  els.dataFreshness.textContent = formatTimestamp(response.headers.get("Last-Modified"));
  state.rows = prepareRows(parseCsv(text));
  setDefaults();
  addListeners();
  render();
}

init().catch((error) => {
  document.body.innerHTML = `<main class="empty">Could not load dashboard data: ${error.message}</main>`;
});
