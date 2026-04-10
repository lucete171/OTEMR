"""
Change flag 감지.
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
    message: str
    previous_value: Optional[float]
    current_value: Optional[float]
    unit: str
    ref_flag: str
    direction: str
    # ── 추가 ──────────────────────────────
    visibility: str = "ON_ALERT"   # "ALWAYS" | "ON_ALERT" | "ON_DEMAND"
    trigger: str = "TREND"         # "THRESHOLD" | "TREND" | "CONTEXT"
    trend_message: str = ""        # Layer 2용 설명 ("3개월 연속 상승 중")


FLAG_RULES: dict[int, dict] = {
    50912: {"delta_pct": 50, "abs_high": 3.0,  "label": "Creatinine"},
    52546: {"delta_pct": 50, "abs_high": 3.0,  "label": "Creatinine"},
    51222: {"delta_pct": 20, "abs_low": 7.0,   "label": "Hemoglobin"},
    51237: {"delta_pct": 30, "abs_high": 3.5,  "label": "INR"},
    51675: {"delta_pct": 30, "abs_high": 3.5,  "label": "INR"},
    50963: {"delta_pct": 50, "abs_high": 900,  "label": "BNP"},
    50813: {"delta_pct": 0,  "abs_high": 2.0,  "label": "Lactate"},
    50931: {"delta_pct": 0,  "abs_high": 400,  "label": "Glucose"},
    50971: {"delta_pct": 0,  "abs_high": 6.0,  "abs_low": 3.0, "label": "Potassium"},
    52610: {"delta_pct": 0,  "abs_high": 6.0,  "abs_low": 3.0, "label": "Potassium"},
    51265: {"delta_pct": 30, "abs_low": 50.0,  "abs_high": 600.0, "label": "Platelet Count"},
    53189: {"delta_pct": 30, "abs_low": 50.0,  "abs_high": 600.0, "label": "Platelet Count"},
    51301: {"delta_pct": 100,"abs_high": 20.0, "label": "WBC"},
    50820: {"delta_pct": 0,  "abs_low": 7.35,  "abs_high": 7.45, "label": "pH"},
    50802: {"delta_pct": 0,  "abs_low": -2.0,  "abs_high": 2.0,  "label": "Base Excess"},
}


def detect_flags(trends: dict[int, TrendResult]) -> list[ChangeFlag]:
    flags: list[ChangeFlag] = []

    for item_id, trend in trends.items():
        if not trend.has_recent_data:
            continue

        rule = FLAG_RULES.get(item_id, {})
        severity = _evaluate_severity(trend, rule)

        if severity is None:
            continue

        # ── 레이어 분류 ───────────────────────────────
        visibility, trigger, trend_message = _classify_layer(trend, rule)

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
            visibility=visibility,
            trigger=trigger,
            trend_message=trend_message,
        ))

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    flags.sort(key=lambda f: order.get(f.severity, 3))
    return flags


def _classify_layer(
    trend: TrendResult,
    rule: dict,
) -> tuple[str, str, str]:
    """
    레이어 분류 로직.

    Layer 1 (ALWAYS / THRESHOLD):
        → 현재값이 절대 임계값 초과 (정상범위 이탈)
        → 의사가 마지막 기록에서 바로 확인하는 것

    Layer 2 (ON_ALERT / TREND):
        → 현재값은 정상인데 방향이 나쁜 것
        → 의사가 놓치기 쉬운 것 — 우리 에이전트 핵심 가치

    Layer 3 (ON_DEMAND / CONTEXT):
        → 방향도 정상, 변화폭도 작음
        → 히스토리 맥락용
    """
    val = trend.last_value
    is_normal_now = trend.ref_flag == "NORMAL"
    is_worsening = trend.direction == "WORSENING"

    # Layer 1 — 지금 당장 이상한 것
    if "abs_high" in rule and val is not None and val > rule["abs_high"]:
        return "ALWAYS", "THRESHOLD", ""
    if "abs_low" in rule and val is not None and val < rule["abs_low"]:
        return "ALWAYS", "THRESHOLD", ""
    if trend.ref_flag in ("HIGH", "LOW"):
        return "ALWAYS", "THRESHOLD", ""

    # Layer 2 — 지금은 정상인데 방향이 나쁜 것
    if is_normal_now and is_worsening:
        msg = _build_trend_message(trend)
        return "ON_ALERT", "TREND", msg

    # Layer 3 — 히스토리 맥락
    return "ON_DEMAND", "CONTEXT", ""


def _build_trend_message(trend: TrendResult) -> str:
    """Layer 2용 트렌드 설명 문장."""
    if trend.slope_pct_per_week is not None and abs(trend.slope_pct_per_week) >= 1:
        direction_str = "상승" if trend.slope_pct_per_week > 0 else "하강"
        return (
            f"{trend.label} 현재 정상범위이나 "
            f"주당 {abs(trend.slope_pct_per_week):.1f}% {direction_str} 추세 "
            f"(최근 {trend.n_points}회 측정 기준)"
        )
    if trend.delta_pct is not None and abs(trend.delta_pct) >= 10:
        sign = "+" if trend.delta_pct > 0 else ""
        return (
            f"{trend.label} 현재 정상범위이나 "
            f"직전 대비 {sign}{trend.delta_pct:.1f}% 변화"
        )
    return f"{trend.label} {trend.direction} 추세"


def _evaluate_severity(trend: TrendResult, rule: dict) -> Optional[str]:
    val = trend.last_value
    delta_pct = trend.delta_pct

    if "abs_high" in rule and val is not None and val > rule["abs_high"]:
        return "HIGH"
    if "abs_low" in rule and val is not None and val < rule["abs_low"]:
        return "HIGH"

    if "delta_pct" in rule and delta_pct is not None:
        if abs(delta_pct) >= rule["delta_pct"] and rule["delta_pct"] > 0:
            return "HIGH" if abs(delta_pct) >= rule["delta_pct"] * 1.5 else "MEDIUM"

    if trend.ref_flag in ("HIGH", "LOW"):
        return "HIGH"

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