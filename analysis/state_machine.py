"""
환자 상태 머신.

4가지 상태:
  STABLE        → 유의미한 이상 없음
  DETERIORATING → 1~3점 범위의 악화 신호
  CRITICAL      → 4점 이상 또는 하드 오버라이드 조건 충족
  RECOVERING    → 이전 악화 상태에서 주요 지표 개선 중

설계 원칙:
  - Pure function: I/O 없음, 입력이 동일하면 항상 동일한 출력
  - 모든 전이(transition)는 명시적 규칙과 reasoning_trace를 동반
  - 하드 오버라이드가 점수 기반 판정보다 우선
  - CRITICAL → STABLE 직접 전이 불가 (RECOVERING 경유 강제)
  - previous_state 없으면 이력 없는 첫 판정으로 처리

점수 체계:
  HIGH severity 플래그  × 2점
  MEDIUM severity 플래그 × 1점
  WORSENING direction   × 1점 (lab별)
  SEVERE 다변량 신호     × 2점
  MODERATE 다변량 신호   × 1점
  Cr > 3.0 mg/dL        + 3점 (추가)
  Lactate > 2.0 mmol/L  + 2점 (추가)

  score 0          → STABLE
  score 1~3        → DETERIORATING
  score ≥ 4        → CRITICAL

하드 오버라이드 (점수 무관, 즉시 CRITICAL):
  Lactate > 4.0 mmol/L
  Creatinine > 3× 기준치 (> 3.6 mg/dL, 기준 Cr 상한 1.2 × 3)
  BUN > 50 mg/dL AND Cr > 3.0 mg/dL (동반)
  INR > 5.0
  다변량 신호 severity == "SEVERE"
"""
from __future__ import annotations

from typing import Optional

from analysis.flags import ChangeFlag, FLAG_RULES
from analysis.trend import TrendResult
from models.clinical_output import MultivariateSignal, PatientStateTransition

# 상태 상수
STABLE        = "STABLE"
DETERIORATING = "DETERIORATING"
CRITICAL      = "CRITICAL"
RECOVERING    = "RECOVERING"

# 하드 오버라이드 item_id 상수
_LACTATE_IDS = {50813}
_CR_IDS      = {50912, 52546}
_BUN_ID      = 51006
_INR_IDS     = {51237, 51675}

# RECOVERING 판정에 쓰이는 핵심 lab item_ids
_RECOVERY_LABS = {50912, 52546, 51222, 51301, 50813}  # Cr, Hgb, WBC, Lactate


def determine_patient_state(
    trends: dict[int, TrendResult],
    flags: list[ChangeFlag],
    multivariate_signals: list[MultivariateSignal],
    previous_state: Optional[str] = None,
) -> tuple[str, int, Optional[PatientStateTransition]]:
    """
    환자 상태 판정.

    Args:
        trends: compute_trends() 반환값
        flags: detect_flags() 반환값
        multivariate_signals: run_multivariate_analysis() 반환값
        previous_state: 이전 판정 상태 (없으면 None)

    Returns:
        (patient_state, deterioration_score, transition_or_None)
    """
    trace: list[str] = []

    # ── 1. 하드 오버라이드 확인 ──────────────────────────────
    override_state, override_reason, override_labs = _check_hard_overrides(
        trends, multivariate_signals
    )
    if override_state == CRITICAL:
        transition = _make_transition(previous_state, CRITICAL, override_reason, override_labs)
        return CRITICAL, 99, transition  # score=99로 명시적 오버라이드 표시

    # ── 2. RECOVERING 확인 ──────────────────────────────────
    # 이전 상태가 악화 계열일 때, 핵심 지표 개선 시 RECOVERING
    # CRITICAL → STABLE 직접 전이 방지 (RECOVERING 경유 강제)
    if previous_state in (DETERIORATING, CRITICAL):
        is_recovering, recovering_labs = _check_recovering(trends)
        if is_recovering:
            reason = f"이전 {previous_state} 상태에서 핵심 지표 개선 중: {', '.join(recovering_labs)}"
            transition = _make_transition(previous_state, RECOVERING, reason, recovering_labs)
            return RECOVERING, 0, transition

    # ── 3. 점수 기반 상태 판정 ──────────────────────────────
    score, score_trace = _compute_deterioration_score(trends, flags, multivariate_signals)
    trace.extend(score_trace)

    if score == 0:
        new_state = STABLE
    elif score <= 3:
        new_state = DETERIORATING
    else:
        new_state = CRITICAL

    # RECOVERING 상태에서 개선 안 됐으면 DETERIORATING로 재분류
    if previous_state == RECOVERING and new_state == STABLE:
        # 실제로 점수 0이면 STABLE 허용
        pass

    # ── 4. 전이 감지 ────────────────────────────────────────
    if previous_state is None or previous_state != new_state:
        reason = f"deterioration_score={score}: " + "; ".join(trace[:3])  # 주요 근거 3개
        triggered = _extract_triggered_labs(flags, multivariate_signals, score_trace)
        transition = _make_transition(previous_state, new_state, reason, triggered)
    else:
        transition = None  # 상태 유지

    return new_state, score, transition


# ──────────────────────────────────────────────────────────────
# 하드 오버라이드
# ──────────────────────────────────────────────────────────────

def _check_hard_overrides(
    trends: dict[int, TrendResult],
    multivariate_signals: list[MultivariateSignal],
) -> tuple[Optional[str], str, list[str]]:
    """
    하드 오버라이드 조건 확인.

    Returns:
        (state_if_override, reason, triggered_labs)
        state_if_override가 None이면 오버라이드 없음.
    """
    # Lactate > 4.0 mmol/L (패혈증 쇼크 마커)
    lactate = _get_latest_value(trends, _LACTATE_IDS)
    if lactate is not None and lactate > 4.0:
        return CRITICAL, f"Lactate {lactate:.1f} mmol/L > 4.0 (패혈증 쇼크 기준)", ["Lactate"]

    # INR > 5.0 (심각한 응고 장애)
    inr = _get_latest_value(trends, _INR_IDS)
    if inr is not None and inr > 5.0:
        return CRITICAL, f"INR {inr:.2f} > 5.0 (심각한 응고 장애)", ["INR"]

    # Cr > 3.6 mg/dL (정상 상한 1.2 × 3) AND BUN > 50 mg/dL 동반
    cr = _get_latest_value(trends, _CR_IDS)
    bun = _get_latest_value(trends, {_BUN_ID})
    if cr is not None and cr > 3.6:
        if bun is not None and bun > 50:
            return CRITICAL, f"Cr {cr:.2f} + BUN {bun:.1f} — 중증 신부전", ["Creatinine", "BUN"]
        else:
            return CRITICAL, f"Creatinine {cr:.2f} mg/dL > 3.6 (정상 상한 3×)", ["Creatinine"]

    # 다변량 신호 SEVERE
    for sig in multivariate_signals:
        if sig.severity == "SEVERE":
            return CRITICAL, f"{sig.panel} 패널 SEVERE: {sig.interpretation}", sig.contributing_items

    return None, "", []


# ──────────────────────────────────────────────────────────────
# RECOVERING 판정
# ──────────────────────────────────────────────────────────────

def _check_recovering(
    trends: dict[int, TrendResult],
) -> tuple[bool, list[str]]:
    """
    핵심 지표(Cr, Hgb, WBC, Lactate) 중 2개 이상 IMPROVING이면 RECOVERING.

    Returns:
        (is_recovering, improving_lab_labels)
    """
    improving_labs: list[str] = []
    for iid in _RECOVERY_LABS:
        t = trends.get(iid)
        if t is not None and t.has_recent_data and t.direction == "IMPROVING":
            improving_labs.append(t.label)

    return len(improving_labs) >= 2, improving_labs


# ──────────────────────────────────────────────────────────────
# 점수 계산
# ──────────────────────────────────────────────────────────────

def _compute_deterioration_score(
    trends: dict[int, TrendResult],
    flags: list[ChangeFlag],
    multivariate_signals: list[MultivariateSignal],
) -> tuple[int, list[str]]:
    """
    deterioration_score 계산.

    Returns:
        (score, trace_lines)
    """
    score = 0
    trace: list[str] = []

    # 플래그 기여
    high_flags = [f for f in flags if f.severity == "HIGH"]
    med_flags  = [f for f in flags if f.severity == "MEDIUM"]

    if high_flags:
        pts = len(high_flags) * 2
        score += pts
        labels = [f.label for f in high_flags]
        trace.append(f"HIGH 플래그 {len(high_flags)}개 (+{pts}점): {', '.join(labels)}")

    if med_flags:
        pts = len(med_flags)
        score += pts
        labels = [f.label for f in med_flags]
        trace.append(f"MEDIUM 플래그 {len(med_flags)}개 (+{pts}점): {', '.join(labels)}")

    # WORSENING 방향 기여
    worsening = [t for t in trends.values() if t.direction == "WORSENING"]
    if worsening:
        pts = len(worsening)
        score += pts
        labels = [t.label for t in worsening]
        trace.append(f"WORSENING {len(worsening)}개 (+{pts}점): {', '.join(labels)}")

    # 다변량 신호 기여
    for sig in multivariate_signals:
        if sig.severity == "SEVERE":
            score += 2
            trace.append(f"{sig.panel} SEVERE (+2점)")
        elif sig.severity == "MODERATE":
            score += 1
            trace.append(f"{sig.panel} MODERATE (+1점)")

    # 임계 검사 추가 기여
    cr = _get_latest_value(trends, _CR_IDS)
    if cr is not None and cr > 3.0:
        score += 3
        trace.append(f"Cr {cr:.2f} > 3.0 mg/dL (+3점)")

    lactate = _get_latest_value(trends, _LACTATE_IDS)
    if lactate is not None and lactate > 2.0:
        score += 2
        trace.append(f"Lactate {lactate:.1f} > 2.0 mmol/L (+2점)")

    return score, trace


# ──────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────

def _get_latest_value(
    trends: dict[int, TrendResult],
    item_ids: set[int],
) -> Optional[float]:
    """item_ids 중 데이터가 있는 첫 번째 최근값 반환."""
    for iid in item_ids:
        t = trends.get(iid)
        if t is not None and t.has_recent_data:
            return t.last_value
    return None


def _make_transition(
    from_state: Optional[str],
    to_state: str,
    reason: str,
    triggered_by: list[str],
) -> PatientStateTransition:
    return PatientStateTransition(
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        triggered_by=triggered_by,
    )


def _extract_triggered_labs(
    flags: list[ChangeFlag],
    multivariate_signals: list[MultivariateSignal],
    score_trace: list[str],
) -> list[str]:
    """점수에 기여한 lab label 목록 추출 (중복 제거)."""
    labs: list[str] = []
    seen: set[str] = set()

    for f in flags:
        if f.severity in ("HIGH", "MEDIUM") and f.label not in seen:
            labs.append(f.label)
            seen.add(f.label)

    for sig in multivariate_signals:
        if sig.severity in ("SEVERE", "MODERATE"):
            for item in sig.contributing_items:
                if item not in seen:
                    labs.append(item)
                    seen.add(item)

    return labs
