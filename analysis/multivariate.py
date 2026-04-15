"""
다변량 임상 패널 분석.

단변량 분석이 놓치는 복합 임상 패턴을 포착:
  - RENAL:       Creatinine + BUN → 신장 기능 및 AKI 패턴 판별
  - ANEMIA:      Hemoglobin + MCV → 빈혈 유형 분류
  - COAGULATION: INR + PT + PTT   → 응고 장애 패턴 분류

각 패널은:
  1. 데이터 존재 여부 확인 (없으면 skip)
  2. 임상 규칙 적용
  3. severity + interpretation + reasoning_trace 반환

임상 근거:
  - BUN:Cr 비율: 신전성(pre-renal) vs 신실질성(intrinsic) AKI 감별에 사용
  - MCV: 소구성(<80) / 정구성(80-100) / 대구성(>100) 분류로 빈혈 원인 추론
  - INR/PT/PTT 패턴: 와파린, 헤파린, 범응고병증(DIC), 간질환 감별
"""
from __future__ import annotations

from typing import Optional

from analysis.trend import TrendResult
from models.clinical_output import MultivariateSignal

# ──────────────────────────────────────────────────────────────
# item_id 상수 (config/lab_profiles.py 참조)
# ──────────────────────────────────────────────────────────────
_CR_IDS  = {50912, 52546}                  # Creatinine
_BUN_ID  = 51006                           # BUN (Urea Nitrogen)
_HGB_ID  = 51222                           # Hemoglobin
_MCV_ID  = 51250                           # MCV
_INR_IDS = {51237, 51675}                  # INR
_PT_ID   = 51274                           # PT
_PTT_ID  = 51275                           # PTT


# ──────────────────────────────────────────────────────────────
# 공개 진입점
# ──────────────────────────────────────────────────────────────

def run_multivariate_analysis(
    trends: dict[int, TrendResult],
) -> list[MultivariateSignal]:
    """
    가용한 모든 패널 분석 실행.

    데이터가 없는 패널은 조용히 skip.

    Args:
        trends: compute_trends()의 반환값

    Returns:
        감지된 MultivariateSignal 목록 (없으면 빈 리스트)
    """
    signals: list[MultivariateSignal] = []

    renal = analyze_renal_panel(trends)
    if renal is not None:
        signals.append(renal)

    anemia = analyze_anemia_panel(trends)
    if anemia is not None:
        signals.append(anemia)

    coag = analyze_coagulation_panel(trends)
    if coag is not None:
        signals.append(coag)

    return signals


# ──────────────────────────────────────────────────────────────
# 신장 기능 패널 (Creatinine + BUN)
# ──────────────────────────────────────────────────────────────

def analyze_renal_panel(
    trends: dict[int, TrendResult],
) -> Optional[MultivariateSignal]:
    """
    신장 기능 패널 분석.

    BUN:Cr 비율을 핵심 지표로 사용:
      비율 > 20  → 신전성 패턴 (탈수, 심박출 감소, GI 출혈)
      비율 < 10  → 신실질성 패턴 (세뇨관 손상, 급성 세뇨관 괴사)
      10 ≤ 비율 ≤ 20 → 중간 패턴 (복합 원인 가능)

    Severity:
      Cr > 3.0 → SEVERE
      Cr 2.0~3.0 → MODERATE
      Cr 1.2~2.0 → MILD
      정상 범위 → NORMAL

    데이터 충분도:
      Cr + BUN 모두 n_points ≥ 3 → confidence 1.0
      그 외 → confidence 0.6
    """
    cr_trend = _get_first(trends, _CR_IDS)
    bun_trend = trends.get(_BUN_ID)

    # Creatinine 없으면 패널 분석 불가
    if cr_trend is None or not cr_trend.has_recent_data:
        return None

    cr_val = cr_trend.last_value
    contributing = [cr_trend.label]
    trace: list[str] = []

    # ── Severity 판정 (Cr 절대값 기반) ──
    if cr_val is None:
        return None

    if cr_val > 3.0:
        severity = "SEVERE"
    elif cr_val > 2.0:
        severity = "MODERATE"
    elif cr_val > 1.2:
        severity = "MILD"
    else:
        severity = "NORMAL"

    trace.append(f"Creatinine {cr_val:.2f} mg/dL → {severity}")

    # ── BUN:Cr 비율 분석 ──
    bun_cr_pattern = ""
    if bun_trend is not None and bun_trend.has_recent_data and bun_trend.last_value:
        bun_val = bun_trend.last_value
        contributing.append(bun_trend.label)
        ratio = bun_val / cr_val if cr_val > 0 else None

        if ratio is not None:
            trace.append(f"BUN {bun_val:.1f} mg/dL, BUN:Cr 비율 = {ratio:.1f}")
            if ratio > 20:
                bun_cr_pattern = "신전성 패턴 (탈수/관류 감소 의심)"
                trace.append(f"BUN:Cr > 20 → 신전성(pre-renal) AKI 패턴")
                # 신전성은 severity 1단계 상향 (관류 감소 → 더 위험)
                if severity == "MILD":
                    severity = "MODERATE"
                    trace.append("신전성 패턴으로 severity MILD → MODERATE 상향")
            elif ratio < 10:
                bun_cr_pattern = "신실질성 패턴 (세뇨관 손상 의심)"
                trace.append(f"BUN:Cr < 10 → 신실질성(intrinsic) 손상 패턴")
            else:
                bun_cr_pattern = "혼합 패턴"
                trace.append(f"BUN:Cr 10~20 → 복합 원인 가능")

    # ── 방향성 분석 ──
    cr_dir = cr_trend.direction
    bun_dir = bun_trend.direction if bun_trend else "UNKNOWN"

    if cr_dir == "WORSENING" and bun_dir == "WORSENING":
        trace.append("Cr + BUN 동반 악화 중 → 신장 기능 저하 가속 가능성")
        if severity == "MILD":
            severity = "MODERATE"
            trace.append("동반 악화로 severity MILD → MODERATE 상향")
    elif cr_dir == "WORSENING":
        trace.append(f"Cr {cr_dir}, BUN {bun_dir} — Cr만 악화 중")

    # ── 해석 문장 조립 ──
    if severity == "NORMAL":
        interpretation = "신장 기능 정상 범위"
    else:
        pattern_str = f" ({bun_cr_pattern})" if bun_cr_pattern else ""
        interpretation = f"신장 기능 {severity}{pattern_str} — Cr {cr_val:.2f} mg/dL"
        if cr_dir == "WORSENING":
            interpretation += ", 악화 추세"

    # ── 신뢰도 ──
    cr_sufficient = cr_trend.n_points >= 3
    bun_sufficient = bun_trend is not None and bun_trend.n_points >= 3
    confidence = 1.0 if (cr_sufficient and bun_sufficient) else 0.6

    return MultivariateSignal(
        panel="RENAL",
        interpretation=interpretation,
        severity=severity,
        contributing_items=contributing,
        confidence=confidence,
        reasoning_trace=trace,
    )


# ──────────────────────────────────────────────────────────────
# 빈혈 패널 (Hemoglobin + MCV)
# ──────────────────────────────────────────────────────────────

def analyze_anemia_panel(
    trends: dict[int, TrendResult],
) -> Optional[MultivariateSignal]:
    """
    빈혈 패널 분석.

    MCV 기반 빈혈 유형 분류 (Hgb LOW일 때):
      MCV < 80  → 소구성 빈혈 (철결핍, 지중해빈혈)
      80~100    → 정구성 빈혈 (만성질환/CKD 연관, 급성 출혈)
      > 100     → 대구성 빈혈 (B12/엽산 결핍, 약물 유발)

    MCV 없이 Hgb만 있으면 → 유형 미상 빈혈 (confidence 낮춤)

    Severity (Hgb g/dL):
      ≥ 10       → MILD
      8.0 ~ 10   → MODERATE
      < 8.0      → SEVERE
      정상        → NORMAL
    """
    hgb_trend = trends.get(_HGB_ID)
    mcv_trend = trends.get(_MCV_ID)

    if hgb_trend is None or not hgb_trend.has_recent_data:
        return None

    hgb_val = hgb_trend.last_value
    if hgb_val is None:
        return None

    contributing = [hgb_trend.label]
    trace: list[str] = []

    # ── Severity 판정 (Hgb 절대값) ──
    # 정상 하한: 여성 12.0, 남성 13.5 g/dL — MIMIC ref_range (12.0, 17.5) 사용
    hgb_ref_low = (hgb_trend.ref_range[0] if hgb_trend.ref_range else 12.0)

    if hgb_val >= hgb_ref_low:
        severity = "NORMAL"
    elif hgb_val >= 10.0:
        severity = "MILD"
    elif hgb_val >= 8.0:
        severity = "MODERATE"
    else:
        severity = "SEVERE"

    trace.append(f"Hemoglobin {hgb_val:.1f} g/dL → {severity}")

    if severity == "NORMAL":
        # Hgb 정상이면 빈혈 패널 분석 의미 없음
        interpretation = "빈혈 없음 (Hgb 정상 범위)"
        return MultivariateSignal(
            panel="ANEMIA",
            interpretation=interpretation,
            severity="NORMAL",
            contributing_items=contributing,
            confidence=1.0 if hgb_trend.n_points >= 3 else 0.7,
            reasoning_trace=trace,
        )

    # ── MCV 기반 유형 분류 ──
    anemia_type = ""
    if mcv_trend is not None and mcv_trend.has_recent_data and mcv_trend.last_value:
        mcv_val = mcv_trend.last_value
        contributing.append(mcv_trend.label)
        trace.append(f"MCV {mcv_val:.1f} fL")

        if mcv_val < 80:
            anemia_type = "소구성 빈혈 (철결핍/지중해빈혈 패턴)"
            trace.append("MCV < 80 → 소구성: 철결핍 또는 지중해빈혈 감별 필요")
        elif mcv_val <= 100:
            anemia_type = "정구성 빈혈 (만성질환/CKD 연관 가능)"
            trace.append("MCV 80~100 → 정구성: 만성질환 빈혈 또는 CKD 연관성 확인")
        else:
            anemia_type = "대구성 빈혈 (B12/엽산 결핍 또는 약물 유발)"
            trace.append("MCV > 100 → 대구성: B12/엽산 결핍 또는 Methotrexate 등 약물 확인")
        confidence = 1.0 if (hgb_trend.n_points >= 3 and mcv_trend.n_points >= 2) else 0.7
    else:
        trace.append("MCV 데이터 없음 — 빈혈 유형 분류 불가")
        anemia_type = "빈혈 유형 미상 (MCV 데이터 없음)"
        confidence = 0.6

    # ── 방향성 ──
    if hgb_trend.direction == "WORSENING":
        trace.append("Hgb 악화 추세 — 빈혈 진행 중")
        if severity == "MILD":
            severity = "MODERATE"
            trace.append("Hgb 악화 추세로 severity MILD → MODERATE 상향")

    interpretation = f"{anemia_type} ({severity}) — Hgb {hgb_val:.1f} g/dL"
    if hgb_trend.direction == "WORSENING":
        interpretation += ", 악화 추세"

    return MultivariateSignal(
        panel="ANEMIA",
        interpretation=interpretation,
        severity=severity,
        contributing_items=contributing,
        confidence=confidence,
        reasoning_trace=trace,
    )


# ──────────────────────────────────────────────────────────────
# 응고 패널 (INR + PT + PTT)
# ──────────────────────────────────────────────────────────────

def analyze_coagulation_panel(
    trends: dict[int, TrendResult],
) -> Optional[MultivariateSignal]:
    """
    응고 패널 분석.

    패턴 감별:
      INR만 상승        → 와파린 효과 또는 간질환 (외인성 경로)
      PTT만 상승        → 헤파린 효과 또는 접촉인자 결핍 (내인성 경로)
      INR + PTT 모두 상승 → 범응고병증(DIC) 또는 간부전
      모두 정상         → 응고 이상 없음

    Severity:
      INR > 3.5 OR PT > 20 OR PTT > 60 → SEVERE
      INR 2.0~3.5 OR PT 15~20 OR PTT 45~60 → MODERATE
      경미한 이상 → MILD
      정상 → NORMAL
    """
    inr_trend = _get_first(trends, _INR_IDS)
    pt_trend  = trends.get(_PT_ID)
    ptt_trend = trends.get(_PTT_ID)

    # 최소 하나라도 있어야 분석 가능
    available = [t for t in [inr_trend, pt_trend, ptt_trend]
                 if t is not None and t.has_recent_data]
    if not available:
        return None

    contributing = [t.label for t in available]
    trace: list[str] = []

    inr_val = inr_trend.last_value if (inr_trend and inr_trend.has_recent_data) else None
    pt_val  = pt_trend.last_value  if (pt_trend  and pt_trend.has_recent_data)  else None
    ptt_val = ptt_trend.last_value if (ptt_trend and ptt_trend.has_recent_data) else None

    # ── Severity 판정 ──
    severe_flags: list[str] = []
    moderate_flags: list[str] = []

    if inr_val is not None:
        trace.append(f"INR {inr_val:.2f}")
        if inr_val > 3.5:
            severe_flags.append(f"INR {inr_val:.2f} > 3.5")
        elif inr_val > 2.0:
            moderate_flags.append(f"INR {inr_val:.2f} > 2.0")

    if pt_val is not None:
        trace.append(f"PT {pt_val:.1f} sec")
        if pt_val > 20:
            severe_flags.append(f"PT {pt_val:.1f} > 20 sec")
        elif pt_val > 15:
            moderate_flags.append(f"PT {pt_val:.1f} > 15 sec")

    if ptt_val is not None:
        trace.append(f"PTT {ptt_val:.1f} sec")
        if ptt_val > 60:
            severe_flags.append(f"PTT {ptt_val:.1f} > 60 sec")
        elif ptt_val > 45:
            moderate_flags.append(f"PTT {ptt_val:.1f} > 45 sec")

    if severe_flags:
        severity = "SEVERE"
        trace.append(f"중증 응고 이상: {', '.join(severe_flags)}")
    elif moderate_flags:
        severity = "MODERATE"
        trace.append(f"중등도 응고 이상: {', '.join(moderate_flags)}")
    else:
        # ref_flag 기반 MILD 확인
        has_abnormal_ref = any(t.ref_flag in ("HIGH", "LOW") for t in available)
        severity = "MILD" if has_abnormal_ref else "NORMAL"

    # ── 패턴 감별 ──
    inr_elevated  = inr_val is not None and inr_val > 1.5
    ptt_elevated  = ptt_val is not None and ptt_val > 45

    if inr_elevated and ptt_elevated:
        pattern = "범응고병증(DIC) 또는 간부전 패턴 — INR + PTT 동반 연장"
        trace.append("INR + PTT 모두 상승 → 범응고병증(DIC) / 간부전 감별 필요")
    elif inr_elevated:
        pattern = "외인성 경로 이상 — 와파린 효과 또는 간질환"
        trace.append("INR만 상승 → 와파린 용량 또는 간기능 확인")
    elif ptt_elevated:
        pattern = "내인성 경로 이상 — 헤파린 효과 또는 접촉인자 결핍"
        trace.append("PTT만 상승 → 헤파린 투여 여부 확인")
    else:
        pattern = "응고 이상 없음"

    # ── 해석 문장 조립 ──
    if severity == "NORMAL":
        interpretation = "응고 기능 정상 범위"
    else:
        inr_str = f"INR {inr_val:.2f}" if inr_val else ""
        interpretation = f"{pattern} ({severity})"
        if inr_str:
            interpretation += f" — {inr_str}"

    confidence = 1.0 if len(available) >= 2 else 0.6

    return MultivariateSignal(
        panel="COAGULATION",
        interpretation=interpretation,
        severity=severity,
        contributing_items=contributing,
        confidence=confidence,
        reasoning_trace=trace,
    )


# ──────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────

def _get_first(
    trends: dict[int, TrendResult],
    item_ids: set[int],
) -> Optional[TrendResult]:
    """item_ids 중 데이터가 있는 첫 번째 TrendResult 반환."""
    for iid in item_ids:
        t = trends.get(iid)
        if t is not None and t.has_recent_data:
            return t
    return None
