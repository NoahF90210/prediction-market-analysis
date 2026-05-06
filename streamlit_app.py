from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.accuracy import add_score_columns, calibration_table, metric_summary

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "cleaned" / "accuracy_markets.csv"


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


def format_number(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def empty_state() -> None:
    st.title("Prediction Market Accuracy")
    st.info(
        "No scored dataset found yet. Run `python3 src/build_accuracy_dataset.py` "
        "from the project folder, then refresh this dashboard."
    )


def filter_data(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filters")
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


def render_metrics(df: pd.DataFrame) -> None:
    summary = metric_summary(df).iloc[0]
    total_volume = df["volume"].sum()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Markets", f"{int(summary['n']):,}")
    col2.metric("Brier Score", f"{summary['brier']:.3f}")
    col3.metric("Avg Forecast", f"{summary['avg_forecast']:.1%}")
    col4.metric("Total Volume", f"${format_number(total_volume)}")


def render_brier_charts(df: pd.DataFrame) -> None:
    by_platform_category = metric_summary(df, ["platform", "category"])
    by_category = metric_summary(df, ["category"])

    left, right = st.columns([1.2, 1])
    with left:
        fig = px.bar(
            by_platform_category,
            x="category",
            y="brier",
            color="platform",
            barmode="group",
            text="n",
            labels={"brier": "Brier score", "category": "", "platform": "Platform"},
            title="Brier Score by Platform and Category",
        )
        fig.update_traces(texttemplate="%{text} markets", textposition="outside")
        fig.update_layout(legend_orientation="h", legend_y=-0.2, margin=dict(t=60, b=80))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.bar(
            by_category,
            x="category",
            y="observed_yes_rate",
            color="category",
            text=by_category["observed_yes_rate"].map(lambda x: f"{x:.1%}"),
            labels={"observed_yes_rate": "Observed YES rate", "category": ""},
            title="Observed YES Rate",
        )
        fig.update_layout(showlegend=False, yaxis_tickformat=".0%", margin=dict(t=60, b=40))
        fig.update_traces(textposition="outside")
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
            line=dict(color="#2f2f2f", dash="dash"),
            name="Perfect calibration",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=cal["avg_forecast"],
            y=cal["observed_yes_rate"],
            mode="markers+lines",
            marker=dict(
                size=(cal["n"].clip(lower=1) ** 0.5) * 8,
                color=cal["brier"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Brier"),
            ),
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
    fig.update_layout(
        title="Calibration by Probability Bucket",
        xaxis_title="Average forecast probability",
        yaxis_title="Observed YES rate",
        xaxis_tickformat=".0%",
        yaxis_tickformat=".0%",
        xaxis_range=[0, 1],
        yaxis_range=[0, 1],
        margin=dict(t=60, b=40),
    )
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

    st.title("Prediction Market Accuracy")
    st.caption(
        "Resolved binary sports and elections markets with at least $100,000 in volume. "
        "Forecasts use the last non-trivial pre-resolution YES probability."
    )

    filtered = filter_data(df)
    if filtered.empty:
        st.warning("No markets match the current filters.")
        return

    render_metrics(filtered)

    tab1, tab2, tab3 = st.tabs(["Accuracy", "Calibration", "Markets"])
    with tab1:
        render_brier_charts(filtered)
    with tab2:
        render_calibration(filtered)
    with tab3:
        render_market_table(filtered)


if __name__ == "__main__":
    main()
