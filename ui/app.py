"""
OTEMR Agent 01 — Streamlit 데모 앱.

실행: streamlit run ui/app.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logger = logging.getLogger(__name__)

import streamlit as st

from analysis.checklist import generate_checklist
from analysis.flags import detect_flags
from analysis.trend import compute_trends
from agent.context_builder import build_user_context
from agent.summarizer import generate
from config.lab_profiles import get_item_ids_for_purpose_and_diagnoses
from data import cache
from data.demo_patients import DEMO_CASES, get_case
from data.loader import load_demo_patient

# Fixture fallback (BQ 없을 때)
from tests.fixtures.patient_dm_ckd import get_fixture as get_dm_ckd_fixture

DEMO_SUBJECT_IDS = {c.subject_id for c in DEMO_CASES}

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="OTEMR — Clinical Briefing",
    page_icon="🏥",
    layout="wide",
)

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────

PURPOSE_LABELS = {
    "rounds": "🌙 인계용",
    "preop": "🔪 수술 전",
    "referral": "📨 타과 의뢰",
}

PURPOSE_DESCRIPTIONS = {
    "rounds": "최근 72시간 변화 중심 · 즉각 주의 사항 강조",
    "preop": "심장/신장/응고 위험도 · 항응고제 bridge 계획",
    "referral": "전문의를 위한 전체 임상 요약 · 의뢰 이유 선두",
}


# ──────────────────────────────────────────────
# 환자 로드 (캐시 → fixture fallback)
# ──────────────────────────────────────────────

def load_patient_record(subject_id: int, purpose: str):
    """캐시 → demo parquet → BQ → fixture 순으로 로드."""
    cache_key = f"{subject_id}_{purpose}_180"
    cached = cache.load(cache_key)
    if cached is not None:
        return cached, "cache"

    # demo parquet
    if subject_id in DEMO_SUBJECT_IDS:
        try:
            record = load_demo_patient(subject_id, purpose)
            return record, "demo"
        except Exception as e:
            logger.warning(f"Demo parquet load failed for {subject_id}: {e}")

    # fixture (99001 전용)
    if subject_id == 99001:
        record = get_dm_ckd_fixture()
        record.purpose = purpose
        return record, "fixture"

    # BQ 시도
    try:
        from data.loader import load_patient
        record = load_patient(subject_id=subject_id, purpose=purpose)
        return record, "bq"
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None, None


# ──────────────────────────────────────────────
# 파이프라인 실행
# ──────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def run_pipeline(subject_id: int, purpose: str):
    """전체 파이프라인 실행 (캐시됨)."""
    record, source = load_patient_record(subject_id, purpose)
    if record is None:
        return None, None, None, None, None

    # 분석
    item_ids = get_item_ids_for_purpose_and_diagnoses(purpose, record.icd_prefixes)
    trends = compute_trends(record.labs, item_ids)
    flags = detect_flags(trends)
    checklist = generate_checklist(record, trends, flags)

    # 프롬프트 + GPT-4
    user_context = build_user_context(record, trends, flags, checklist)
    output = generate(user_context=user_context, purpose=purpose)

    return record, trends, flags, checklist, output


# ──────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────

def main():
    # 사이드바
    with st.sidebar:
        st.title("🏥 OTEMR")
        st.caption("AI Clinical Briefing — Agent 01")
        st.divider()

        st.markdown("**환자 선택**")
        patient_mode = st.radio(
            "모드",
            ["Demo 케이스", "직접 입력"],
            label_visibility="collapsed",
        )

        if patient_mode == "Demo 케이스":
            case_options = {
                f"Case {c.case_id}: {c.label}": c.case_id
                for c in DEMO_CASES
            }
            # Fixture 데모 케이스 추가
            case_options["[Fixture] DM+CKD 합성 데이터"] = "FIXTURE"
            selected_label = st.selectbox("케이스", list(case_options.keys()))
            selected_case_id = case_options[selected_label]

            if selected_case_id == "FIXTURE":
                subject_id = 99001
            else:
                case = get_case(selected_case_id)
                subject_id = case.subject_id if case else 99001
        else:
            subject_id = st.number_input("Subject ID", min_value=1, value=99001)

        st.divider()
        st.markdown("**도움말**")
        st.caption("BQ 셋업 전에는 [Fixture] 케이스로 전체 파이프라인을 테스트할 수 있습니다.")

    # 메인 컨텐츠
    st.title("Clinical Briefing")

    # 목적 선택
    purpose_cols = st.columns(3)
    if "purpose" not in st.session_state:
        st.session_state.purpose = "rounds"

    for i, (purpose_key, purpose_label) in enumerate(PURPOSE_LABELS.items()):
        with purpose_cols[i]:
            is_selected = st.session_state.purpose == purpose_key
            if st.button(
                purpose_label,
                key=f"btn_{purpose_key}",
                use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                st.session_state.purpose = purpose_key
                st.rerun()

    purpose = st.session_state.purpose
    st.caption(PURPOSE_DESCRIPTIONS[purpose])
    st.divider()

    # 파이프라인 실행
    with st.spinner("데이터 로드 및 GPT-4 요약 생성 중..."):
        result = run_pipeline(subject_id, purpose)
        record, trends, flags, checklist, output = result

    if record is None or output is None:
        st.error("데이터를 불러올 수 없습니다.")
        return

    # Patient Header
    diag_tags = [d.icd_code[:3] for d in record.diagnoses[:5]]
    st.markdown(
        f"**{record.anchor_age}세 {record.gender}** "
        f"| {', '.join(diag_tags)} "
        f"| 입원: {record.admissions[0].admittime.strftime('%Y-%m-%d') if record.admissions else '—'}"
    )

    # 3개 컬럼 레이아웃
    left, right = st.columns([3, 2])

    with left:
        # Change Flags
        from ui.components.flags_panel import render_flags_panel
        render_flags_panel(flags)

        st.divider()

        # 임상 요약
        from ui.components.summary_panel import render_summary_panel
        render_summary_panel(output)

    with right:
        # Lab 트렌드
        st.markdown("### 📈 Lab 트렌드")
        from ui.components.trend_chart import render_trend_row

        sorted_trends = sorted(
            trends.values(),
            key=lambda t: (not t.has_recent_data, t.direction != "WORSENING"),
        )
        for trend in sorted_trends[:12]:  # 최대 12개 표시
            render_trend_row(trend)
            st.divider()

        # Must-check 체크리스트
        from ui.components.checklist_panel import render_checklist_panel
        render_checklist_panel(output.checklist)


if __name__ == "__main__":
    main()
