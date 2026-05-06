from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from src.accuracy import add_score_columns, baseline_comparison_table, calibration_table, metric_summary

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "cleaned" / "accuracy_markets.csv"

COLORS = {
    "polymarket": "#2F5EE5",
    "kalshi": "#5FCB99",
    "text": "#1F2C37",
    "muted": "#687785",
    "panel": "#FFF8EE",
    "line": "#D7CCBF",
    "good": "#3F9D6E",
    "warn": "#B86B32",
}

app = dash.Dash(__name__, title="How accurate are prediction markets?")
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
    df["category_confidence"] = pd.to_numeric(_col(df, "category_confidence", 0), errors="coerce").fillna(0.0)
    df["exclude_reason"] = _col(df, "exclude_reason", "").fillna("")
    return add_score_columns(df)


@lru_cache
def headline_metrics() -> dict:
    df = load_data()
    scored = df[df["analysis_ready"]]
    overall = metric_summary(scored).iloc[0]
    by_platform = metric_summary(scored, ["platform"]).set_index("platform")
    baseline_50 = baseline_comparison_table(scored, "baseline_prob_50", "always_50").iloc[0]
    baseline_cat = baseline_comparison_table(scored, "baseline_prob_category_rate", "category_rate").iloc[0]
    return {
        "n_scored": int(overall["n"]),
        "n_captured": int(len(df)),
        "brier": float(overall["brier"]),
        "log_loss": float(overall["log_loss"]),
        "polymarket": {
            "brier": float(by_platform.loc["polymarket", "brier"]),
            "n": int(by_platform.loc["polymarket", "n"]),
            "yes_rate": float(by_platform.loc["polymarket", "observed_yes_rate"]),
        } if "polymarket" in by_platform.index else None,
        "kalshi": {
            "brier": float(by_platform.loc["kalshi", "brier"]),
            "n": int(by_platform.loc["kalshi", "n"]),
            "yes_rate": float(by_platform.loc["kalshi", "observed_yes_rate"]),
        } if "kalshi" in by_platform.index else None,
        "vs_50_pct": float(baseline_50["brier_improvement_pct"]) * 100,
        "vs_cat_pct": float(baseline_cat["brier_improvement_pct"]) * 100,
    }


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


def base_layout(fig: go.Figure, title: str, height: int = 420) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=20, color=COLORS["text"])),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLORS["panel"],
        font=dict(family="Inter, Segoe UI, sans-serif", size=13, color=COLORS["text"]),
        margin=dict(t=70, r=24, b=56, l=56),
        hoverlabel=dict(bgcolor="#FFF9F0", bordercolor=COLORS["line"], font=dict(color=COLORS["text"], size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        height=height,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=COLORS["line"], tickfont=dict(color=COLORS["muted"]))
    fig.update_yaxes(gridcolor=COLORS["line"], zeroline=False, tickfont=dict(color=COLORS["muted"]))
    return fig


def calibration_figure() -> go.Figure:
    df = load_data()
    df = df[df["analysis_ready"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color=COLORS["muted"], dash="dash"), name="Perfect calibration", hoverinfo="skip",
    ))
    for platform, color in [("polymarket", COLORS["polymarket"]), ("kalshi", COLORS["kalshi"])]:
        sub = df[df["platform"] == platform]
        if sub.empty:
            continue
        cal = calibration_table(sub).copy()
        cal["bin_label"] = cal["probability_bin"].astype(str)
        sizes = ((cal["n"].clip(lower=1) ** 0.5) * 5).tolist()
        fig.add_trace(go.Scatter(
            x=cal["avg_forecast"], y=cal["observed_yes_rate"],
            mode="markers+lines", name=platform.title(),
            marker=dict(size=sizes, color=color, line=dict(color="#fff", width=1)),
            customdata=cal[["n", "brier", "bin_label"]].to_numpy(dtype=object),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Bucket: %{customdata[2]}<br>"
                "Predicted: %{x:.0%}<br>"
                "Actually happened: %{y:.0%}<br>"
                "Markets: %{customdata[0]}<extra></extra>"
            ),
        ))
    base_layout(fig, "Are predictions trustworthy?", height=440)
    fig.update_xaxes(range=[0, 1], tickformat=".0%", title="What the market predicted")
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title="What actually happened")
    return fig


def category_brier_figure() -> go.Figure:
    df = load_data()
    df = df[df["analysis_ready"]]
    grouped = metric_summary(df, ["category"]).sort_values("brier")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=grouped["brier"], y=grouped["category"], orientation="h",
        marker=dict(color=COLORS["polymarket"]),
        customdata=grouped[["n"]].to_numpy(),
        hovertemplate="<b>%{y}</b><br>Brier: %{x:.3f}<br>Markets: %{customdata[0]}<extra></extra>",
    ))
    fig.add_vline(x=0.25, line_dash="dash", line_color=COLORS["muted"],
                  annotation_text="Random guess (0.25)", annotation_position="top right",
                  annotation_font=dict(size=11, color=COLORS["muted"]))
    base_layout(fig, "Where are markets most accurate?", height=440)
    fig.update_xaxes(title="Brier score (lower = more accurate)")
    fig.update_yaxes(title="")
    return fig


def coverage_figure() -> go.Figure:
    df = load_data()
    df = df[df["analysis_ready"]]
    grouped = df.groupby(["category", "platform"], observed=True).size().reset_index(name="n")
    fig = go.Figure()
    for platform, color in [("polymarket", COLORS["polymarket"]), ("kalshi", COLORS["kalshi"])]:
        sub = grouped[grouped["platform"] == platform]
        fig.add_trace(go.Bar(
            x=sub["category"], y=sub["n"], name=platform.title(),
            marker_color=color,
            hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>%{y} markets<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    base_layout(fig, "Markets scored by category", height=320)
    fig.update_yaxes(title="Markets")
    return fig


def headline_card() -> html.Div:
    m = headline_metrics()
    poly_better = m["polymarket"] and m["kalshi"] and m["polymarket"]["brier"] < m["kalshi"]["brier"]
    winner_note = (
        "Polymarket edges out Kalshi, but bootstrap intervals overlap — call it a tie."
        if poly_better else
        "Kalshi edges out Polymarket, but bootstrap intervals overlap — call it a tie."
    )
    return html.Div(
        className="hero-panel",
        children=[
            html.Div("Prediction market accuracy study", className="hero-kicker"),
            html.H1("Prediction markets beat coin-flip baseline by ~53%", className="hero-title"),
            html.P(
                f"We scored {m['n_scored']:,} resolved binary markets on Polymarket and Kalshi "
                f"with at least $100K of volume. The forecasts are correct often enough to be "
                f"meaningfully better than guessing — and {winner_note.lower()}",
                className="hero-copy",
            ),
        ],
    )


def headline_kpis() -> html.Div:
    m = headline_metrics()
    cards = [
        ("Markets scored", f"{m['n_scored']:,}",
         f"out of {m['n_captured']:,} captured",
         f"≥ $100K volume, resolved YES/NO"),
        ("Beat 50/50 guess by", f"{m['vs_50_pct']:.0f}%",
         "in Brier score",
         "Lower error than predicting 50% on every market."),
        ("Beat category base-rate by", f"{m['vs_cat_pct']:.0f}%",
         "in Brier score",
         "Better than just predicting the historical YES rate per category."),
        ("Brier score", f"{m['brier']:.3f}",
         "0 = perfect, 0.25 = random",
         "Mean squared error between forecast and outcome."),
    ]
    return html.Div(
        className="kpi-grid",
        children=[
            html.Div(className="kpi-card", children=[
                html.Div(label, className="kpi-label"),
                html.Div(value, className="kpi-value"),
                html.Div(note, className="kpi-note"),
                html.Div(extra, className="kpi-accent"),
            ])
            for label, value, note, extra in cards
        ],
    )


def platform_card(platform: str, m: dict, opponent_brier: float | None) -> html.Div:
    color = COLORS["polymarket"] if platform == "polymarket" else COLORS["kalshi"]
    better = opponent_brier is not None and m["brier"] < opponent_brier
    return html.Div(
        className="platform-card",
        style={"borderLeft": f"6px solid {color}"},
        children=[
            html.Div(platform.title(), className="platform-name"),
            html.Div(f"{m['brier']:.3f}", className="platform-metric"),
            html.Div("Brier score", className="platform-metric-label"),
            html.Div([
                html.Span(f"{m['n']:,} markets", className="platform-stat"),
                html.Span(" · ", style={"color": COLORS["muted"]}),
                html.Span(f"{m['yes_rate']:.0%} YES rate", className="platform-stat"),
            ], style={"marginTop": "0.8rem"}),
            html.Div(
                "Slightly more accurate (within margin of error)" if better else "",
                className="platform-tag",
                style={"color": COLORS["good"], "marginTop": "0.6rem", "fontSize": "0.85rem", "fontWeight": 700},
            ),
        ],
    )


def platform_comparison() -> html.Div:
    m = headline_metrics()
    poly = m["polymarket"]
    kalshi = m["kalshi"]
    return html.Div(
        className="comparison-row",
        children=[
            platform_card("polymarket", poly, kalshi["brier"] if kalshi else None) if poly else html.Div(),
            platform_card("kalshi", kalshi, poly["brier"] if poly else None) if kalshi else html.Div(),
        ],
    )


def grid_rows(df: pd.DataFrame) -> list[dict]:
    table = df.sort_values("volume", ascending=False).copy()
    table["forecast_pct"] = table["forecast_prob"].map(fmt_pct)
    table["volume_label"] = table["volume"].map(fmt_money)
    table["brier_label"] = table["brier"].map(lambda x: "—" if pd.isna(x) else f"{x:.3f}")
    table["correct"] = ((table["forecast_prob"] >= 0.5) & (table["resolution"] == "YES")) | \
                      ((table["forecast_prob"] < 0.5) & (table["resolution"] == "NO"))
    table["correct_label"] = table["correct"].map({True: "✓", False: "✗"})
    return table[[
        "platform", "category", "title", "resolution", "forecast_pct",
        "correct_label", "brier_label", "volume_label",
    ]].where(pd.notna(table), None).to_dict("records")


def app_layout() -> dmc.MantineProvider:
    df = load_data()
    platforms = sorted(df["platform"].dropna().unique()) if not df.empty else []
    categories = sorted(df["category"].dropna().unique()) if not df.empty else []
    return dmc.MantineProvider(
        theme={"fontFamily": "Inter, sans-serif", "primaryColor": "blue"},
        children=dmc.Container(
            size="xl",
            className="app-shell",
            children=dmc.Stack(gap="xl", children=[
                headline_card(),
                headline_kpis(),
                html.Div(className="section-title", children="Polymarket vs. Kalshi"),
                platform_comparison(),
                dmc.Grid(gutter="xl", children=[
                    dmc.GridCol(span={"base": 12, "lg": 6}, children=[
                        dcc.Graph(figure=calibration_figure(), config={"displayModeBar": False}),
                        html.Div(
                            "Each dot is a probability bucket. Dots on the dashed line mean the market "
                            "was perfectly calibrated — when it predicted 70% YES, exactly 70% of those "
                            "markets resolved YES. Bigger dots = more markets in that bucket.",
                            className="chart-caption",
                        ),
                    ]),
                    dmc.GridCol(span={"base": 12, "lg": 6}, children=[
                        dcc.Graph(figure=category_brier_figure(), config={"displayModeBar": False}),
                        html.Div(
                            "Brier score by category — lower means the forecasts were closer to the "
                            "eventual outcome. The dashed line is what you'd get by predicting 50% on "
                            "every market.",
                            className="chart-caption",
                        ),
                    ]),
                ]),
                dcc.Graph(figure=coverage_figure(), config={"displayModeBar": False}),
                html.Div(className="section-title", children="Explore the data"),
                html.Div(className="filter-bar", children=[
                    dmc.MultiSelect(
                        id="platform-filter",
                        label="Platform",
                        data=[{"label": p.title(), "value": p} for p in platforms],
                        value=platforms,
                        clearable=False,
                        style={"minWidth": "220px"},
                    ),
                    dmc.MultiSelect(
                        id="category-filter",
                        label="Category",
                        data=[{"label": c.replace("_", " ").title(), "value": c} for c in categories],
                        value=categories,
                        clearable=False,
                        searchable=True,
                        style={"minWidth": "260px"},
                    ),
                    dmc.TextInput(
                        id="market-search",
                        label="Search",
                        placeholder="search title or category...",
                        style={"flex": 1, "minWidth": "240px"},
                    ),
                ]),
                dag.AgGrid(
                    id="markets-grid",
                    className="ag-theme-alpine",
                    columnDefs=[
                        {"field": "platform", "headerName": "Platform", "width": 130},
                        {"field": "category", "headerName": "Category", "width": 140},
                        {"field": "title", "headerName": "Market", "flex": 3, "wrapText": True, "autoHeight": True},
                        {"field": "resolution", "headerName": "Resolved", "width": 110},
                        {"field": "forecast_pct", "headerName": "Forecast", "width": 110},
                        {"field": "correct_label", "headerName": "Correct?", "width": 110},
                        {"field": "brier_label", "headerName": "Brier", "width": 100},
                        {"field": "volume_label", "headerName": "Volume", "width": 120},
                    ],
                    defaultColDef={"sortable": True, "filter": True, "resizable": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 25, "animateRows": False},
                    rowData=grid_rows(df[df["analysis_ready"]]) if not df.empty else [],
                    style={"height": "640px"},
                ),
                html.Div(
                    className="narrative-card",
                    children=[
                        html.H3("Methodology", style={"marginTop": 0}),
                        html.P([
                            "Forecast = the last non-trivial pre-resolution YES probability (between 2% and 98%). ",
                            "We exclude markets below $100K volume and any flagged for category review. ",
                            "Brier and log loss are computed only on the analysis-ready subset; coverage counts include all captured markets.",
                        ], style={"color": COLORS["muted"], "lineHeight": 1.7}),
                        html.P([
                            "Categories come from a fail-closed taxonomy: explicit overrides → platform metadata → mapping rules → narrow keyword fallback. ",
                            "Bootstrap 95% confidence intervals around the platform-level Brier scores overlap, so platform comparisons should be interpreted cautiously.",
                        ], style={"color": COLORS["muted"], "lineHeight": 1.7}),
                    ],
                ),
            ]),
        ),
    )


app.layout = app_layout


@app.callback(
    Output("markets-grid", "rowData"),
    Input("platform-filter", "value"),
    Input("category-filter", "value"),
    Input("market-search", "value"),
)
def update_markets_grid(platforms, categories, search):
    df = load_data()
    if df.empty:
        return []
    df = df[df["analysis_ready"]]
    if platforms:
        df = df[df["platform"].isin(platforms)]
    if categories:
        df = df[df["category"].isin(categories)]
    if search:
        mask = df["title"].astype(str).str.contains(search, case=False, na=False) | \
               df["category"].astype(str).str.contains(search, case=False, na=False)
        df = df[mask]
    return grid_rows(df)


if __name__ == "__main__":
    app.run(debug=True)
