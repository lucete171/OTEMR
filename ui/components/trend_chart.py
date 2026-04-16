"""
Altair 스파크라인 컴포넌트.
"""
from typing import Optional

import pandas as pd
import streamlit as st

try:
    import altair as alt
    HAS_ALTAIR = True
except ImportError:
    HAS_ALTAIR = False

from analysis.trend import TrendResult
from models.clinical_output import TrendSummary

DIRECTION_COLORS = {
    "WORSENING": "#e74c3c",
    "IMPROVING": "#27ae60",
    "STABLE": "#95a5a6",
    "CHANGING": "#f39c12",
    "UNKNOWN": "#bdc3c7",
}


def render_trend_row(
    trend: TrendResult,
    summary: Optional[TrendSummary] = None,
) -> None:
    """
    Lab 트렌드 한 행 렌더링 (label + 스파크라인 + 값 + 방향).

    summary가 제공되면 이상값(⚡) / 변화점(📍) 배지를 추가로 표시.
    """
    col1, col2, col3 = st.columns([2, 3, 2])

    with col1:
        ref_badge = {
            "HIGH": "🔴",
            "LOW": "🔵",
            "NORMAL": "🟢",
            "UNKNOWN": "⚪",
        }.get(trend.ref_flag, "⚪")

        # 고급 분석 배지
        adv_badges = ""
        if summary is not None:
            if summary.is_anomaly:
                z_str = f"z={summary.anomaly_score:.1f}" if summary.anomaly_score else ""
                adv_badges += f" <span title='통계적 이상값 {z_str}' style='cursor:help'>⚡</span>"
            if summary.change_point_detected:
                conf_str = f"{summary.change_point_confidence:.0%}"
                adv_badges += f" <span title='변화점 감지 ({conf_str})' style='cursor:help'>📍</span>"

        st.markdown(
            f"**{trend.label}** {ref_badge}{adv_badges}",
            unsafe_allow_html=True,
        )

    with col2:
        if trend.sparkline and len(trend.sparkline) >= 2 and HAS_ALTAIR:
            _render_sparkline(trend, summary=summary)
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


def _render_sparkline(
    trend: TrendResult,
    summary: Optional[TrendSummary] = None,
) -> None:
    df = pd.DataFrame(trend.sparkline, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])

    color = DIRECTION_COLORS.get(trend.direction, "#95a5a6")

    line = (
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

    # 변화점 위치에 수직 규칙선 추가
    if (
        summary is not None
        and summary.change_point_detected
        and summary.change_point_index is not None
    ):
        cp_idx = summary.change_point_index
        # sparkline은 최대 10개로 thin 처리 — raw index를 sparkline index로 근사
        n_spark = len(trend.sparkline)
        n_raw = trend.n_points
        # sparkline index 비례 계산
        spark_idx = min(int(cp_idx * n_spark / max(n_raw, 1)), n_spark - 1)
        if 0 <= spark_idx < n_spark:
            cp_date = df["date"].iloc[spark_idx]
            cp_df = pd.DataFrame({"date": [cp_date]})
            rule = (
                alt.Chart(cp_df)
                .mark_rule(color="#e67e22", strokeWidth=1.5, strokeDash=[3, 3])
                .encode(x="date:T")
            )
            chart = line + rule
        else:
            chart = line
    else:
        chart = line

    st.altair_chart(chart, use_container_width=False)
