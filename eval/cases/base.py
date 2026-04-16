"""
EvalCase 데이터클래스.

평가 케이스는 환자 데이터 + 기대값(expected outputs)으로 구성된다.
rule_eval.py가 이 기대값과 실제 파이프라인 출력을 비교한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from data.loader import PatientRecord


@dataclass
class ExpectedFlag:
    """기대하는 ChangeFlag 조건."""
    lab_label: str              # 예: "Creatinine"
    severity: str               # "HIGH" | "MEDIUM" | "LOW"


@dataclass
class EvalCase:
    """단일 평가 케이스."""
    name: str
    patient_record: PatientRecord
    purpose: str

    # 1차 평가 기대값 —————————————————————————
    # trend 방향: {"Creatinine": "WORSENING", "Hemoglobin": "WORSENING"}
    expected_trend_directions: dict[str, str] = field(default_factory=dict)

    # 기대 flag 목록
    expected_flags: list[ExpectedFlag] = field(default_factory=list)

    # checklist에 포함되어야 할 키워드 (대소문자 무시)
    expected_checklist_keywords: list[str] = field(default_factory=list)

    # flag가 생성되면 안 되는 lab label 목록
    expected_absent_flag_labels: list[str] = field(default_factory=list)

    # 2차 평가 —————————————————————————
    # LLM judge 최소 합격 점수 (25점 만점, 기본 18점)
    min_judge_total: float = 18.0

    # 3차 평가 (고급 분석) ——————————————
    # 예상 환자 상태: "STABLE" | "DETERIORATING" | "CRITICAL" | "RECOVERING"
    expected_patient_state: Optional[str] = None
    # 이상값으로 탐지되어야 할 lab label 목록 (예: ["Creatinine"])
    expected_anomalous_labs: list[str] = field(default_factory=list)
    # 다변량 패널 중 NORMAL이 아닌 것이어야 할 패널 목록 (예: ["RENAL", "ANEMIA"])
    expected_multivariate_panels: list[str] = field(default_factory=list)
