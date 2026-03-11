"""
시계열 트렌드 분석.

각 lab item에 대해 TrendResult를 계산:
- 최근값, 정상 범위 판정
- 선형회귀 기반 slope + 방향 (IMPROVING / WORSENING / STABLE)
- 직전 2회 간 delta
- 스파크라인용 데이터 포인트 (최대 10개)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from config.lab_profiles import get_lab_meta
from data.loader import LabEvent

logger = logging.getLogger(__name__)


@dataclass
class TrendResult:
    itemid: int
    label: str
    unit: str

    last_value: Optional[float]
    last_date: Optional[datetime]
    ref_range: Optional[tuple[float, float]]
    ref_flag: str  # "HIGH" | "LOW" | "NORMAL" | "UNKNOWN"

    # 시계열 통계 (데이터 3개 이상일 때)
    slope: Optional[float] = None         # 선형회귀 slope (units/day)
    slope_pct_per_week: Optional[float] = None
    r_squared: Optional[float] = None
    direction: str = "UNKNOWN"            # "IMPROVING" | "WORSENING" | "STABLE" | "UNKNOWN"

    # 직전 2회 간 변화
    delta_abs: Optional[float] = None
    delta_pct: Optional[float] = None
    previous_value: Optional[float] = None
    previous_date: Optional[datetime] = None

    # UI용 스파크라인 데이터 (datetime, value) 최대 10개
    sparkline: list[tuple[datetime, float]] = field(default_factory=list)

    # 원본 포인트 수
    n_points: int = 0

    @property
    def has_recent_data(self) -> bool:
        """최근값이 존재하는지."""
        return self.last_value is not None

    @property
    def summary_str(self) -> str:
        """프롬프트 삽입용 한 줄 요약."""
        if not self.has_recent_data:
            return f"{self.label}: [데이터 없음]"
        val_str = f"{self.last_value:.2f} {self.unit}".strip()
        trend_str = f" ({self.direction})" if self.direction not in ("UNKNOWN", "STABLE") else ""
        delta_str = ""
        if self.delta_pct is not None and abs(self.delta_pct) >= 5:
            sign = "+" if self.delta_pct > 0 else ""
            delta_str = f", {sign}{self.delta_pct:.1f}% vs prev"
        return f"{self.label}: {val_str} [{self.ref_flag}]{trend_str}{delta_str}"


def compute_trends(
    labs: list[LabEvent],
    item_ids: Optional[list[int]] = None,
) -> dict[int, TrendResult]:
    """
    LabEvent 목록에서 item_id별 TrendResult를 계산.

    Args:
        labs: loader에서 가져온 LabEvent 목록
        item_ids: 분석할 item_id 목록. None이면 전체.

    Returns:
        {item_id: TrendResult} dict
    """
    # item_id별로 그룹핑
    grouped: dict[int, list[LabEvent]] = {}
    for lab in labs:
        if item_ids is None or lab.itemid in item_ids:
            grouped.setdefault(lab.itemid, []).append(lab)

    results: dict[int, TrendResult] = {}
    for item_id, events in grouped.items():
        results[item_id] = _compute_single(item_id, events)

    # item_ids에 있지만 데이터가 없는 항목도 포함 (gap 표시용)
    if item_ids:
        for iid in item_ids:
            if iid not in results:
                meta = get_lab_meta(iid)
                results[iid] = TrendResult(
                    itemid=iid,
                    label=meta["label"],
                    unit=meta.get("unit", ""),
                    last_value=None,
                    last_date=None,
                    ref_range=meta.get("ref_range"),
                    ref_flag="UNKNOWN",
                    direction="UNKNOWN",
                )

    return results


def _compute_single(item_id: int, events: list[LabEvent]) -> TrendResult:
    meta = get_lab_meta(item_id)
    label = meta["label"]
    unit = meta.get("unit", "")
    ref_range = meta.get("ref_range")
    worsening_dir = meta.get("worsening_direction", "both")
    min_delta = meta.get("min_meaningful_delta", 0)

    # 시간 순 정렬 + 이상치 제거
    sorted_events = sorted(events, key=lambda e: e.charttime)
    values = np.array([e.valuenum for e in sorted_events])
    values = _remove_outliers(values)

    valid_events = [e for e, v in zip(sorted_events, values) if not np.isnan(v)]
    valid_values = [v for v in values if not np.isnan(v)]

    if not valid_values:
        return TrendResult(
            itemid=item_id, label=label, unit=unit,
            last_value=None, last_date=None,
            ref_range=ref_range, ref_flag="UNKNOWN",
        )

    last_val = valid_values[-1]
    last_date = valid_events[-1].charttime
    ref_flag = _ref_flag(last_val, ref_range)

    result = TrendResult(
        itemid=item_id, label=label, unit=unit,
        last_value=last_val, last_date=last_date,
        ref_range=ref_range, ref_flag=ref_flag,
        n_points=len(valid_values),
        sparkline=_thin_sparkline(valid_events, valid_values),
    )

    # delta (직전 2회)
    if len(valid_values) >= 2:
        prev_val = valid_values[-2]
        prev_date = valid_events[-2].charttime
        result.previous_value = prev_val
        result.previous_date = prev_date
        result.delta_abs = last_val - prev_val
        result.delta_pct = (result.delta_abs / prev_val * 100) if prev_val != 0 else None

    # slope (3개 이상)
    if len(valid_values) >= 3:
        times_days = np.array([
            (e.charttime - valid_events[0].charttime).total_seconds() / 86400
            for e in valid_events
        ])
        slope, r_sq = _linear_regression(times_days, np.array(valid_values))
        result.slope = slope
        result.r_squared = r_sq

        ref_mid = np.mean(ref_range) if ref_range else last_val
        if ref_mid and ref_mid != 0:
            result.slope_pct_per_week = slope * 7 / ref_mid * 100

    result.direction = _classify_direction(
        slope=result.slope,
        delta_abs=result.delta_abs,
        worsening_dir=worsening_dir,
        min_delta=min_delta,
    )

    return result


def _remove_outliers(values: np.ndarray) -> np.ndarray:
    """IQR 3배 기준으로 이상치를 NaN으로 처리."""
    if len(values) < 4:
        return values
    q1, q3 = np.nanpercentile(values, [25, 75])
    iqr = q3 - q1
    lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
    result = values.copy().astype(float)
    result[(result < lower) | (result > upper)] = np.nan
    return result


def _ref_flag(value: float, ref_range: Optional[tuple]) -> str:
    if ref_range is None:
        return "UNKNOWN"
    lo, hi = ref_range
    if value < lo:
        return "LOW"
    if value > hi:
        return "HIGH"
    return "NORMAL"


def _linear_regression(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """단순 선형회귀. (slope, r_squared) 반환."""
    n = len(x)
    x_mean, y_mean = x.mean(), y.mean()
    ss_xy = ((x - x_mean) * (y - y_mean)).sum()
    ss_xx = ((x - x_mean) ** 2).sum()
    if ss_xx == 0:
        return 0.0, 0.0
    slope = ss_xy / ss_xx
    y_pred = slope * (x - x_mean) + y_mean
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y_mean) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0.0
    return float(slope), float(r_squared)


def _classify_direction(
    slope: Optional[float],
    delta_abs: Optional[float],
    worsening_dir: str,
    min_delta: float,
) -> str:
    """slope + 최소 의미 변화량 기준으로 방향 분류.

    slope 기반 전체 추세를 먼저 검토 — 점진적 CKD/빈혈처럼
    마지막 2회 delta는 작아도 전체 추세가 뚜렷한 케이스를 올바르게 감지.
    slope가 유의미하지 않으면 delta 기반으로 fallback.
    """
    # slope 기반 (전체 추세 우선)
    # 90일(3개월) 누적 변화가 min_delta 이상이면 유의미한 추세로 판단
    if slope is not None and abs(slope) >= min_delta / 90:
        is_increasing = slope > 0
        if worsening_dir == "up":
            return "WORSENING" if is_increasing else "IMPROVING"
        elif worsening_dir == "down":
            return "IMPROVING" if is_increasing else "WORSENING"
        else:
            return "CHANGING"

    # slope 약하거나 없음 → delta로 판단
    if delta_abs is not None:
        if abs(delta_abs) < min_delta:
            return "STABLE"
        is_increasing = delta_abs > 0
    else:
        return "UNKNOWN"

    if worsening_dir == "up":
        return "WORSENING" if is_increasing else "IMPROVING"
    elif worsening_dir == "down":
        return "IMPROVING" if is_increasing else "WORSENING"
    else:  # "both" — 정상 범위 밖으로 가는 방향 = WORSENING
        return "CHANGING"


def _thin_sparkline(
    events: list[LabEvent],
    values: list[float],
    max_points: int = 10,
) -> list[tuple[datetime, float]]:
    """균등 샘플링으로 스파크라인용 포인트 수 제한."""
    n = len(events)
    if n <= max_points:
        return [(e.charttime, v) for e, v in zip(events, values)]
    indices = np.linspace(0, n - 1, max_points, dtype=int)
    return [(events[i].charttime, values[i]) for i in indices]
