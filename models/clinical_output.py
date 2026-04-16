"""
고급 임상 분석 레이어의 구조화 출력 모델.

기존 TrendResult / ChangeFlag 데이터클래스를 대체하지 않으며,
그 위에 추가되는 파생 신호와 상태 판정 결과를 담는다.

모든 필드는 임상의에게 설명 가능한(explainable) 형태로 설계됨.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TrendSummary(BaseModel):
    """
    단일 lab item에 대한 고급 분석 요약.

    기존 TrendResult의 파생값(EWMA, 이상감지, 변화점)을 담으며,
    원본 TrendResult는 기존 파이프라인에서 그대로 유지된다.

    TrendResult vs TrendSummary 차이:
      - TrendResult.direction: 선형회귀 slope 임계값 초과 여부 (규칙 기반)
      - ewma_direction: EWMA 기반 — 최근값에 가중치, 노이즈에 강건
      - is_anomaly: z-score로 마지막 값의 통계적 이상도 측정
        (TrendResult의 IQR 아웃라이어 제거와 다름 — 제거가 아닌 탐지)
      - change_point_detected: 값의 평균이 구조적으로 이동한 시점 탐지
        (점진적 악화 vs 급격한 변화 시점 구분 가능)
    """
    itemid: int
    label: str
    last_value: Optional[float] = None
    direction: str = "UNKNOWN"            # 기존 TrendResult.direction 그대로 복사

    # ── EWMA 신호 ──────────────────────────────────────────
    ewma_value: Optional[float] = None    # 마지막 EWMA 평활값
    ewma_direction: str = "FLAT"          # "UP" | "DOWN" | "FLAT"
    ewma_slope: Optional[float] = None    # EWMA 기울기 (units/day)
    ewma_interpretation: str = ""         # 예: "점진적 상승", "급격한 하강"
    ewma_confidence: float = 0.0          # 0.0 ~ 1.0

    # ── 이상 감지 (z-score 기반) ────────────────────────────
    anomaly_score: Optional[float] = None  # |z-score| 값
    is_anomaly: bool = False               # |z| > z_threshold (기본 2.5)
    anomaly_interpretation: str = ""       # 예: "임상적으로 유의한 이상값"

    # ── 변화점 탐지 ─────────────────────────────────────────
    change_point_detected: bool = False
    change_point_index: Optional[int] = None   # sparkline 배열 기준 인덱스
    change_point_confidence: float = 0.0       # 0.0 ~ 0.999
    change_point_interpretation: str = ""      # 예: "급격한 평균 이동 감지"


class MultivariateSignal(BaseModel):
    """
    복합 임상 패널(다변량) 분석 결과.

    관련 검사값들을 함께 해석하여 단변량 분석이 놓치는
    임상 패턴(예: BUN:Cr 비율, MCV+Hgb 조합)을 포착한다.
    """
    panel: str           # "RENAL" | "ANEMIA" | "COAGULATION"
    interpretation: str  # 임상의 가독 해석 (한국어)
    severity: str        # "NORMAL" | "MILD" | "MODERATE" | "SEVERE"
    contributing_items: list[str]    # 판정에 기여한 검사 label 목록
    confidence: float                # 0.0 ~ 1.0 (데이터 충분도 반영)
    reasoning_trace: list[str]       # 단계별 추론 근거 목록


class PatientStateTransition(BaseModel):
    """
    환자 상태 전이 이벤트.

    상태가 변화할 때 어떤 이유로 전이되었는지 명시적으로 기록.
    임상의에게 "왜 이 상태로 판정됐는가"를 설명하기 위한 근거.
    """
    from_state: Optional[str] = None    # None = 최초 판정 (이전 상태 없음)
    to_state: str                        # "STABLE"|"DETERIORATING"|"CRITICAL"|"RECOVERING"
    reason: str                          # 전이 이유 요약 (임상의 가독)
    triggered_by: list[str] = Field(default_factory=list)  # 트리거된 검사 label 목록


class ClinicalAnalysisOutput(BaseModel):
    """
    고급 임상 분석 레이어의 최상위 출력 객체.

    기존 파이프라인 출력(TrendResult, ChangeFlag)과 병렬로 존재하며,
    LLM 컨텍스트 보강 및 고급 UI 패널에 사용된다.

    구조:
      trend_summaries      → 각 lab의 EWMA/이상/변화점 요약
      multivariate_signals → 복합 패널 해석 (신기능, 빈혈, 응고)
      patient_state        → 현재 환자 상태 (상태 머신 결과)
      state_transition     → 상태 전이 정보 (있을 경우)
      explanations         → 핵심 임상 추론 요약 (LLM 컨텍스트 보강용)
    """
    subject_id: int
    analysis_timestamp: str               # ISO 8601 형식

    # ── 환자 상태 판정 ────────────────────────────────────
    patient_state: str = "STABLE"         # "STABLE"|"DETERIORATING"|"CRITICAL"|"RECOVERING"
    state_confidence: float = 0.0         # 0.0 ~ 1.0
    state_transition: Optional[PatientStateTransition] = None

    # ── 단변량 고급 분석 요약 (lab별) ────────────────────
    trend_summaries: list[TrendSummary] = Field(default_factory=list)

    # ── 다변량 패널 분석 ──────────────────────────────────
    multivariate_signals: list[MultivariateSignal] = Field(default_factory=list)

    # ── 기존 detect_flags() 결과 통계 (참조용) ───────────
    change_flags_count: int = 0
    high_severity_flag_count: int = 0

    # ── 임상 추론 설명 (LLM 컨텍스트 삽입용) ─────────────
    explanations: list[str] = Field(default_factory=list)

    # ── 경고 (데이터 부족, 신뢰도 낮음 등) ───────────────
    warnings: list[str] = Field(default_factory=list)

    # ── 메타 ──────────────────────────────────────────────
    analysis_version: str = "2.0"
    deterioration_score: int = 0          # 상태 머신 내부 점수 (디버그용)
