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
        label="Case A: DM + CKD 진행",
        subject_id=0,  # TODO: BQ 쿼리 후 채울 것
        default_purpose="rounds",
        description="당뇨 + 만성신장질환 3기 환자. Cr이 3회 입원에 걸쳐 상승 중.",
        diagnosis_tags=["DM", "CKD", "HTN"],
    ),
    DemoCase(
        case_id="B",
        label="Case B: 수술 전 심장 위험",
        subject_id=0,  # TODO: BQ 쿼리 후 채울 것
        default_purpose="preop",
        description="고혈압 + 관상동맥질환 환자. 항응고제 복용 중. 복강경 담낭절제술 예정.",
        diagnosis_tags=["CAD", "HTN", "Anticoagulation"],
    ),
    DemoCase(
        case_id="C",
        label="Case C: 타과 의뢰",
        subject_id=0,  # TODO: BQ 쿼리 후 채울 것
        default_purpose="referral",
        description="간경화 + 복수 환자. 간담도외과 의뢰 예정.",
        diagnosis_tags=["Cirrhosis", "Ascites", "HE"],
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
