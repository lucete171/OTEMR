"""
Change Flags 패널 컴포넌트.
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
        st.success("특이 변화 없음 (Change flags 없음)")
        return

    st.markdown("### ⚠️ Change Flags")
    for flag in flags:
        cfg = SEVERITY_CONFIG.get(flag.severity, SEVERITY_CONFIG["LOW"])
        with st.container():
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
