"""
케이스 1: DM + CKD 환자 (rounds).

tests/fixtures/patient_dm_ckd.py의 합성 환자(99001)를 재활용.
Creatinine WORSENING + HIGH flag + Metformin 안전 체크 검증.
"""
from eval.cases.base import EvalCase, ExpectedFlag
from tests.fixtures.patient_dm_ckd import get_fixture


def build() -> EvalCase:
    record = get_fixture()
    record.purpose = "rounds"

    return EvalCase(
        name="dm_ckd_rounds",
        patient_record=record,
        purpose="rounds",
        expected_trend_directions={
            "Creatinine": "WORSENING",
            "Hemoglobin": "WORSENING",
            "BUN": "WORSENING",
        },
        expected_flags=[
            # 직전 delta 10.5%(1.9→2.1)는 50% 미만 → WORSENING+ref HIGH → MEDIUM
            ExpectedFlag(lab_label="Creatinine", severity="MEDIUM"),
        ],
        expected_checklist_keywords=[
            # MEDIUM flag → AKI checklist 미생성, metformin 안전 규칙은 항상 실행
            "metformin",
        ],
        expected_absent_flag_labels=[
            "Sodium",   # 변화 없음 — flag 생성되면 안 됨
            "INR",      # 정상 범위 내
        ],
        min_judge_total=18.0,
    )
