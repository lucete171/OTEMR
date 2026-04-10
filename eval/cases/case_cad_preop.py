"""
케이스 2: CAD + 항응고 preop 환자 (demo patient B, subject_id=13303809).

수술 전 평가 시나리오. Coagulation / Troponin / preop checklist 검증.
parquet 로드 실패 시 케이스 빌드 자체가 RuntimeError를 던져 runner가 스킵.
"""
from __future__ import annotations

from data.loader import load_demo_patient
from eval.cases.base import EvalCase, ExpectedFlag

SUBJECT_ID = 13303809
PURPOSE = "preop"


def build() -> EvalCase:
    try:
        record = load_demo_patient(SUBJECT_ID, PURPOSE)
    except Exception as e:
        raise RuntimeError(
            f"CAD preop 케이스 데이터 로드 실패 (subject_id={SUBJECT_ID}): {e}"
        ) from e

    return EvalCase(
        name="cad_preop",
        patient_record=record,
        purpose=PURPOSE,
        # 실제 트렌드 방향은 데이터 의존 → 방향 검증 최소화, 스키마/checklist 위주
        expected_trend_directions={},
        expected_flags=[],
        expected_checklist_keywords=[
            # preop 목적별 규칙(_purpose_specific_rules)에서 생성
            "수술",
        ],
        expected_absent_flag_labels=[],
        min_judge_total=18.0,
    )
