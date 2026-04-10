"""
데모용 사전 선정 환자 목록.

각 케이스는 각각 다른 임상 시나리오를 커버:
  - Case A: DM + CKD 진행 → 트렌드 시각화, 인계용
  - Case B: 수술 전 심장 위험 환자 → Pre-op
  - Case C: 복잡 다계통 타과 의뢰 → Referral

subject_id는 BQ 접근 후 scripts/cache_demo_patients.py 실행 시 채워짐.
지금은 placeholder 값으로 설정.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class DemoCase:
    case_id: str           # "A", "B", "C"
    label: str             # UI에 표시될 이름
    subject_id: int        # MIMIC-IV subject_id (BQ 접근 후 채움)
    default_purpose: str   # 기본 목적
    description: str       # 케이스 설명
    diagnosis_tags: list[str]  # 주요 진단 태그 (표시용)


DEMO_CASES: list[DemoCase] = [
    DemoCase(
        case_id="A",
        label="Case A: DM + CKD/ESRD",
        subject_id=18767874,
        default_purpose="rounds",
        description="71세 여성. T2DM + CKD stage5/ESRD + 투석 의존 + HTN + HF. 복합 대사·신장 문제.",
        diagnosis_tags=["DM", "CKD/ESRD", "HTN", "HF"],
    ),
    DemoCase(
        case_id="B",
        label="Case B: 수술 전 심장 위험",
        subject_id=13303809,
        default_purpose="preop",
        description="36세 여성. CAD + 과거 MI + CABG 시행력 + 항응고제 복용 중 + T1DM. 수술 전 평가.",
        diagnosis_tags=["CAD", "old MI", "CABG", "Anticoagulation", "T1DM"],
    ),
    DemoCase(
        case_id="C",
        label="Case C: 복합 다계통 의뢰",
        subject_id=12468016,
        default_purpose="referral",
        description="50세 남성. CKD + HF + COPD + AKI + Crohn's. 복합 다계통 환자, 타과 의뢰.",
        diagnosis_tags=["CKD", "HF", "COPD", "AKI", "Crohn's"],
    ),
]


def get_case(case_id: str) -> Optional[DemoCase]:
    for case in DEMO_CASES:
        if case.case_id == case_id:
            return case
    return None


def get_available_cases() -> list[DemoCase]:
    """subject_id가 설정된 케이스만 반환 (0은 미설정)."""
    return [c for c in DEMO_CASES if c.subject_id != 0]


def get_all_cases() -> list[DemoCase]:
    return DEMO_CASES
