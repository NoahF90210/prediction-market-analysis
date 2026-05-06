from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.accuracy import add_score_columns, calibration_table, metric_summary

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "cleaned" / "accuracy_markets.csv"

PALETTE = {
    "bg": "#F4EFE6",
    "panel": "#FFF9F0",
    "panel_alt": "#FAF3E8",
    "border": "#D8CDC0",
    "text": "#1E2B36",
    "muted": "#62707C",
    "grid": "#E9DED0",
    "polymarket": "#1F5A91",
    "kalshi": "#B35C38",
    "accent": "#8B3D2E",
}
PLATFORM_COLORS = {
    "polymarket": PALETTE["polymarket"],
    "kalshi": PALETTE["kalshi"],
}

st.set_page_config(
    page_title="Prediction Market Accuracy",
    layout="wide",
)


@st.cache_data
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(DATA_PATH)
    df["market_id"] = df["market_id"].astype(str)
    df["open_time"] = pd.to_datetime(df["open_time"], errors="coerce")
    df["close_time"] = pd.to_datetime(df["close_time"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["forecast_prob"] = pd.to_numeric(df["forecast_prob"], errors="coerce")
    return add_score_columns(df)


def inject_theme() -> None:
    st.markdown(
        f"""
        <style>
          :root {{
            --bg: {PALETTE["bg"]};
            --panel: {PALETTE["panel"]};
            --panel-alt: {PALETTE["panel_alt"]};
            --border: {PALETTE["border"]};
            --text: {PALETTE["text"]};
            --muted: {PALETTE["muted"]};
            --grid: {PALETTE["grid"]};
            --polymarket: {PALETTE["polymarket"]};
            --kalshi: {PALETTE["kalshi"]};
            --accent: {PALETTE["accent"]};
          }}

          .stApp {{
            background:
              radial-gradient(circle at top left, rgba(179, 92, 56, 0.12), transparent 32%),
              linear-gradient(180deg, #f8f1e8 0%, var(--bg) 100%);
            color: var(--text);
          }}

          .block-container {{
            padding-top: 2.4rem;
            padding-bottom: 2.8rem;
            max-width: 1380px;
          }}

          [data-testid="stSidebar"] {{
            background: rgba(255, 249, 240, 0.92);
            border-right: 1px solid rgba(216, 205, 192, 0.65);
          }}

          [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
          [data-testid="stSidebar"] label,
          [data-testid="stSidebar"] .stSelectbox label,
          [data-testid="stSidebar"] .stMultiSelect label {{
            color: var(--muted);
          }}

          [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
            color: var(--text);
            letter-spacing: 0.02em;
          }}

          .hero-shell {{
            margin-bottom: 1.8rem;
            padding: 2rem 2rem 1.3rem;
            border: 1px solid rgba(216, 205, 192, 0.85);
            border-radius: 28px;
            background: linear-gradient(140deg, rgba(255, 249, 240, 0.94), rgba(250, 243, 232, 0.95));
            box-shadow: 0 24px 64px rgba(68, 52, 39, 0.08);
          }}

          .hero-kicker {{
            margin-bottom: 0.8rem;
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
          }}

          .hero-title {{
            margin: 0;
            font-size: clamp(2.5rem, 4vw, 4.4rem);
            line-height: 0.96;
            font-weight: 760;
            color: var(--text);
          }}

          .hero-copy {{
            max-width: 56rem;
            margin-top: 1rem;
            color: var(--muted);
            font-size: 1.05rem;
            line-height: 1.65;
          }}

          .section-label {{
            margin: 0 0 0.65rem;
            color: var(--muted);
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
          }}

          .metric-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1.35rem;
            margin: 0.35rem 0 2rem;
          }}

          .metric-card {{
            min-height: 190px;
            padding: 1.35rem 1.45rem 1.3rem;
            border-radius: 24px;
            background: rgba(255, 249, 240, 0.96);
            border: 1px solid rgba(216, 205, 192, 0.78);
            box-shadow: 0 18px 40px rgba(68, 52, 39, 0.06);
          }}

          .metric-label {{
            color: var(--muted);
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }}

          .metric-value {{
            margin-top: 0.7rem;
            color: var(--text);
            font-size: clamp(2rem, 2.8vw, 3.15rem);
            line-height: 1;
            font-weight: 780;
            letter-spacing: -0.03em;
          }}

          .metric-note {{
            margin-top: 0.9rem;
            color: var(--muted);
            font-size: 0.93rem;
            line-height: 1.45;
          }}

          .metric-accent {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            margin-top: 1rem;
            color: var(--accent);
            font-size: 0.83rem;
            font-weight: 700;
          }}

          .metric-dot {{
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 999px;
            background: var(--accent);
          }}

          div[data-testid="stTabs"] button {{
            font-weight: 700;
          }}

          div[data-testid="stPlotlyChart"] {{
            border: 1px solid rgba(216, 205, 192, 0.78);
            border-radius: 24px;
            background: rgba(255, 249, 240, 0.96);
            box-shadow: 0 16px 34px rgba(68, 52, 39, 0.05);
            padding: 0.35rem 0.35rem 0;
          }}

          div[data-testid="stDataFrame"] {{
            border: 1px solid rgba(216, 205, 192, 0.78);
            border-radius: 18px;
            overflow: hidden;
          }}

          @media (max-width: 1100px) {{
            .metric-grid {{
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
          }}

          @media (max-width: 720px) {{
            .hero-shell {{
              padding: 1.5rem 1.2rem 1.1rem;
            }}
            .metric-grid {{
              grid-template-columns: 1fr;
            }}
            .metric-card {{
              min-height: 160px;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def format_number(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def format_currency(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def empty_state() -> None:
    inject_theme()
    st.markdown(
        """
        <section class="hero-shell">
          <div class="hero-kicker">Prediction Market Analysis</div>
          <h1 class="hero-title">Prediction Market Accuracy</h1>
          <p class="hero-copy">
            No scored dataset is available yet. Build the main dataset first, then reload the dashboard.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.info("Run `python3 src/build_accuracy_dataset.py` from the project folder, then refresh this page.")


def filter_data(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filters")
        st.caption("Use the controls to isolate specific slices of platform, category, liquidity, and implied probability.")
        platforms = sorted(df["platform"].dropna().unique())
        categories = sorted(df["category"].dropna().unique())
        selected_platforms = st.multiselect("Platform", platforms, default=platforms)
        selected_categories = st.multiselect("Category", categories, default=categories)

        min_volume, max_volume = float(df["volume"].min()), float(df["volume"].max())
        volume_range = st.slider(
            "Volume",
            min_value=min_volume,
            max_value=max_volume,
            value=(min_volume, max_volume),
            format="$%.0f",
        )

        prob_range = st.slider(
            "Forecast probability",
            min_value=0.0,
            max_value=1.0,
            value=(0.0, 1.0),
            step=0.01,
        )

    return df[
        df["platform"].isin(selected_platforms)
        & df["category"].isin(selected_categories)
        & df["volume"].between(volume_range[0], volume_range[1])
        & df["forecast_prob"].between(prob_range[0], prob_range[1])
    ].copy()


def render_hero(df: pd.DataFrame) -> None:
    coverage = df.groupby("platform", observed=True)["market_id"].count().to_dict()
    st.markdown(
        f"""
        <section class="hero-shell">
          <div class="hero-kicker">Forecast Evaluation Dashboard</div>
          <h1 class="hero-title">Prediction Market Accuracy</h1>
          <p class="hero-copy">
            Resolved binary sports and elections markets with at least $100,000 in volume.
            Forecasts use the last non-trivial pre-resolution YES probability so the charts reflect
            actual forecast quality instead of trivial settlement prices.
          </p>
          <p class="hero-copy">
            Current filtered view includes {len(df):,} markets:
            {coverage.get("polymarket", 0):,} Polymarket and {coverage.get("kalshi", 0):,} Kalshi.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_metric_cards(df: pd.DataFrame) -> None:
    summary = metric_summary(df).iloc[0]
    lead_time = summary["median_days_to_resolution"]
    total_volume = df["volume"].sum()
    metrics = [
        {
            "label": "Markets",
            "value": f"{int(summary['n']):,}",
            "note": "Scored contracts in the current filtered view.",
            "accent": f"{df['platform'].nunique()} platforms in scope",
        },
        {
            "label": "Brier Score",
            "value": f"{summary['brier']:.3f}",
            "note": "Lower is better. Penalizes misses quadratically.",
            "accent": f"Observed YES rate {summary['observed_yes_rate']:.1%}",
        },
        {
            "label": "Avg Forecast",
            "value": f"{summary['avg_forecast']:.1%}",
            "note": "Mean implied YES probability across visible markets.",
            "accent": f"Median lead time {lead_time:.1f} days" if pd.notna(lead_time) else "Lead time unavailable for some rows",
        },
        {
            "label": "Total Volume",
            "value": format_currency(total_volume),
            "note": "Combined dollar volume of the visible market set.",
            "accent": f"Median market volume {format_currency(summary['median_volume'])}",
        },
    ]
    cards_html = "".join(
        f"""
        <article class="metric-card">
          <div class="metric-label">{item["label"]}</div>
          <div class="metric-value">{item["value"]}</div>
          <div class="metric-note">{item["note"]}</div>
          <div class="metric-accent"><span class="metric-dot"></span>{item["accent"]}</div>
        </article>
        """
        for item in metrics
    )
    st.markdown('<p class="section-label">Overview</p>', unsafe_allow_html=True)
    st.markdown(f'<section class="metric-grid">{cards_html}</section>', unsafe_allow_html=True)


def apply_plotly_theme(fig: go.Figure, title: str, height: int = 440) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=22, color=PALETTE["text"])),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,249,240,0.55)",
        font=dict(family="Avenir Next, Segoe UI, sans-serif", size=14, color=PALETTE["text"]),
        hoverlabel=dict(
            bgcolor=PALETTE["panel"],
            bordercolor=PALETTE["border"],
            font=dict(color=PALETTE["text"], size=13),
        ),
        margin=dict(t=76, r=26, b=56, l=56),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title_text="",
        ),
        height=height,
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        linecolor=PALETTE["border"],
        tickfont=dict(color=PALETTE["muted"]),
        title_font=dict(color=PALETTE["muted"], size=13),
    )
    fig.update_yaxes(
        gridcolor=PALETTE["grid"],
        gridwidth=1,
        zeroline=False,
        linecolor=PALETTE["border"],
        tickfont=dict(color=PALETTE["muted"]),
        title_font=dict(color=PALETTE["muted"], size=13),
    )
    return fig


def render_brier_charts(df: pd.DataFrame) -> None:
    by_platform_category = metric_summary(df, ["platform", "category"])
    by_category = metric_summary(df, ["category"])

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        fig = px.bar(
            by_platform_category,
            x="category",
            y="brier",
            color="platform",
            barmode="group",
            color_discrete_map=PLATFORM_COLORS,
            labels={"brier": "Brier score", "category": "", "platform": "Platform"},
            custom_data=["platform", "category", "n", "log_loss", "observed_yes_rate"],
        )
        fig.update_traces(
            marker_line_width=0,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Category: %{customdata[1]}<br>"
                "Markets: %{customdata[2]}<br>"
                "Brier: %{y:.3f}<br>"
                "Log loss: %{customdata[3]:.3f}<br>"
                "Observed YES: %{customdata[4]:.1%}<extra></extra>"
            ),
        )
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0,
            y=1.12,
            showarrow=False,
            text="Hover for market counts and supporting metrics",
            font=dict(size=12, color=PALETTE["muted"]),
        )
        apply_plotly_theme(fig, "Brier Score by Platform and Category")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.bar(
            by_category,
            x="category",
            y="observed_yes_rate",
            color="category",
            color_discrete_sequence=[PALETTE["accent"], PALETTE["polymarket"]],
            labels={"observed_yes_rate": "Observed YES rate", "category": ""},
            custom_data=["n", "brier", "avg_forecast"],
        )
        fig.update_traces(
            marker_line_width=0,
            text=by_category["observed_yes_rate"].map(lambda x: f"{x:.1%}"),
            textposition="outside",
            hovertemplate=(
                "Category: %{x}<br>"
                "Observed YES: %{y:.1%}<br>"
                "Markets: %{customdata[0]}<br>"
                "Brier: %{customdata[1]:.3f}<br>"
                "Avg forecast: %{customdata[2]:.1%}<extra></extra>"
            ),
        )
        apply_plotly_theme(fig, "Observed YES Rate by Category")
        fig.update_layout(showlegend=False)
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)


def render_calibration(df: pd.DataFrame) -> None:
    cal = calibration_table(df)
    cal["probability_bin"] = cal["probability_bin"].astype(str)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color=PALETTE["muted"], dash="dash", width=2),
            name="Perfect calibration",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=cal["avg_forecast"],
            y=cal["observed_yes_rate"],
            mode="markers+lines",
            marker=dict(
                size=(cal["n"].clip(lower=1) ** 0.5) * 7,
                color=cal["brier"],
                colorscale=[
                    [0.0, "#F3D7B8"],
                    [0.5, "#D98F5C"],
                    [1.0, PALETTE["polymarket"]],
                ],
                line=dict(color="rgba(255,249,240,0.9)", width=1.5),
                showscale=True,
                colorbar=dict(title="Brier", tickformat=".3f"),
            ),
            line=dict(color="rgba(31,90,145,0.35)", width=2),
            text=cal["probability_bin"],
            customdata=cal[["n", "brier"]],
            hovertemplate=(
                "Bucket: %{text}<br>"
                "Markets: %{customdata[0]}<br>"
                "Avg forecast: %{x:.1%}<br>"
                "Observed YES: %{y:.1%}<br>"
                "Brier: %{customdata[1]:.3f}<extra></extra>"
            ),
            name="Observed",
        )
    )
    apply_plotly_theme(fig, "Calibration by Probability Bucket", height=500)
    fig.update_xaxes(title="Average forecast probability", tickformat=".0%", range=[0, 1])
    fig.update_yaxes(title="Observed YES rate", tickformat=".0%", range=[0, 1])
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        cal.assign(
            avg_forecast_pct=cal["avg_forecast"] * 100,
            observed_yes_rate_pct=cal["observed_yes_rate"] * 100,
        )[["probability_bin", "n", "avg_forecast_pct", "observed_yes_rate_pct", "brier"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "probability_bin": "Probability bucket",
            "n": "Markets",
            "avg_forecast_pct": st.column_config.NumberColumn("Avg forecast", format="%.1f%%"),
            "observed_yes_rate_pct": st.column_config.NumberColumn("Observed YES", format="%.1f%%"),
            "brier": st.column_config.NumberColumn("Brier", format="%.3f"),
        },
    )


def render_market_table(df: pd.DataFrame) -> None:
    table = df.sort_values("volume", ascending=False)[
        [
            "platform",
            "category",
            "title",
            "resolution",
            "forecast_prob",
            "brier",
            "volume",
            "close_time",
        ]
    ].copy()
    table["forecast_prob"] = table["forecast_prob"] * 100
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "platform": "Platform",
            "category": "Category",
            "title": "Market",
            "resolution": "Result",
            "forecast_prob": st.column_config.NumberColumn("Forecast", format="%.1f%%"),
            "brier": st.column_config.NumberColumn("Brier", format="%.3f"),
            "volume": st.column_config.NumberColumn("Volume", format="$%.0f"),
            "close_time": st.column_config.DatetimeColumn("Close time"),
        },
    )


def main() -> None:
    df = load_data()
    if df.empty:
        empty_state()
        return

    inject_theme()
    filtered = filter_data(df)
    if filtered.empty:
        st.warning("No markets match the current filters.")
        return

    render_hero(filtered)
    render_metric_cards(filtered)

    tab1, tab2, tab3 = st.tabs(["Accuracy", "Calibration", "Markets"])
    with tab1:
        render_brier_charts(filtered)
    with tab2:
        render_calibration(filtered)
    with tab3:
        render_market_table(filtered)


if __name__ == "__main__":
    main()
