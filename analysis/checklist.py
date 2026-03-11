"""
Must-check 체크리스트 생성.

Rule-based로 아이템 생성 → LLM이 WHY 이유 문장 보강.
안전 관련 아이템은 규칙으로 확실히 잡고, LLM에 의존하지 않음.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from analysis.flags import ChangeFlag
from analysis.trend import TrendResult
from data.loader import PatientRecord

logger = logging.getLogger(__name__)


@dataclass
class ChecklistItem:
    item: str              # 체크해야 할 액션
    reason: str            # WHY (처음엔 rule 기반, 이후 LLM 보강)
    urgency: str           # "URGENT" | "ROUTINE" | "OPTIONAL"
    source: str            # "rule" | "llm" | "flag"


# ──────────────────────────────────────────────
# Rule-based 체크리스트 생성
# ──────────────────────────────────────────────

def generate_checklist(
    record: PatientRecord,
    trends: dict[int, TrendResult],
    flags: list[ChangeFlag],
) -> list[ChecklistItem]:
    """Rule-based 체크리스트 생성. LLM 보강 전 단계."""
    items: list[ChecklistItem] = []

    # 1. Flag 기반 아이템
    for flag in flags:
        if flag.severity == "HIGH":
            items.extend(_items_from_high_flag(flag))

    # 2. 약물 안전 규칙
    items.extend(_medication_safety_rules(record, trends))

    # 3. 데이터 갭 체크
    items.extend(_data_gap_items(trends))

    # 4. 목적별 추가 규칙
    items.extend(_purpose_specific_rules(record, trends))

    # 중복 제거
    seen = set()
    deduped = []
    for item in items:
        key = item.item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    # urgency 순 정렬
    order = {"URGENT": 0, "ROUTINE": 1, "OPTIONAL": 2}
    deduped.sort(key=lambda x: order.get(x.urgency, 3))
    return deduped


def _items_from_high_flag(flag: ChangeFlag) -> list[ChecklistItem]:
    items = []

    # Creatinine 급증 → AKI 평가
    if flag.item_id == 50912:
        items.append(ChecklistItem(
            item="Nephrology 의뢰 또는 AKI 원인 평가",
            reason=f"Creatinine {flag.current_value:.2f} mg/dL ({flag.message})",
            urgency="URGENT",
            source="rule",
        ))
        items.append(ChecklistItem(
            item="신독성 약물 검토 (NSAIDs, contrast, aminoglycosides)",
            reason="AKI 진행 시 신독성 약물 중단 고려",
            urgency="URGENT",
            source="rule",
        ))

    # INR 초치료역
    if flag.item_id == 51237 and flag.current_value and flag.current_value > 3.5:
        items.append(ChecklistItem(
            item="항응고제 용량 조정 검토",
            reason=f"INR {flag.current_value:.1f} — 치료역(2-3) 초과",
            urgency="URGENT",
            source="rule",
        ))

    # BNP 급증
    if flag.item_id == 50963:
        items.append(ChecklistItem(
            item="심부전 악화 여부 임상 평가 (호흡음, 부종, 산소포화도)",
            reason=f"BNP {flag.message}",
            urgency="URGENT",
            source="rule",
        ))

    # Troponin 상승
    if flag.item_id == 52546:
        items.append(ChecklistItem(
            item="12-lead EKG 시행 및 Cardiology 협진 고려",
            reason=f"Troponin T {flag.message}",
            urgency="URGENT",
            source="rule",
        ))

    # Lactate 상승
    if flag.item_id == 50813:
        items.append(ChecklistItem(
            item="Lactate 재측정 및 패혈증 번들 확인",
            reason=f"Lactate {flag.message} — 조직 관류 저하 가능성",
            urgency="URGENT",
            source="rule",
        ))

    return items


def _medication_safety_rules(
    record: PatientRecord,
    trends: dict[int, TrendResult],
) -> list[ChecklistItem]:
    """약물-신기능/간기능 안전 규칙."""
    items = []
    cr_trend = trends.get(50912)
    cr_val = cr_trend.last_value if cr_trend else None

    active_drugs = {p.drug.lower() for p in record.active_prescriptions}

    # Metformin 금기: Cr > 1.5 (남성) or > 1.4 (여성)
    threshold = 1.4 if record.gender == "F" else 1.5
    if cr_val and cr_val > threshold:
        if any("metformin" in d for d in active_drugs):
            items.append(ChecklistItem(
                item="Metformin 중단 또는 용량 감량 검토",
                reason=f"Creatinine {cr_val:.2f} mg/dL — Metformin 신기능 금기 기준 초과",
                urgency="URGENT",
                source="rule",
            ))

    # NSAID 금기: AKI / CKD
    tags_str = " ".join(
        d.icd_code[:3] for d in record.diagnoses
    )
    has_ckd_or_aki = any(code in tags_str for code in ("N18", "N17"))
    if has_ckd_or_aki:
        if any(drug in d for d in active_drugs for drug in ("ibuprofen", "naproxen", "ketorolac", "indomethacin")):
            items.append(ChecklistItem(
                item="NSAID 사용 중단 검토 (CKD/AKI 금기)",
                reason="신기능 저하 환자에서 NSAID는 신독성 위험",
                urgency="URGENT",
                source="rule",
            ))

    return items


def _data_gap_items(trends: dict[int, TrendResult]) -> list[ChecklistItem]:
    """중요 lab인데 최근 데이터가 없는 경우 체크리스트 추가."""
    items = []
    # HbA1c gap — DM 환자에서 6개월 이상 없으면 재측정 권고
    hba1c = trends.get(50852)
    if hba1c and not hba1c.has_recent_data:
        items.append(ChecklistItem(
            item="HbA1c 측정 (최근 데이터 없음)",
            reason="당뇨 조절 상태 확인을 위해 HbA1c 재측정 고려",
            urgency="ROUTINE",
            source="rule",
        ))
    return items


def _purpose_specific_rules(
    record: PatientRecord,
    trends: dict[int, TrendResult],
) -> list[ChecklistItem]:
    items = []
    purpose = record.purpose

    if purpose == "preop":
        # INR 확인 (수술 전 필수)
        inr = trends.get(51237)
        if inr and inr.last_value and inr.last_value > 1.5:
            items.append(ChecklistItem(
                item="수술 전 항응고제 bridge 계획 수립",
                reason=f"INR {inr.last_value:.1f} — 수술 전 항응고 관리 필요",
                urgency="URGENT",
                source="rule",
            ))

        # Cr 확인 (contrast / 마취제 용량)
        cr = trends.get(50912)
        if cr and cr.last_value and cr.last_value > 1.5:
            items.append(ChecklistItem(
                item="마취과 사전 협의 — 신기능 저하",
                reason=f"Creatinine {cr.last_value:.2f} mg/dL — 마취제 용량 및 수액 관리 조정",
                urgency="ROUTINE",
                source="rule",
            ))

    elif purpose == "referral":
        # 의뢰 목적 명시
        items.append(ChecklistItem(
            item="의뢰서에 주요 lab 트렌드 첨부",
            reason="수신 전문의가 임상 추이를 파악할 수 있도록 시계열 데이터 동봉",
            urgency="ROUTINE",
            source="rule",
        ))

    return items
