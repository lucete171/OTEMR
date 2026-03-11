"""
GPT-4 임상 요약 패널.
"""
import streamlit as st
from agent.output_schema import AgentOutput, PreVisitContext


def render_summary_panel(output: AgentOutput) -> None:
    ctx = output.pre_visit_context

    # 데이터 충분도
    _render_sufficiency(ctx)

    st.markdown("### 📋 임상 요약")
    st.markdown(ctx.patient_summary)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Active Problems**")
        for problem in ctx.active_problems:
            st.markdown(f"- {problem}")

    with col2:
        st.markdown("**Current Medications**")
        for med in ctx.current_medications:
            st.markdown(f"- {med}")

    if ctx.relevant_labs:
        st.markdown("**Key Labs**")
        for lab in ctx.relevant_labs:
            trend_icon = {
                "WORSENING": "↗️ 악화",
                "IMPROVING": "↘️ 호전",
                "STABLE": "→ 안정",
            }.get(lab.trend, "")
            st.markdown(
                f"- **{lab.label}**: {lab.value} ({lab.date}) {trend_icon}  \n"
                f"  _{lab.interpretation}_"
            )

    # Raw JSON (디버깅용 expander)
    with st.expander("Raw JSON (개발용)", expanded=False):
        st.json(output.model_dump())


def _render_sufficiency(ctx: PreVisitContext) -> None:
    gaps = ctx.data_sufficiency.gaps
    total_expected = len(ctx.relevant_labs) + len(gaps)
    available = len(ctx.relevant_labs)

    if total_expected > 0:
        ratio = available / total_expected
        st.progress(ratio, text=f"데이터 충분도: {available}/{total_expected}")

    if gaps:
        with st.expander(f"⚠️ 데이터 갭 {len(gaps)}개", expanded=False):
            for gap in gaps:
                st.markdown(f"- {gap}")
