"""
케이스 3: CKD + HF + COPD 다계통 referral 환자 (demo patient C, subject_id=12468016).

타과 의뢰 시나리오. referral checklist 항목 검증.
parquet 로드 실패 시 RuntimeError를 던져 runner가 스킵.
"""
from __future__ import annotations

from data.loader import load_demo_patient
from eval.cases.base import EvalCase, ExpectedFlag

SUBJECT_ID = 12468016
PURPOSE = "referral"


def build() -> EvalCase:
    try:
        record = load_demo_patient(SUBJECT_ID, PURPOSE)
    except Exception as e:
        raise RuntimeError(
            f"Referral 케이스 데이터 로드 실패 (subject_id={SUBJECT_ID}): {e}"
        ) from e

    return EvalCase(
        name="multi_referral",
        patient_record=record,
        purpose=PURPOSE,
        expected_trend_directions={},
        expected_flags=[],
        expected_checklist_keywords=[
            # referral 목적 규칙에서 생성되는 항목
            "의뢰서",
        ],
        expected_absent_flag_labels=[],
        min_judge_total=18.0,
    )
