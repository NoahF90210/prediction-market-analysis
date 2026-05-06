from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from src.accuracy import add_score_columns, calibration_table, metric_summary

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "cleaned" / "accuracy_markets.csv"

COLORS = {
    "bg": "#F4EFE6",
    "bg_alt": "#FFF9F0",
    "panel": "#FFF8EE",
    "panel_alt": "#F8F1E7",
    "line": "#D7CCBF",
    "text": "#1F2C37",
    "muted": "#687785",
    "polymarket": "#2F5EE5",
    "kalshi": "#5FCB99",
    "accent": "#A85532",
    "warning": "#B86B32",
}
COMPARABLE_MIN_MARKETS = 20

app = dash.Dash(__name__, title="Prediction Market Accuracy")
server = app.server


def _col(df: pd.DataFrame, name: str, default):
    if name in df.columns:
        return df[name]
    if isinstance(default, pd.Series):
        return default
    return pd.Series([default] * len(df), index=df.index)


@lru_cache
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(DATA_PATH)
    df["raw_tags"] = _col(df, "raw_tags", "[]").fillna("[]")
    df["needs_review"] = _col(df, "needs_review", False).fillna(False).astype(bool)
    df["include_in_analysis"] = _col(df, "include_in_analysis", True).fillna(True).astype(bool)
    df["meets_volume_threshold"] = _col(df, "meets_volume_threshold", df["volume"] >= 100_000).fillna(False).astype(bool)
    df["analysis_ready"] = _col(df, "analysis_ready", df["include_in_analysis"]).fillna(False).astype(bool)
    df["is_cross_platform_comparable"] = _col(df, "is_cross_platform_comparable", False).fillna(False).astype(bool)
    df["category_confidence"] = pd.to_numeric(_col(df, "category_confidence", 0), errors="coerce").fillna(0.0)
    df["exclude_reason"] = _col(df, "exclude_reason", "").fillna("")
    return add_score_columns(df)


def fmt_money(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def fmt_pct(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:.1%}"


def empty_dashboard_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "platform",
            "market_id",
            "title",
            "category",
            "resolution",
            "forecast_prob",
            "forecast_source",
            "volume",
            "include_in_analysis",
            "analysis_ready",
            "meets_volume_threshold",
            "needs_review",
            "is_cross_platform_comparable",
            "category_confidence",
            "brier",
            "log_loss",
            "outcome",
            "review_reason",
            "raw_platform_category",
            "exclude_reason",
        ]
    )


def comparable_categories(df: pd.DataFrame) -> list[str]:
    eligible = (
        df[df["include_in_analysis"]]
        .groupby(["category", "platform"], observed=True)
        .size()
        .unstack(fill_value=0)
    )
    return sorted(
        category
        for category, row in eligible.iterrows()
        if len([count for count in row if count >= COMPARABLE_MIN_MARKETS]) >= 2
    )


def filter_dataframe(
    df: pd.DataFrame,
    platforms: list[str],
    categories: list[str],
    volume_range: list[float],
    prob_range: list[float],
    analysis_scope: str,
    category_view: str,
    quality_mode: str,
) -> pd.DataFrame:
    filtered = df.copy()
    if platforms:
        filtered = filtered[filtered["platform"].isin(platforms)]
    if categories:
        filtered = filtered[filtered["category"].isin(categories)]
    volume_mask = filtered["volume"].between(volume_range[0], volume_range[1])
    probability_mask = filtered["forecast_prob"].between(prob_range[0], prob_range[1])
    if analysis_scope == "all":
        probability_mask = probability_mask | filtered["forecast_prob"].isna()
    filtered = filtered[volume_mask & probability_mask]
    if analysis_scope == "analysis_ready":
        filtered = filtered[filtered["analysis_ready"]]
    if category_view == "comparable":
        filtered = filtered[filtered["is_cross_platform_comparable"]]
    if quality_mode == "reviewed":
        filtered = filtered[~filtered["needs_review"]]
    return filtered.copy()


def base_layout(fig: go.Figure, title: str, height: int = 420) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=24, color=COLORS["text"])),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLORS["panel"],
        font=dict(family="Inter, Segoe UI, sans-serif", size=14, color=COLORS["text"]),
        margin=dict(t=72, r=26, b=56, l=56),
        hoverlabel=dict(
            bgcolor=COLORS["bg_alt"],
            bordercolor=COLORS["line"],
            font=dict(color=COLORS["text"], size=13),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        height=height,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=COLORS["line"], tickfont=dict(color=COLORS["muted"]))
    fig.update_yaxes(gridcolor=COLORS["line"], zeroline=False, tickfont=dict(color=COLORS["muted"]))
    return fig


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color=COLORS["muted"]),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return base_layout(fig, "", height=340)


def overview_cards(df: pd.DataFrame) -> list[html.Div]:
    analysis_df = df[df["analysis_ready"]] if not df.empty else df
    if analysis_df.empty:
        summary = pd.Series({"n": 0, "brier": 0.0, "observed_yes_rate": 0.0})
    else:
        summary = metric_summary(analysis_df).iloc[0]
    captured = int(len(df))
    analysis_ready = int(df["analysis_ready"].sum()) if not df.empty else 0
    flagged = int(df["needs_review"].sum())
    below_threshold = int((~df["meets_volume_threshold"]).sum()) if not df.empty else 0
    cards = [
        ("Captured Markets", f"{captured:,}", "All resolved markets in the current filtered view.", f"{analysis_ready:,} analysis-ready"),
        ("Brier Score", f"{summary['brier']:.3f}", "Computed only on the volume >= $100K analysis-ready subset.", f"Observed YES {summary['observed_yes_rate']:.1%}"),
        ("Categories", f"{df['category'].nunique():,}", "Canonical categories currently visible.", f"{int(df['is_cross_platform_comparable'].sum()):,} comparable rows"),
        ("Needs Review", f"{flagged:,}", "Rows flagged for category review or excluded from scoring.", f"{below_threshold:,} below $100K threshold"),
    ]
    return [
        html.Div(
            className="kpi-card",
            children=[
                html.Div(label, className="kpi-label"),
                html.Div(value, className="kpi-value"),
                html.Div(note, className="kpi-note"),
                html.Div(accent, className="kpi-accent"),
            ],
        )
        for label, value, note, accent in cards
    ]


def coverage_badges(df: pd.DataFrame) -> list[dmc.Badge]:
    comparable = comparable_categories(load_data())
    badges = [
        dmc.Badge(f"{df['platform'].nunique()} platforms", color="gray", variant="light", radius="xl"),
        dmc.Badge(f"{df['category'].nunique()} categories in view", color="gray", variant="light", radius="xl"),
        dmc.Badge(f"{len(comparable)} comparable categories", color="green", variant="light", radius="xl"),
        dmc.Badge(f"{int((~df['meets_volume_threshold']).sum())} below $100K", color="orange", variant="light", radius="xl"),
        dmc.Badge("Headline metrics use scored rows only", color="blue", variant="light", radius="xl"),
    ]
    return badges


def platform_category_figure(df: pd.DataFrame) -> go.Figure:
    grouped = metric_summary(df, ["platform", "category"])
    if grouped.empty:
        return empty_figure("No markets match the current filter set.")
    fig = px.bar(
        grouped,
        x="category",
        y="brier",
        color="platform",
        barmode="group",
        color_discrete_map={"polymarket": COLORS["polymarket"], "kalshi": COLORS["kalshi"]},
        custom_data=["n", "log_loss", "observed_yes_rate"],
        labels={"category": "", "brier": "Brier score"},
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{fullData.name}</b><br>"
            "Category: %{x}<br>"
            "Brier: %{y:.3f}<br>"
            "Markets: %{customdata[0]}<br>"
            "Log loss: %{customdata[1]:.3f}<br>"
            "Observed YES: %{customdata[2]:.1%}<extra></extra>"
        )
    )
    return base_layout(fig, "Forecast Error by Platform and Category")


def coverage_figure(df: pd.DataFrame) -> go.Figure:
    grouped = (
        df.groupby(["category", "platform"], observed=True)["market_id"]
        .count()
        .reset_index(name="markets")
    )
    if grouped.empty:
        return empty_figure("No category coverage to display.")
    fig = px.bar(
        grouped,
        x="category",
        y="markets",
        color="platform",
        barmode="stack",
        color_discrete_map={"polymarket": COLORS["polymarket"], "kalshi": COLORS["kalshi"]},
        labels={"category": "", "markets": "Markets"},
    )
    fig.update_traces(
        hovertemplate="<b>%{fullData.name}</b><br>Category: %{x}<br>Markets: %{y}<extra></extra>"
    )
    return base_layout(fig, "Coverage by Category", height=360)


def calibration_figure(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("No calibration data available.")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color=COLORS["muted"], dash="dash"),
            name="Perfect calibration",
            hoverinfo="skip",
        )
    )
    for platform, color in [("polymarket", COLORS["polymarket"]), ("kalshi", COLORS["kalshi"])]:
        platform_df = df[df["platform"] == platform]
        if platform_df.empty:
            continue
        cal = calibration_table(platform_df)
        cal = cal.copy()
        cal["probability_bin_label"] = cal["probability_bin"].astype(str)
        marker_sizes = ((cal["n"].clip(lower=1) ** 0.5) * 6).tolist()
        fig.add_trace(
            go.Scatter(
                x=cal["avg_forecast"],
                y=cal["observed_yes_rate"],
                mode="markers+lines",
                name=platform,
                marker=dict(size=marker_sizes, color=color, line=dict(color="#fff", width=1)),
                customdata=cal[["n", "brier", "probability_bin_label"]].to_numpy(dtype=object),
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Bucket: %{customdata[2]}<br>"
                    "Avg forecast: %{x:.1%}<br>"
                    "Observed YES: %{y:.1%}<br>"
                    "Markets: %{customdata[0]}<br>"
                    "Brier: %{customdata[1]:.3f}<extra></extra>"
                ),
            )
        )
    base_layout(fig, "Calibration by Platform", height=420)
    fig.update_xaxes(range=[0, 1], tickformat=".0%", title="Average forecast probability")
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title="Observed YES rate")
    return fig


def source_quality_figure(df: pd.DataFrame) -> go.Figure:
    grouped = (
        df.groupby(["forecast_source", "platform"], observed=True)["market_id"]
        .count()
        .reset_index(name="markets")
    )
    if grouped.empty:
        return empty_figure("No forecast-source data available.")
    grouped["forecast_source"] = grouped["forecast_source"].fillna("unknown")
    fig = px.bar(
        grouped,
        x="forecast_source",
        y="markets",
        color="platform",
        barmode="group",
        color_discrete_map={"polymarket": COLORS["polymarket"], "kalshi": COLORS["kalshi"]},
        labels={"forecast_source": "", "markets": "Markets"},
    )
    fig.update_traces(hovertemplate="<b>%{fullData.name}</b><br>Source: %{x}<br>Markets: %{y}<extra></extra>")
    return base_layout(fig, "Forecast Source Quality", height=360)


def grid_rows(df: pd.DataFrame) -> list[dict]:
    table = df.sort_values(["needs_review", "volume"], ascending=[True, False]).copy()
    table["forecast_pct"] = table["forecast_prob"].map(fmt_pct)
    table["category_confidence_pct"] = table["category_confidence"].map(lambda x: f"{x:.0%}" if pd.notna(x) else "n/a")
    table["volume_label"] = table["volume"].map(fmt_money)
    table["brier_label"] = table["brier"].map(lambda x: f"{x:.3f}")
    records = table[
        [
            "platform",
            "category",
            "title",
            "resolution",
            "forecast_pct",
            "brier_label",
            "volume_label",
            "category_source",
            "category_confidence_pct",
            "needs_review",
            "raw_platform_category",
            "review_reason",
            "exclude_reason",
        ]
    ].where(pd.notna(table), None).to_dict("records")
    return records


def app_layout() -> dmc.MantineProvider:
    df = load_data()
    platforms = sorted(df["platform"].dropna().unique())
    categories = sorted(df["category"].dropna().unique())
    comparable = comparable_categories(df)
    min_volume = float(df["volume"].min()) if not df.empty else 0.0
    max_volume = float(df["volume"].max()) if not df.empty else 1.0

    return dmc.MantineProvider(
        theme={"fontFamily": "Inter, sans-serif", "primaryColor": "green"},
        children=dmc.Container(
            size="xl",
            className="app-shell",
            children=[
                dmc.Stack(
                    gap="xl",
                    children=[
                        html.Section(
                            className="hero-panel",
                            children=[
                                html.Div("Prediction market dashboard", className="hero-kicker"),
                                html.H1("Prediction Market Accuracy", className="hero-title"),
                                html.P(
                                    "A category-audited view of liquid resolved Polymarket and Kalshi markets. "
                                    "Category assignments preserve source metadata, flag uncertain rows, and default "
                                    "the analysis to reviewed comparable slices.",
                                    className="hero-copy",
                                ),
                            ],
                        ),
                        dmc.Grid(
                            gutter="xl",
                            children=[
                                dmc.GridCol(
                                    span={"base": 12, "md": 3},
                                    children=dmc.Stack(
                                        gap="md",
                                        children=[
                                            dmc.Paper(
                                                shadow="xs",
                                                radius="xl",
                                                p="lg",
                                                className="filter-panel",
                                                children=[
                                                    dmc.Title("Filters", order=3, mb="xs"),
                                                    dmc.Text(
                                                        "Default settings emphasize comparable, review-approved categories.",
                                                        c="dimmed",
                                                        size="sm",
                                                        mb="md",
                                                    ),
                                                    dmc.MultiSelect(
                                                        id="platform-filter",
                                                        label="Platform",
                                                        data=[{"label": p.title(), "value": p} for p in platforms],
                                                        value=platforms,
                                                        searchable=True,
                                                        clearable=False,
                                                    ),
                                                    dmc.MultiSelect(
                                                        id="category-filter",
                                                        label="Category",
                                                        data=[{"label": c.replace('_', ' ').title(), "value": c} for c in categories],
                                                        value=comparable or categories,
                                                        searchable=True,
                                                        clearable=False,
                                                        mt="md",
                                                    ),
                                                    dmc.RangeSlider(
                                                        id="volume-filter",
                                                        label="Volume",
                                                        min=min_volume,
                                                        max=max_volume,
                                                        value=[min_volume, max_volume],
                                                        minRange=0,
                                                        mt="xl",
                                                    ),
                                                    dmc.RangeSlider(
                                                        id="probability-filter",
                                                        label="Forecast probability",
                                                        min=0.0,
                                                        max=1.0,
                                                        value=[0.0, 1.0],
                                                        step=0.01,
                                                        mt="xl",
                                                    ),
                                                    dmc.SegmentedControl(
                                                        id="analysis-scope",
                                                        data=[
                                                            {"label": "All captured markets", "value": "all"},
                                                            {"label": "Analysis-ready markets", "value": "analysis_ready"},
                                                        ],
                                                        value="analysis_ready",
                                                        fullWidth=True,
                                                        mt="xl",
                                                    ),
                                                    dmc.SegmentedControl(
                                                        id="category-view",
                                                        data=[
                                                            {"label": "Comparable", "value": "comparable"},
                                                            {"label": "All categories", "value": "all"},
                                                        ],
                                                        value="all",
                                                        fullWidth=True,
                                                        mt="md",
                                                    ),
                                                    dmc.SegmentedControl(
                                                        id="quality-mode",
                                                        data=[
                                                            {"label": "Reviewed only", "value": "reviewed"},
                                                            {"label": "Include low-confidence", "value": "all"},
                                                        ],
                                                        value="reviewed",
                                                        fullWidth=True,
                                                        mt="md",
                                                    ),
                                                    dmc.TextInput(
                                                        id="market-search",
                                                        label="Search markets",
                                                        placeholder="Search title, category, or reason...",
                                                        mt="md",
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                ),
                                dmc.GridCol(
                                    span={"base": 12, "md": 9},
                                    children=dmc.Stack(
                                        gap="lg",
                                        children=[
                                            html.Div(id="coverage-badges", className="badge-row"),
                                            html.Div(id="overview-cards", className="kpi-grid"),
                                            dmc.Tabs(
                                                value="overview",
                                                children=[
                                                    dmc.TabsList(
                                                        [
                                                            dmc.TabsTab("Overview", value="overview"),
                                                            dmc.TabsTab("Calibration", value="calibration"),
                                                            dmc.TabsTab("Markets", value="markets"),
                                                            dmc.TabsTab("Method", value="method"),
                                                        ]
                                                    ),
                                                    dmc.TabsPanel(
                                                        value="overview",
                                                        pt="lg",
                                                        children=[
                                                            dmc.Grid(
                                                                gutter="xl",
                                                                children=[
                                                                    dmc.GridCol(span={"base": 12, "lg": 8}, children=dcc.Graph(id="platform-category-chart")),
                                                                    dmc.GridCol(span={"base": 12, "lg": 4}, children=dcc.Graph(id="coverage-chart")),
                                                                    dmc.GridCol(span={"base": 12, "lg": 6}, children=dcc.Graph(id="source-quality-chart")),
                                                                    dmc.GridCol(
                                                                        span={"base": 12, "lg": 6},
                                                                        children=dmc.Paper(
                                                                            className="narrative-card",
                                                                            p="xl",
                                                                            radius="xl",
                                                                            children=[
                                                                                dmc.Title("Coverage and Confidence", order=3),
                                                                                dmc.Text(
                                                                    "Raw coverage stays visible by default, while Brier and calibration use only the scored subset with volume >= $100K and accepted category quality. "
                                                                                    "Use the scope and quality toggles to inspect what was captured versus what is currently safe to analyze.",
                                                                                    mt="md",
                                                                                    c="dimmed",
                                                                                ),
                                                                                html.Ul(
                                                                                    className="method-list",
                                                                                    children=[
                                                                                        html.Li("Source tags and category metadata outrank keyword guesses."),
                                                                                        html.Li("Comparable is a secondary lens, not the default visibility rule."),
                                                                                        html.Li("Rows with conflicting or weak signals remain visible, but are flagged for review or exclusion."),
                                                                                    ],
                                                                                ),
                                                                            ],
                                                                        ),
                                                                    ),
                                                                ],
                                                            )
                                                        ],
                                                    ),
                                                    dmc.TabsPanel(value="calibration", pt="lg", children=dcc.Graph(id="calibration-chart")),
                                                    dmc.TabsPanel(
                                                        value="markets",
                                                        pt="lg",
                                                        children=dag.AgGrid(
                                                            id="markets-grid",
                                                            className="ag-theme-alpine",
                                                            columnDefs=[
                                                                {"field": "platform", "headerName": "Platform"},
                                                                {"field": "category", "headerName": "Category"},
                                                                {"field": "title", "headerName": "Market", "flex": 2.8, "wrapText": True, "autoHeight": True},
                                                                {"field": "resolution", "headerName": "Result"},
                                                                {"field": "forecast_pct", "headerName": "Forecast"},
                                                                {"field": "brier_label", "headerName": "Brier"},
                                                                {"field": "volume_label", "headerName": "Volume"},
                                                                {"field": "category_source", "headerName": "Category source"},
                                                                {"field": "category_confidence_pct", "headerName": "Confidence"},
                                                                {"field": "needs_review", "headerName": "Needs review"},
                                                                {"field": "raw_platform_category", "headerName": "Raw category"},
                                                                {"field": "review_reason", "headerName": "Review reason", "flex": 2},
                                                                {"field": "exclude_reason", "headerName": "Exclude reason", "flex": 1.4},
                                                            ],
                                                            defaultColDef={"sortable": True, "filter": True, "resizable": True},
                                                            dashGridOptions={
                                                                "pagination": True,
                                                                "paginationPageSize": 25,
                                                                "animateRows": False,
                                                            },
                                                            style={"height": "780px"},
                                                        ),
                                                    ),
                                                    dmc.TabsPanel(
                                                        value="method",
                                                        pt="lg",
                                                        children=dmc.Paper(
                                                            className="narrative-card",
                                                            p="xl",
                                                            radius="xl",
                                                            children=[
                                                                dmc.Title("Methodology", order=3),
                                                                dmc.Text(
                                                                    "Forecasts use the last non-trivial pre-resolution YES probability. "
                                                                    "Category mapping follows a fail-closed hierarchy: explicit override, source metadata, deterministic mapping rules, then narrow keyword fallback. "
                                                                    "Rows that remain ambiguous are marked for review rather than forced into analysis. "
                                                                    "Markets below $100K volume remain in coverage counts but are excluded from scoring by default.",
                                                                    mt="md",
                                                                    c="dimmed",
                                                                ),
                                                            ],
                                                        ),
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ],
                )
            ],
        ),
    )


app.layout = app_layout


@app.callback(
    Output("overview-cards", "children"),
    Output("coverage-badges", "children"),
    Output("platform-category-chart", "figure"),
    Output("coverage-chart", "figure"),
    Output("source-quality-chart", "figure"),
    Output("calibration-chart", "figure"),
    Output("markets-grid", "rowData"),
    Input("platform-filter", "value"),
    Input("category-filter", "value"),
    Input("volume-filter", "value"),
    Input("probability-filter", "value"),
    Input("analysis-scope", "value"),
    Input("category-view", "value"),
    Input("quality-mode", "value"),
    Input("market-search", "value"),
)
def update_dashboard(
    platforms,
    categories,
    volume_range,
    probability_range,
    analysis_scope,
    category_view,
    quality_mode,
    market_search,
):
    df = load_data()
    filtered = filter_dataframe(
        df,
        platforms or [],
        categories or [],
        volume_range or [float(df["volume"].min()), float(df["volume"].max())],
        probability_range or [0.0, 1.0],
        analysis_scope or "analysis_ready",
        category_view or "comparable",
        quality_mode or "reviewed",
    )
    if market_search:
        mask = filtered["title"].astype(str).str.contains(market_search, case=False, na=False)
        mask |= filtered["category"].astype(str).str.contains(market_search, case=False, na=False)
        mask |= filtered["review_reason"].astype(str).str.contains(market_search, case=False, na=False)
        filtered = filtered[mask]
    if filtered.empty:
        empty_df = empty_dashboard_frame()
        return (
            overview_cards(empty_df),
            coverage_badges(empty_df),
            empty_figure("No markets match the current filters."),
            empty_figure("No markets match the current filters."),
            empty_figure("No markets match the current filters."),
            empty_figure("No markets match the current filters."),
            [],
        )
    return (
        overview_cards(filtered),
        coverage_badges(filtered),
        platform_category_figure(filtered),
        coverage_figure(filtered),
        source_quality_figure(filtered),
        calibration_figure(filtered),
        grid_rows(filtered),
    )


if __name__ == "__main__":
    app.run(debug=True)
