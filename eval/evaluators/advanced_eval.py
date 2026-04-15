"""
고급 분석 레이어 평가 훅.

세 가지 평가 함수:
  compare_old_vs_new_trend()  — 기존 direction vs EWMA 방향 불일치 탐지
  detect_missed_critical_cases() — 플래그 없이 CRITICAL 판정된 케이스 탐지
  generate_debug_trace()      — 전체 중간 신호를 포함한 디버그 딕셔너리

EvalCase.expected_patient_state / expected_anomalous_labs /
expected_multivariate_panels와 비교해 자동화 평가도 지원.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from analysis.flags import ChangeFlag
from analysis.trend import TrendResult
from eval.cases.base import EvalCase
from models.clinical_output import ClinicalAnalysisOutput


# ──────────────────────────────────────────────────────────────
# 결과 데이터클래스
# ──────────────────────────────────────────────────────────────

@dataclass
class AdvancedCheckResult:
    """단일 고급 평가 체크 결과."""
    name: str
    passed: bool
    expected: str
    actual: str
    note: str = ""


@dataclass
class AdvancedEvalResult:
    """고급 분석 평가 종합 결과."""
    case_name: str
    state_checks: list[AdvancedCheckResult] = field(default_factory=list)
    anomaly_checks: list[AdvancedCheckResult] = field(default_factory=list)
    multivariate_checks: list[AdvancedCheckResult] = field(default_factory=list)

    @property
    def all_checks(self) -> list[AdvancedCheckResult]:
        return self.state_checks + self.anomaly_checks + self.multivariate_checks

    @property
    def passed(self) -> int:
        return sum(1 for c in self.all_checks if c.passed)

    @property
    def total(self) -> int:
        return len(self.all_checks)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 1.0


# ──────────────────────────────────────────────────────────────
# 공개 평가 함수
# ──────────────────────────────────────────────────────────────

def evaluate_advanced(
    case: EvalCase,
    advanced: ClinicalAnalysisOutput,
) -> AdvancedEvalResult:
    """
    EvalCase의 기대값과 ClinicalAnalysisOutput을 비교해 자동 평가.

    EvalCase에 expected_* 필드가 없으면 해당 체크 skip.

    Args:
        case: 기대값이 포함된 평가 케이스
        advanced: run_advanced_analysis() 반환값

    Returns:
        AdvancedEvalResult
    """
    result = AdvancedEvalResult(case_name=case.name)

    # ── 환자 상태 체크 ──────────────────────────────────────
    if case.expected_patient_state is not None:
        check = AdvancedCheckResult(
            name="patient_state",
            passed=advanced.patient_state == case.expected_patient_state,
            expected=case.expected_patient_state,
            actual=advanced.patient_state,
            note=f"deterioration_score={advanced.deterioration_score}",
        )
        result.state_checks.append(check)

    # ── 이상값 탐지 체크 ────────────────────────────────────
    detected_anomaly_labels = {
        s.label for s in advanced.trend_summaries if s.is_anomaly
    }
    for expected_label in case.expected_anomalous_labs:
        check = AdvancedCheckResult(
            name=f"anomaly_{expected_label}",
            passed=expected_label in detected_anomaly_labels,
            expected=f"{expected_label} is_anomaly=True",
            actual=f"detected={expected_label in detected_anomaly_labels}",
        )
        result.anomaly_checks.append(check)

    # ── 다변량 패널 체크 ────────────────────────────────────
    detected_panels = {
        sig.panel for sig in advanced.multivariate_signals
        if sig.severity != "NORMAL"
    }
    for expected_panel in case.expected_multivariate_panels:
        check = AdvancedCheckResult(
            name=f"multivariate_{expected_panel}",
            passed=expected_panel in detected_panels,
            expected=f"{expected_panel} severity != NORMAL",
            actual=f"detected={expected_panel in detected_panels}",
        )
        result.multivariate_checks.append(check)

    return result


def compare_old_vs_new_trend(
    trends: dict[int, TrendResult],
    advanced: ClinicalAnalysisOutput,
) -> list[dict]:
    """
    기존 선형회귀 기반 direction vs EWMA 기반 방향 비교.

    불일치(disagree) 케이스를 반환하여 두 방법의 차이를 정량화.
    임상적으로는 EWMA 방향이 더 신뢰도 높을 수 있음 (노이즈 강건).

    Returns:
        불일치 케이스 목록. 각 항목:
          {label, linear_direction, ewma_direction, last_value, note}
    """
    disagreements: list[dict] = []
    summary_map = {s.itemid: s for s in advanced.trend_summaries}

    # 방향 매핑: TrendResult.direction → 정규화된 방향
    direction_map = {
        "WORSENING": "BAD",
        "IMPROVING": "GOOD",
        "STABLE": "STABLE",
        "CHANGING": "CHANGING",
        "UNKNOWN": "UNKNOWN",
    }
    # EWMA 방향: UP/DOWN → 악화 방향은 lab_profiles의 worsening_direction에 따라 다름
    # 여기서는 단순히 방향만 비교 (임상 해석은 별도)

    for item_id, trend in trends.items():
        if not trend.has_recent_data:
            continue
        summary = summary_map.get(item_id)
        if summary is None:
            continue

        linear_dir = direction_map.get(trend.direction, "UNKNOWN")
        ewma_dir = summary.ewma_direction  # "UP" | "DOWN" | "FLAT"

        # STABLE ↔ WORSENING 불일치가 가장 임상적으로 유의미
        is_linear_bad = trend.direction == "WORSENING"
        is_ewma_moving = ewma_dir in ("UP", "DOWN")

        if is_linear_bad != is_ewma_moving:
            disagreements.append({
                "label": trend.label,
                "linear_direction": trend.direction,
                "ewma_direction": ewma_dir,
                "last_value": trend.last_value,
                "note": (
                    "EWMA 안정적이나 선형회귀 WORSENING" if is_linear_bad
                    else "EWMA 방향 있으나 선형회귀 STABLE/IMPROVING"
                ),
            })

    return disagreements


def detect_missed_critical_cases(
    flags: list[ChangeFlag],
    advanced: ClinicalAnalysisOutput,
) -> list[str]:
    """
    HIGH 플래그 없이 patient_state == CRITICAL인 케이스 탐지.

    이 케이스들은 기존 rule-based flag 시스템이 놓쳤으나
    고급 분석(다변량 신호, EWMA 이상 등)이 잡아낸 critical 상황.

    Returns:
        임상 경고 메시지 목록
    """
    warnings: list[str] = []

    if advanced.patient_state != "CRITICAL":
        return warnings

    high_flag_labels = [f.label for f in flags if f.severity == "HIGH"]

    if not high_flag_labels:
        # CRITICAL이지만 HIGH 플래그 없음 → 고급 분석만이 감지한 케이스
        reasons = [e for e in advanced.explanations if "CRITICAL" in e or "이상" in e]
        reason_str = "; ".join(reasons[:2]) if reasons else "고급 분석 신호"
        warnings.append(
            f"[주의] 기존 플래그 없이 CRITICAL 판정 — {reason_str} "
            f"(score={advanced.deterioration_score})"
        )
    else:
        # CRITICAL이고 HIGH 플래그도 있지만 플래그가 커버하지 못한 추가 신호가 있는지 확인
        multivariate_severe = [
            sig for sig in advanced.multivariate_signals
            if sig.severity == "SEVERE"
            and not any(item in high_flag_labels for item in sig.contributing_items)
        ]
        for sig in multivariate_severe:
            warnings.append(
                f"[추가 신호] {sig.panel} 패널 SEVERE — 기존 플래그 미포함: "
                f"{sig.interpretation}"
            )

    return warnings


def generate_debug_trace(
    advanced: ClinicalAnalysisOutput,
) -> dict:
    """
    전체 중간 신호와 추론 근거를 포함한 디버그 딕셔너리.

    개발/검증 용도. 임상의에게 "왜 이 판정이 나왔는가"를 설명.

    Returns:
        {
          "patient_state": str,
          "deterioration_score": int,
          "transition": dict | None,
          "anomalies": [{"label", "z_score", "interpretation"}],
          "change_points": [{"label", "index", "confidence", "interpretation"}],
          "multivariate": [{"panel", "severity", "reasoning_trace"}],
          "explanations": list[str],
          "warnings": list[str],
        }
    """
    anomalies = [
        {
            "label": s.label,
            "z_score": round(s.anomaly_score, 3) if s.anomaly_score is not None else None,
            "interpretation": s.anomaly_interpretation,
        }
        for s in advanced.trend_summaries if s.is_anomaly
    ]

    change_points = [
        {
            "label": s.label,
            "index": s.change_point_index,
            "confidence": round(s.change_point_confidence, 3),
            "interpretation": s.change_point_interpretation,
        }
        for s in advanced.trend_summaries if s.change_point_detected
    ]

    multivariate = [
        {
            "panel": sig.panel,
            "severity": sig.severity,
            "interpretation": sig.interpretation,
            "reasoning_trace": sig.reasoning_trace,
        }
        for sig in advanced.multivariate_signals
    ]

    transition_dict = None
    if advanced.state_transition:
        t = advanced.state_transition
        transition_dict = {
            "from": t.from_state,
            "to": t.to_state,
            "reason": t.reason,
            "triggered_by": t.triggered_by,
        }

    return {
        "patient_state": advanced.patient_state,
        "deterioration_score": advanced.deterioration_score,
        "state_confidence": round(advanced.state_confidence, 3),
        "transition": transition_dict,
        "anomalies": anomalies,
        "change_points": change_points,
        "multivariate": multivariate,
        "explanations": advanced.explanations,
        "warnings": advanced.warnings,
        "analysis_version": advanced.analysis_version,
    }
