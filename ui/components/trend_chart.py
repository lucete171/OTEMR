"""
Altair 스파크라인 컴포넌트.
"""
import pandas as pd
import streamlit as st

try:
    import altair as alt
    HAS_ALTAIR = True
except ImportError:
    HAS_ALTAIR = False

from analysis.trend import TrendResult

DIRECTION_COLORS = {
    "WORSENING": "#e74c3c",
    "IMPROVING": "#27ae60",
    "STABLE": "#95a5a6",
    "CHANGING": "#f39c12",
    "UNKNOWN": "#bdc3c7",
}


def render_trend_row(trend: TrendResult) -> None:
    """Lab 트렌드 한 행 렌더링 (label + 스파크라인 + 값 + 방향)."""
    col1, col2, col3 = st.columns([2, 3, 2])

    with col1:
        ref_badge = {
            "HIGH": "🔴",
            "LOW": "🔵",
            "NORMAL": "🟢",
            "UNKNOWN": "⚪",
        }.get(trend.ref_flag, "⚪")
        st.markdown(f"**{trend.label}** {ref_badge}")

    with col2:
        if trend.sparkline and len(trend.sparkline) >= 2 and HAS_ALTAIR:
            _render_sparkline(trend)
        elif not trend.has_recent_data:
            st.caption("데이터 없음")
        else:
            st.caption(f"({trend.n_points}개 포인트)")

    with col3:
        if trend.has_recent_data:
            val_str = f"{trend.last_value:.2f} {trend.unit}".strip()
            dir_color = DIRECTION_COLORS.get(trend.direction, "#bdc3c7")
            dir_arrow = {
                "WORSENING": "↓" if trend.label in ("Hemoglobin", "Platelet") else "↑",
                "IMPROVING": "↑" if trend.label in ("Hemoglobin", "Platelet") else "↓",
                "STABLE": "→",
            }.get(trend.direction, "")
            st.markdown(
                f"<span style='color:{dir_color}; font-weight:bold'>{val_str} {dir_arrow}</span>",
                unsafe_allow_html=True,
            )
            if trend.delta_pct is not None and abs(trend.delta_pct) >= 5:
                sign = "+" if trend.delta_pct > 0 else ""
                st.caption(f"{sign}{trend.delta_pct:.1f}% vs prev")
        else:
            st.caption("—")


def _render_sparkline(trend: TrendResult) -> None:
    df = pd.DataFrame(trend.sparkline, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])

    color = DIRECTION_COLORS.get(trend.direction, "#95a5a6")

    chart = (
        alt.Chart(df)
        .mark_line(color=color, strokeWidth=2)
        .encode(
            x=alt.X("date:T", axis=None),
            y=alt.Y("value:Q", axis=None, scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("date:T", format="%Y-%m-%d"),
                alt.Tooltip("value:Q", format=".2f"),
            ],
        )
        .properties(width=150, height=50)
    )
    st.altair_chart(chart, use_container_width=False)
