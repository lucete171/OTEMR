"""
고급 임상 분석 레이어 오케스트레이터.

기존 파이프라인:
  compute_trends() → detect_flags() → generate_checklist()

이 모듈은 그 이후에 호출:
  run_advanced_analysis(trends, flags) → ClinicalAnalysisOutput

내부 흐름:
  1. 각 TrendResult의 _raw_values에서 IQR 제거 (cleaned 값 생성)
  2. EWMA / 변화점 탐지 / 이상 감지 (cleaned 값 사용)
  3. 다변량 패널 분석
  4. 환자 상태 머신
  5. ClinicalAnalysisOutput 조립
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from analysis.ewma import (
    AnomalyResult,
    ChangePointResult,
    EWMAResult,
    compute_ewma,
    detect_anomaly,
    detect_change_point,
)
from analysis.flags import ChangeFlag
from analysis.multivariate import run_multivariate_analysis
from analysis.state_machine import determine_patient_state
from analysis.trend import TrendResult, remove_outliers_iqr
from models.clinical_output import (
    ClinicalAnalysisOutput,
    TrendSummary,
)

logger = logging.getLogger(__name__)


def run_advanced_analysis(
    subject_id: int,
    trends: dict[int, TrendResult],
    flags: list[ChangeFlag],
    ewma_alpha: float = 0.3,
    z_threshold: float = 2.5,
    previous_state: Optional[str] = None,
) -> ClinicalAnalysisOutput:
    """
    고급 임상 분석 실행.

    기존 compute_trends() / detect_flags() 결과를 받아
    EWMA / 변화점 / 이상감지 / 다변량 패널 / 상태 머신을 순서대로 실행.

    Args:
        subject_id: 환자 ID (PatientRecord.subject_id)
        trends: compute_trends() 반환값
        flags: detect_flags() 반환값
        ewma_alpha: EWMA 기본 알파값 (기본 0.3)
        z_threshold: 이상감지 z-score 임계값 (기본 2.5)
        previous_state: 이전 판정 상태 (세션 지속 시 전달, 없으면 None)

    Returns:
        ClinicalAnalysisOutput
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []
    trend_summaries: list[TrendSummary] = []

    # ── 1. 단변량 고급 분석 (TrendResult별) ─────────────────
    for item_id, trend in trends.items():
        if not trend.has_recent_data:
            continue

        cleaned_values, cleaned_times = _get_cleaned_series(trend)

        if not cleaned_values:
            warnings.append(f"{trend.label}: IQR 제거 후 유효 데이터 없음")
            continue

        # EWMA
        ewma_res: EWMAResult = compute_ewma(
            cleaned_values=cleaned_values,
            times_days=cleaned_times,
            item_id=item_id,
            alpha=ewma_alpha,
        )

        # 변화점 탐지
        cp_res: ChangePointResult = detect_change_point(
            cleaned_values=cleaned_values,
            times_days=cleaned_times,
            item_id=item_id,
        )

        # 이상 감지
        anom_res: AnomalyResult = detect_anomaly(
            cleaned_values=cleaned_values,
            item_id=item_id,
            z_threshold=z_threshold,
        )

        summary = TrendSummary(
            itemid=item_id,
            label=trend.label,
            last_value=trend.last_value,
            direction=trend.direction,
            # EWMA
            ewma_value=ewma_res.ewma_last,
            ewma_direction=ewma_res.ewma_direction,
            ewma_slope=ewma_res.ewma_slope,
            ewma_interpretation=ewma_res.interpretation,
            ewma_confidence=ewma_res.confidence,
            # 이상 감지
            anomaly_score=anom_res.last_z_score,
            is_anomaly=anom_res.is_anomaly,
            anomaly_interpretation=anom_res.interpretation,
            # 변화점
            change_point_detected=cp_res.detected,
            change_point_index=cp_res.change_index,
            change_point_confidence=cp_res.confidence,
            change_point_interpretation=cp_res.interpretation,
        )
        trend_summaries.append(summary)

    # ── 2. 다변량 패널 분석 ──────────────────────────────────
    multivariate_signals = run_multivariate_analysis(trends)

    # ── 3. 환자 상태 머신 ────────────────────────────────────
    patient_state, score, transition = determine_patient_state(
        trends=trends,
        flags=flags,
        multivariate_signals=multivariate_signals,
        previous_state=previous_state,
    )

    # state_confidence: score를 0~1 범위로 정규화 (score 6 이상 = 1.0)
    state_confidence = min(score / 6.0, 1.0) if score < 99 else 1.0

    # ── 4. 임상 추론 요약 (LLM 컨텍스트 보강용) ─────────────
    explanations = _build_explanations(
        trend_summaries, multivariate_signals, patient_state, score
    )

    # ── 5. 플래그 통계 ───────────────────────────────────────
    high_count = sum(1 for f in flags if f.severity == "HIGH")

    return ClinicalAnalysisOutput(
        subject_id=subject_id,
        analysis_timestamp=timestamp,
        patient_state=patient_state,
        state_confidence=state_confidence,
        state_transition=transition,
        trend_summaries=trend_summaries,
        multivariate_signals=multivariate_signals,
        change_flags_count=len(flags),
        high_severity_flag_count=high_count,
        explanations=explanations,
        warnings=warnings,
        deterioration_score=score,
    )


# ──────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────

def _get_cleaned_series(
    trend: TrendResult,
) -> tuple[list[float], list[float]]:
    """
    TrendResult._raw_values에서 IQR 제거 후 cleaned 시계열 반환.

    Returns:
        (cleaned_values, times_days) — NaN 제거 후 유효 포인트만
    """
    raw = trend._raw_values
    times = trend._raw_times_days

    if not raw:
        return [], []

    raw_arr = np.array(raw, dtype=float)
    cleaned_arr = remove_outliers_iqr(raw_arr)

    # NaN(이상치) 제거, times와 동기화 유지
    valid_pairs = [
        (float(v), float(t))
        for v, t in zip(cleaned_arr, times)
        if not np.isnan(v)
    ]

    if not valid_pairs:
        return [], []

    clean_vals, clean_times = zip(*valid_pairs)
    return list(clean_vals), list(clean_times)


def _build_explanations(
    trend_summaries: list[TrendSummary],
    multivariate_signals,
    patient_state: str,
    score: int,
) -> list[str]:
    """
    LLM 컨텍스트에 삽입할 임상 추론 요약 문장 생성.
    """
    lines: list[str] = []

    # 환자 상태
    state_kr = {
        "STABLE": "안정",
        "DETERIORATING": "악화 중",
        "CRITICAL": "위중",
        "RECOVERING": "회복 중",
    }
    lines.append(
        f"[고급 분석] 환자 상태: {state_kr.get(patient_state, patient_state)} "
        f"(deterioration_score={score})"
    )

    # 이상값 탐지된 lab
    anomalies = [s for s in trend_summaries if s.is_anomaly]
    if anomalies:
        labels = ", ".join(s.label for s in anomalies)
        lines.append(f"통계적 이상값 감지: {labels}")

    # 변화점 탐지된 lab
    changepoints = [s for s in trend_summaries if s.change_point_detected]
    if changepoints:
        labels = ", ".join(
            f"{s.label} ({s.change_point_interpretation})" for s in changepoints
        )
        lines.append(f"급격한 변화 시점 감지: {labels}")

    # 다변량 신호 (NORMAL 제외)
    for sig in multivariate_signals:
        if sig.severity != "NORMAL":
            lines.append(f"{sig.panel} 패널: {sig.interpretation}")

    return lines
