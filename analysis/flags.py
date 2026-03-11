"""
Change flag 감지.

TrendResult 목록을 받아 임상적으로 의미 있는 변화를 ChangeFlag로 생성.
Rule-based (안전 중심) — LLM은 이유 문장 생성에만 사용.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from analysis.trend import TrendResult


@dataclass
class ChangeFlag:
    item_id: int
    label: str
    severity: str          # "HIGH" | "MEDIUM" | "LOW"
    message: str           # 한 줄 설명 (예: "Creatinine +53% vs previous")
    previous_value: Optional[float]
    current_value: Optional[float]
    unit: str
    ref_flag: str          # 현재 정상범위 상태
    direction: str


# ──────────────────────────────────────────────
# 임계값 규칙
# ──────────────────────────────────────────────

# lab별 HIGH severity 기준 (절대값 or 퍼센트)
# (delta_pct_threshold, absolute_value_threshold_for_HIGH)
FLAG_RULES: dict[int, dict] = {
    50912: {"delta_pct": 50, "abs_high": 3.0,   "label": "Creatinine"},   # AKI criteria
    51222: {"delta_pct": 20, "abs_low": 7.0,    "label": "Hemoglobin"},   # Severe anemia
    51237: {"delta_pct": 30, "abs_high": 3.5,   "label": "INR"},          # Supratherapeutic
    50963: {"delta_pct": 50, "abs_high": 900,   "label": "BNP"},
    52546: {"delta_pct": 50, "abs_high": 0.05,  "label": "Troponin T"},
    50813: {"delta_pct": 0,  "abs_high": 2.0,   "label": "Lactate"},      # Elevated lactate
    50931: {"delta_pct": 0,  "abs_high": 400,   "label": "Glucose"},      # Severe hyperglycemia
    50971: {"delta_pct": 0,  "abs_high": 6.0,   "label": "Potassium"},    # Hyperkalemia
    50971: {"delta_pct": 0,  "abs_low": 2.8,    "label": "Potassium"},    # Hypokalemia
    51301: {"delta_pct": 100,"abs_high": 20.0,  "label": "WBC"},          # Leukocytosis
}


def detect_flags(trends: dict[int, TrendResult]) -> list[ChangeFlag]:
    """
    TrendResult dict에서 ChangeFlag 목록 생성.
    severity: HIGH > MEDIUM > LOW
    """
    flags: list[ChangeFlag] = []

    for item_id, trend in trends.items():
        if not trend.has_recent_data:
            continue

        rule = FLAG_RULES.get(item_id, {})
        severity = _evaluate_severity(trend, rule)

        if severity is None:
            continue

        msg = _build_message(trend)
        flags.append(ChangeFlag(
            item_id=item_id,
            label=trend.label,
            severity=severity,
            message=msg,
            previous_value=trend.previous_value,
            current_value=trend.last_value,
            unit=trend.unit,
            ref_flag=trend.ref_flag,
            direction=trend.direction,
        ))

    # severity 순으로 정렬 (HIGH → MEDIUM → LOW)
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    flags.sort(key=lambda f: order.get(f.severity, 3))
    return flags


def _evaluate_severity(trend: TrendResult, rule: dict) -> Optional[str]:
    val = trend.last_value
    delta_pct = trend.delta_pct

    # HIGH: 절대값 임계값 초과
    if "abs_high" in rule and val is not None and val > rule["abs_high"]:
        return "HIGH"
    if "abs_low" in rule and val is not None and val < rule["abs_low"]:
        return "HIGH"

    # HIGH: 큰 delta%
    if "delta_pct" in rule and delta_pct is not None:
        if abs(delta_pct) >= rule["delta_pct"] and rule["delta_pct"] > 0:
            return "HIGH" if abs(delta_pct) >= rule["delta_pct"] * 1.5 else "MEDIUM"

    # MEDIUM: WORSENING + 참조 범위 이탈
    if trend.direction == "WORSENING" and trend.ref_flag in ("HIGH", "LOW"):
        return "MEDIUM"

    # LOW: WORSENING이지만 참조 범위 내
    if trend.direction == "WORSENING":
        return "LOW"

    return None


def _build_message(trend: TrendResult) -> str:
    val_str = f"{trend.last_value:.2f} {trend.unit}".strip()

    if trend.delta_pct is not None and abs(trend.delta_pct) >= 5:
        sign = "+" if trend.delta_pct > 0 else ""
        delta_str = f"{sign}{trend.delta_pct:.1f}% vs previous"
        return f"{trend.label} {val_str} [{trend.ref_flag}] — {delta_str}"

    if trend.direction not in ("STABLE", "UNKNOWN"):
        return f"{trend.label} {val_str} [{trend.ref_flag}] — {trend.direction}"

    return f"{trend.label} {val_str} [{trend.ref_flag}]"
