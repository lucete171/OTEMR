"""
Must-check 체크리스트 패널 컴포넌트.
"""
import streamlit as st
from agent.output_schema import ChecklistItemOutput

URGENCY_CONFIG = {
    "URGENT":   {"icon": "🚨", "color": "#e74c3c"},
    "ROUTINE":  {"icon": "📋", "color": "#2c3e50"},
    "OPTIONAL": {"icon": "💡", "color": "#7f8c8d"},
}


def render_checklist_panel(checklist: list[ChecklistItemOutput]) -> None:
    if not checklist:
        st.info("생성된 체크리스트 항목 없음")
        return

    st.markdown("### ✅ Must-Check 체크리스트")
    for item in checklist:
        cfg = URGENCY_CONFIG.get(item.urgency, URGENCY_CONFIG["ROUTINE"])
        with st.expander(f"{cfg['icon']} {item.item}", expanded=(item.urgency == "URGENT")):
            st.markdown(
                f"<span style='color:{cfg['color']}; font-size:0.85em'>"
                f"**{item.urgency}**</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**WHY**: {item.reason}")
