"""
Change Flags 패널 — 3레이어 구조.
"""
import streamlit as st
from analysis.flags import ChangeFlag

SEVERITY_CONFIG = {
    "HIGH":   {"icon": "🔴", "color": "#e74c3c", "bg": "#fdecea"},
    "MEDIUM": {"icon": "🟡", "color": "#f39c12", "bg": "#fef9e7"},
    "LOW":    {"icon": "🔵", "color": "#3498db", "bg": "#eaf4fb"},
}


def render_flags_panel(flags: list[ChangeFlag]) -> None:
    if not flags:
        st.success("특이 변화 없음")
        return

    st.markdown("### ⚠️ Change Flags")

    # ── Layer 1: 항상 보임 ─────────────────────────
    layer1 = [f for f in flags if f.visibility == "ALWAYS"]
    if layer1:
        for flag in layer1:
            _render_flag_card(flag)
    else:
        st.success("🟢 현재 임계값 이탈 없음")

    # ── Layer 2: 트렌드 이상 (접혀있다가 펼쳐짐) ────
    layer2 = [f for f in flags if f.visibility == "ON_ALERT"]
    if layer2:
        with st.expander(
            f"🟡 트렌드 주의 {len(layer2)}건 — 지금은 정상, 방향이 나쁨",
            expanded=len(layer1) == 0  # Layer 1 없으면 자동 펼침
        ):
            st.caption("의사가 마지막 기록만 보면 놓치는 변화입니다.")
            for flag in layer2:
                cfg = SEVERITY_CONFIG.get(flag.severity, SEVERITY_CONFIG["LOW"])
                st.markdown(
                    f"""
                    <div style="
                        background-color:{cfg['bg']};
                        border-left: 4px solid {cfg['color']};
                        padding: 8px 12px;
                        margin-bottom: 6px;
                        border-radius: 4px;
                    ">
                        <span style="font-weight:bold">{cfg['icon']} {flag.label}</span>
                        &nbsp;—&nbsp;{flag.trend_message}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # ── Layer 3: 히스토리 (기본 숨김) ───────────────
    layer3 = [f for f in flags if f.visibility == "ON_DEMAND"]
    if layer3:
        with st.expander(f"📁 전체 히스토리 {len(layer3)}건", expanded=False):
            st.caption("방향은 정상이거나 변화폭이 작은 항목입니다.")
            for flag in layer3:
                _render_flag_card(flag)


def _render_flag_card(flag: ChangeFlag) -> None:
    cfg = SEVERITY_CONFIG.get(flag.severity, SEVERITY_CONFIG["LOW"])
    st.markdown(
        f"""
        <div style="
            background-color:{cfg['bg']};
            border-left: 4px solid {cfg['color']};
            padding: 8px 12px;
            margin-bottom: 6px;
            border-radius: 4px;
        ">
            <span style="font-weight:bold">{cfg['icon']} {flag.label}</span>
            &nbsp;—&nbsp;{flag.message}
        </div>
        """,
        unsafe_allow_html=True,
    )