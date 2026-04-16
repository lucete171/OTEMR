"""
고급 임상 분석 패널.

표시 내용:
  - 환자 상태 배지 (STABLE / DETERIORATING / CRITICAL / RECOVERING)
  - 다변량 패널 신호 (RENAL / ANEMIA / COAGULATION) — NORMAL 제외
  - 통계적 이상값 탐지 결과
  - 변화점 탐지 결과
"""
import streamlit as st

from models.clinical_output import ClinicalAnalysisOutput

# ── 상태별 스타일 ─────────────────────────────────────────────
STATE_CONFIG = {
    "CRITICAL": {
        "icon": "🔴",
        "label": "위중 (CRITICAL)",
        "color": "#c0392b",
        "bg": "#fadbd8",
        "border": "#e74c3c",
    },
    "DETERIORATING": {
        "icon": "🟠",
        "label": "악화 중 (DETERIORATING)",
        "color": "#d35400",
        "bg": "#fdebd0",
        "border": "#e67e22",
    },
    "RECOVERING": {
        "icon": "🟡",
        "label": "회복 중 (RECOVERING)",
        "color": "#b7950b",
        "bg": "#fef9e7",
        "border": "#f1c40f",
    },
    "STABLE": {
        "icon": "🟢",
        "label": "안정 (STABLE)",
        "color": "#1e8449",
        "bg": "#eafaf1",
        "border": "#27ae60",
    },
}

PANEL_SEVERITY_COLOR = {
    "SEVERE":   ("#c0392b", "#fadbd8"),
    "MODERATE": ("#d35400", "#fdebd0"),
    "MILD":     ("#b7950b", "#fef9e7"),
    "NORMAL":   ("#1e8449", "#eafaf1"),
}

PANEL_LABEL_KR = {
    "RENAL":       "신장 기능",
    "ANEMIA":      "빈혈",
    "COAGULATION": "응고",
}

SEVERITY_LABEL_KR = {
    "SEVERE":   "중증",
    "MODERATE": "중등도",
    "MILD":     "경증",
    "NORMAL":   "정상",
}


def render_advanced_panel(advanced: ClinicalAnalysisOutput) -> None:
    """고급 분석 결과 전체 패널 렌더링 (배지 제외 — app.py에서 별도 렌더)."""
    # 다변량 신호 (NORMAL 제외)
    non_normal = [s for s in advanced.multivariate_signals if s.severity != "NORMAL"]
    if non_normal:
        st.markdown("#### 🔬 복합 임상 패널")
        for sig in non_normal:
            _render_multivariate_card(sig)

    # 이상값 + 변화점
    anomalies = [s for s in advanced.trend_summaries if s.is_anomaly]
    changepoints = [s for s in advanced.trend_summaries if s.change_point_detected]

    if anomalies or changepoints:
        with st.expander(
            f"📊 고급 시계열 신호 — 이상값 {len(anomalies)}건 · 변화점 {len(changepoints)}건",
            expanded=advanced.patient_state in ("CRITICAL", "DETERIORATING"),
        ):
            if anomalies:
                st.caption("**통계적 이상값** (환자 개인 기준 z-score 초과)")
                for s in anomalies:
                    z = s.anomaly_score
                    z_str = f"z={z:.2f}" if z is not None else ""
                    st.markdown(
                        f"<div style=\"background:#fdecea;border-left:3px solid #e74c3c;"
                        f"padding:6px 10px;margin-bottom:4px;border-radius:3px;color:#1a1a1a\">"
                        f"&#9889; <b>{s.label}</b> {z_str} &mdash; {s.anomaly_interpretation}</div>",
                        unsafe_allow_html=True,
                    )

            if changepoints:
                if anomalies:
                    st.divider()
                st.caption("**변화점 탐지** (값의 평균이 구조적으로 이동한 시점)")
                for s in changepoints:
                    conf = f"{s.change_point_confidence:.0%}" if s.change_point_confidence else ""
                    st.markdown(
                        f"<div style=\"background:#eaf4fb;border-left:3px solid #2980b9;"
                        f"padding:6px 10px;margin-bottom:4px;border-radius:3px;color:#1a1a1a\">"
                        f"&#128205; <b>{s.label}</b> {conf} &mdash; {s.change_point_interpretation}</div>",
                        unsafe_allow_html=True,
                    )


def render_state_badge_inline(advanced: ClinicalAnalysisOutput) -> None:
    """환자 상태 배지만 단독 렌더링 (헤더 영역 등에서 사용)."""
    _render_state_badge(advanced)


# ──────────────────────────────────────────────────────────────
# 내부 렌더 함수
# ──────────────────────────────────────────────────────────────

def _render_state_badge(advanced: ClinicalAnalysisOutput) -> None:
    cfg = STATE_CONFIG.get(advanced.patient_state, STATE_CONFIG["STABLE"])
    score = advanced.deterioration_score
    score_display = "" if score == 99 else f" &middot; score {score}"

    # 전이 정보 (from_state가 있을 때만 표시)
    transition_html = ""
    if advanced.state_transition and advanced.state_transition.from_state:
        t = advanced.state_transition
        triggered = ", ".join(t.triggered_by[:3]) if t.triggered_by else ""
        triggered_str = f" ({triggered})" if triggered else ""
        transition_html = (
            f"<br><small style=\"color:{cfg['color']}\">"
            f"&uarr; {t.from_state} &rarr; {t.to_state}{triggered_str}"
            f"</small>"
        )

    # 들여쓰기 없이 한 줄로 작성 — 4칸 이상 들여쓰기 시 Markdown이 코드블록으로 처리하는 문제 방지
    html = (
        f"<div style=\"background:{cfg['bg']};border-left:5px solid {cfg['border']};"
        f"padding:10px 14px;margin-bottom:12px;border-radius:5px;color:{cfg['color']};\">"
        f"<span style=\"font-size:1.05em;font-weight:bold\">"
        f"{cfg['icon']} 환자 상태: {cfg['label']}{score_display}"
        f"</span>"
        f"{transition_html}"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_multivariate_card(sig) -> None:
    color, bg = PANEL_SEVERITY_COLOR.get(sig.severity, ("#555", "#f5f5f5"))
    panel_kr = PANEL_LABEL_KR.get(sig.panel, sig.panel)
    severity_kr = SEVERITY_LABEL_KR.get(sig.severity, sig.severity)
    items_str = ", ".join(sig.contributing_items)

    with st.expander(
        f"{panel_kr} — {severity_kr} ({items_str})",
        expanded=sig.severity in ("SEVERE", "MODERATE"),
    ):
        st.markdown(
            f"<div style=\"background:{bg};border-left:4px solid {color};"
            f"padding:8px 12px;border-radius:4px;color:#1a1a1a;margin-bottom:8px\">"
            f"{sig.interpretation}</div>",
            unsafe_allow_html=True,
        )
        if sig.reasoning_trace:
            st.caption("추론 근거")
            for line in sig.reasoning_trace:
                st.caption(f"  · {line}")
        if sig.confidence < 0.8:
            st.caption(f"⚠️ 신뢰도 {sig.confidence:.0%} — 데이터 포인트 부족")
