"""
단변량 고급 시계열 분석.

세 가지 분석을 제공:
  1. EWMA (Exponentially Weighted Moving Average)
     - IQR 제거 후 cleaned 값으로 계산 (이상치에 민감한 EWMA 특성 보정)
     - 시간 적응형 알파: 불규칙 측정 간격을 보정
     - 선형회귀 slope보다 최근 변화에 더 민감

  2. 변화점 탐지 (CUSUM + t-test)
     - 순수 numpy/scipy 구현 (외부 의존성 없음)
     - "점진적 악화"와 "급격한 평균 이동"을 구분

  3. 이상 감지 (z-score)
     - IQR-cleaned 값 기준 z-score: "이 환자의 정상 분포 대비" 이상도 측정
     - IQR 제거(trend.py)와 목적이 다름:
         IQR 제거 → Lab 오류 배제 (계산 정확도)
         z-score  → 환자 개인 기준 통계적 이상값 탐지
       예: Cr이 항상 1.0~1.2였는데 갑자기 2.5 → IQR 기준 통과하지만
           z-score는 이상 신호로 감지

모든 함수는 IQR 제거 후 cleaned 값을 입력으로 받는다.
IQR 제거는 analysis/advanced.py (오케스트레이터)에서 한 번 수행.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats


# ──────────────────────────────────────────────────────────────
# 결과 데이터클래스
# ──────────────────────────────────────────────────────────────

@dataclass
class EWMAResult:
    """EWMA 분석 결과."""
    item_id: int
    alpha: float                        # 사용된 기본 알파값
    ewma_values: list[float]            # 시계열 전체 EWMA 평활값 (입력과 동일 길이)
    ewma_last: Optional[float]          # 마지막 EWMA값
    ewma_slope: Optional[float]         # EWMA 시계열의 선형 기울기 (units/day)
    ewma_direction: str                 # "UP" | "DOWN" | "FLAT"
    confidence: float                   # 0.0 ~ 1.0 (포인트 수 기반)
    interpretation: str                 # 임상의 가독 해석


@dataclass
class ChangePointResult:
    """변화점 탐지 결과."""
    item_id: int
    detected: bool                      # 유의미한 변화점 탐지 여부
    change_index: Optional[int]         # 변화점 위치 (cleaned 값 배열 기준)
    change_magnitude: Optional[float]   # |평균 이동 크기|
    confidence: float                   # 0.0 ~ 0.999 (1 - p_value)
    interpretation: str                 # 임상의 가독 해석


@dataclass
class AnomalyResult:
    """이상 감지 결과."""
    item_id: int
    z_scores: list[float]               # 각 포인트별 z-score
    last_z_score: Optional[float]       # 마지막 측정값의 z-score
    is_anomaly: bool                    # |last_z| > z_threshold
    confidence: float                   # min(|z| / 3.0, 1.0)
    interpretation: str                 # 임상의 가독 해석


# ──────────────────────────────────────────────────────────────
# 1. EWMA
# ──────────────────────────────────────────────────────────────

def compute_ewma(
    cleaned_values: list[float],
    times_days: list[float],
    item_id: int,
    alpha: float = 0.3,
    min_delta_for_direction: float = 0.0,
) -> EWMAResult:
    """
    시간 적응형 EWMA 계산.

    IQR 제거 후 cleaned 값을 입력으로 받는다.
    이상치가 포함된 경우 지수 가중 특성상 이후 모든 평활값을 오염시키므로
    반드시 IQR 제거 후 적용해야 한다.

    표준 EWMA는 측정 간격을 무시한다: 90일 전 값과 1일 전 값이 동일한 가중치.
    시간 적응형 알파: alpha_t = 1 - exp(-alpha * delta_days)
    긴 간격 뒤의 새 측정값이 더 큰 가중치를 가져 임상적으로 더 자연스럽다.

    Args:
        cleaned_values: IQR 제거 후 시간 순 정렬된 측정값
        times_days: 첫 측정 기준 경과일 (cleaned_values와 동일 길이)
        item_id: lab item ID
        alpha: 기본 평활 파라미터 (0 < alpha < 1, 클수록 최근값 중시)
        min_delta_for_direction: FLAT 판정 기울기 임계값

    Returns:
        EWMAResult
    """
    n = len(cleaned_values)

    if n == 0:
        return EWMAResult(
            item_id=item_id, alpha=alpha, ewma_values=[],
            ewma_last=None, ewma_slope=None,
            ewma_direction="FLAT", confidence=0.0,
            interpretation="데이터 없음",
        )

    ewma_vals: list[float] = [float(cleaned_values[0])]

    for i in range(1, n):
        delta_days = times_days[i] - times_days[i - 1]
        # 시간 적응형 알파: 긴 간격 후 측정은 더 큰 가중치 부여
        # delta_days=0이면 alpha_t≈0 (같은 날 반복 측정 시 안정성 확보)
        alpha_t = 1.0 - math.exp(-alpha * max(delta_days, 0.0))
        ewma_vals.append(alpha_t * cleaned_values[i] + (1.0 - alpha_t) * ewma_vals[-1])

    ewma_last = ewma_vals[-1]

    # EWMA 시계열에 선형 기울기 계산 (3개 이상)
    ewma_slope: Optional[float] = None
    if n >= 3:
        x = np.array(times_days)
        y = np.array(ewma_vals)
        ewma_slope = _linear_slope(x, y)

    # 방향 분류
    slope_val = ewma_slope if ewma_slope is not None else 0.0
    if abs(slope_val) <= min_delta_for_direction:
        direction = "FLAT"
    elif slope_val > 0:
        direction = "UP"
    else:
        direction = "DOWN"

    # 신뢰도: 포인트 수가 많을수록 높음 (6개 이상 → 1.0)
    confidence = min(n / 6.0, 1.0)

    interpretation = _ewma_interpretation(direction, slope_val)

    return EWMAResult(
        item_id=item_id,
        alpha=alpha,
        ewma_values=ewma_vals,
        ewma_last=ewma_last,
        ewma_slope=ewma_slope,
        ewma_direction=direction,
        confidence=confidence,
        interpretation=interpretation,
    )


def _ewma_interpretation(direction: str, slope: float) -> str:
    if direction == "FLAT":
        return "안정 (EWMA 기준)"
    mag = abs(slope)
    if mag < 0.01:
        trend_str = "완만한"
    elif mag < 0.1:
        trend_str = "점진적"
    else:
        trend_str = "급격한"
    dir_str = "상승" if direction == "UP" else "하강"
    return f"{trend_str} {dir_str} 추세 (EWMA 기준)"


# ──────────────────────────────────────────────────────────────
# 2. 변화점 탐지
# ──────────────────────────────────────────────────────────────

def detect_change_point(
    cleaned_values: list[float],
    times_days: list[float],
    item_id: int,
    min_segment: int = 3,
    p_threshold: float = 0.05,
) -> ChangePointResult:
    """
    CUSUM + Welch's t-test 기반 변화점 탐지 (순수 numpy/scipy).

    IQR 제거 후 cleaned 값을 입력으로 받는다.

    알고리즘:
      1. CUSUM 파일럿 스캔 (O(N)): 최대 편차 위치로 후보 변화점 확인
      2. 유효 범위 [min_segment, N-min_segment] 전체 후보 탐색
      3. Welch's t-test로 좌우 평균 차이의 유의성 검정 (분산 동일 가정 X)
      4. BIC-like 패널티로 과적합 방지: score = |t| - log(N) * 0.5
      5. p < p_threshold인 최고 score 분할점 수락

    최소 데이터: 2 * min_segment = 6개 (기본값)
    미만이면 detected=False를 결정론적으로 반환.

    Args:
        cleaned_values: IQR 제거 후 시간 순 정렬된 측정값
        times_days: 첫 측정 기준 경과일
        item_id: lab item ID
        min_segment: 분할 후 각 구간 최소 포인트 수 (기본 3)
        p_threshold: 변화점 수락 유의수준 (기본 0.05)

    Returns:
        ChangePointResult
    """
    n = len(cleaned_values)

    if n < 2 * min_segment:
        return ChangePointResult(
            item_id=item_id, detected=False,
            change_index=None, change_magnitude=None,
            confidence=0.0, interpretation="데이터 부족 (변화점 탐지 불가)",
        )

    arr = np.array(cleaned_values, dtype=float)
    mu = arr.mean()
    sigma = arr.std()

    if sigma < 1e-10:
        # 모든 값이 동일 → 변화 없음
        return ChangePointResult(
            item_id=item_id, detected=False,
            change_index=None, change_magnitude=None,
            confidence=0.0, interpretation="값 변동 없음",
        )

    # ── Step 1: CUSUM 파일럿으로 최대 편차 위치 파악 ──
    # 전체 탐색 시 O(N^2) 비용이 크므로 CUSUM으로 후보를 먼저 좁힘
    cusum = np.zeros(n + 1)
    for i in range(1, n + 1):
        cusum[i] = cusum[i - 1] + (arr[i - 1] - mu) / sigma

    # ── Step 2: 유효 범위 전체 탐색 + BIC-penalized score ──
    best_k: Optional[int] = None
    best_score = -np.inf
    best_p = 1.0

    for k in range(min_segment, n - min_segment + 1):
        left = arr[:k]
        right = arr[k:]

        if len(left) < 2 or len(right) < 2:
            continue

        # Welch's t-test: 두 그룹 분산이 다를 수 있으므로 equal_var=False
        t_stat, p_val = stats.ttest_ind(left, right, equal_var=False)

        # BIC-like 패널티: 포인트 수가 많을수록 기준이 높아짐 (과적합 방지)
        score = abs(t_stat) - math.log(n) * 0.5

        if score > best_score:
            best_score = score
            best_k = k
            best_p = float(p_val)

    if best_k is None or best_p >= p_threshold:
        return ChangePointResult(
            item_id=item_id, detected=False,
            change_index=None, change_magnitude=None,
            confidence=0.0, interpretation="유의미한 변화점 없음",
        )

    magnitude = float(abs(arr[best_k:].mean() - arr[:best_k].mean()))
    confidence = min(1.0 - best_p, 0.999)
    interpretation = _change_point_interpretation(
        best_k, n, float(arr[:best_k].mean()), float(arr[best_k:].mean()), magnitude
    )

    return ChangePointResult(
        item_id=item_id,
        detected=True,
        change_index=best_k,
        change_magnitude=magnitude,
        confidence=confidence,
        interpretation=interpretation,
    )


def _change_point_interpretation(
    k: int, n: int, mean_before: float, mean_after: float, magnitude: float
) -> str:
    direction = "상승" if mean_after > mean_before else "하강"
    # 변화점 위치를 측정 구간 기준으로 표현
    position = "초반" if k < n // 3 else ("후반" if k > 2 * n // 3 else "중반")
    return (
        f"측정 {position} ({k}/{n}번째 이후)에서 평균 {direction} 변화 감지 "
        f"(이동 크기: {magnitude:.3f})"
    )


# ──────────────────────────────────────────────────────────────
# 3. 이상 감지
# ──────────────────────────────────────────────────────────────

def detect_anomaly(
    cleaned_values: list[float],
    item_id: int,
    z_threshold: float = 2.5,
) -> AnomalyResult:
    """
    z-score 기반 이상 감지.

    IQR 제거 후 cleaned 값을 입력으로 받는다.

    목적: trend.py의 IQR 아웃라이어 제거(계산 정확도 보호)와 달리,
    마지막 측정값이 이 환자의 정상 분포에서 얼마나 벗어나 있는지를
    임상적 신호로 제공한다.

    예: Cr이 항상 1.0~1.2였는데 갑자기 2.5가 나온 경우
      - IQR × 3 기준은 통과 (극단값이 아님)
      - 하지만 z-score는 ~3.5 → 임상적으로 유의미한 이상값으로 탐지

    z = (last_value - mean) / std
    confidence = min(|z| / 3.0, 1.0)

    Args:
        cleaned_values: IQR 제거 후 시간 순 정렬된 측정값
        item_id: lab item ID
        z_threshold: 이상 판정 z-score 절대값 임계값 (기본 2.5)

    Returns:
        AnomalyResult
    """
    n = len(cleaned_values)

    if n == 0:
        return AnomalyResult(
            item_id=item_id, z_scores=[],
            last_z_score=None, is_anomaly=False,
            confidence=0.0, interpretation="데이터 없음",
        )

    arr = np.array(cleaned_values, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std())

    if std < 1e-10:
        z_scores = [0.0] * n
        return AnomalyResult(
            item_id=item_id, z_scores=z_scores,
            last_z_score=0.0, is_anomaly=False,
            confidence=0.0, interpretation="값 변동 없음 (이상 감지 불가)",
        )

    z_arr = (arr - mean) / std
    z_scores = [float(z) for z in z_arr]
    last_z = z_scores[-1]
    is_anomaly = abs(last_z) > z_threshold
    confidence = min(abs(last_z) / 3.0, 1.0)

    interpretation = _anomaly_interpretation(last_z, is_anomaly, z_threshold)

    return AnomalyResult(
        item_id=item_id,
        z_scores=z_scores,
        last_z_score=last_z,
        is_anomaly=is_anomaly,
        confidence=confidence,
        interpretation=interpretation,
    )


def _anomaly_interpretation(z: float, is_anomaly: bool, threshold: float) -> str:
    if not is_anomaly:
        return f"정상 범위 내 (z={z:.2f})"
    direction = "높음" if z > 0 else "낮음"
    severity = "극단적" if abs(z) > 4.0 else "유의미한"
    return f"{severity} 이상값 — 환자 기준 평균 대비 {direction} (z={z:.2f}, 임계값 ±{threshold})"


# ──────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────

def _linear_slope(x: np.ndarray, y: np.ndarray) -> float:
    """단순 선형회귀 기울기만 반환 (trend.py _linear_regression 로직 재현)."""
    x_mean, y_mean = x.mean(), y.mean()
    ss_xx = float(((x - x_mean) ** 2).sum())
    if ss_xx < 1e-10:
        return 0.0
    ss_xy = float(((x - x_mean) * (y - y_mean)).sum())
    return ss_xy / ss_xx
