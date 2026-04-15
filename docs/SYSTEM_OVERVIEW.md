# OTEMR 시스템 개요

> **AI 기반 종단적 EMR 요약 시스템 (AI-driven Longitudinal EMR Record Summarization)**
> 목적: 의사가 환자를 만나기 전 MIMIC-IV 기반 전자의무기록을 자동 분석하여 목적별 임상 브리핑을 생성

---

## 1. 시스템 목적

OTEMR은 전자의무기록(EMR)의 방대한 데이터를 의사가 즉시 활용 가능한 형태로 변환하는 AI 임상 지원 시스템입니다.

- **대상 사용자**: 병원 의사 (내과, 외과, 전문의)
- **데이터 소스**: MIMIC-IV (Google BigQuery) 또는 데모 Parquet 파일
- **핵심 가치**: 규칙 기반 임상 플래그 탐지 + LLM 서술 합성

### 지원 목적 (Purpose)

| 목적 | 설명 | 주요 포커스 |
|------|------|------------|
| `rounds` | 병동 회진 인수인계 | 72시간 내 변화, 즉각적 조치 필요 항목 |
| `preop` | 수술 전 위험 평가 | 심장/신장/응고 위험도, INR 브릿지 계획 |
| `referral` | 전문과 의뢰 | 전체 문제 목록, 진단 워크업 현황 |

---

## 2. 전체 파이프라인

```
[데이터 입력] → [분석] → [문맥 조립] → [LLM 합성] → [UI 표시]
```

### 2-1. 데이터 로딩 (`data/loader.py`)

- **우선순위 폴백 체인**: 캐시 → BigQuery → 데모 Parquet → Fixture(오프라인)
- **`PatientRecord`** 데이터클래스로 모든 환자 정보를 통합 보유
- 로드 항목:
  - 인구통계 (나이, 성별, anchor year)
  - 입원 이력 (최근 10건)
  - 진단 (ICD 코드 + 설명, 최대 15개)
  - 검사 수치 (180일 이력, 목적·진단 기반 필터링)
  - 처방 (활성 약물, 최대 15개)
  - 퇴원 요약 (선택적, 최대 2건)

### 2-2. 규칙 기반 분석

#### 트렌드 분석 (`analysis/trend.py`)
- item_id별로 180일 검사 이력 분석
- IQR 기반 이상치 제거 (3× 승수)
- 선형 회귀 slope + 마지막 2개 값 delta 계산
- 방향 분류: `IMPROVING` / `WORSENING` / `STABLE`
- 스파크라인 데이터 생성 (최대 10포인트)

#### 플래그 탐지 (`analysis/flags.py`)
3계층 임상 알림 시스템:

| 계층 | 조건 | 가시성 | 예시 |
|------|------|--------|------|
| Layer 1 (ALWAYS) | 절대 임계값 초과 | 항상 표시 | INR > 3.5 |
| Layer 2 (ON_ALERT) | 정상값이지만 악화 추세 | 알림 시 표시 | Cr 정상 but 상승 중 |
| Layer 3 (ON_DEMAND) | 안정/저위험 | 요청 시 표시 | 경미한 변화 |

- 13개 검사 항목 규칙 내장: Creatinine, INR, Hemoglobin, Troponin 등

#### 체크리스트 생성 (`analysis/checklist.py`)
- **Flag 기반**: 고중증 플래그 → 자동 조치 항목 생성
- **약물 안전**: Metformin (Cr > 1.5), NSAIDs (신기능 저하) 금기 감지
- **데이터 공백**: DM 환자에 HbA1c 누락 등 식별
- **목적 특이적**: 수술 전 INR 브릿지 계획, 전문과 의뢰 준비 사항 등

#### 진단 문맥화 (`analysis/diagnosis_context.py`)
- 48개 ICD 접두사 → 임상 태그 매핑
  - `E11` → DM2, `N18` → CKD, `I50` → Heart Failure 등
- 목적별 태그 우선순위 재정렬 (preop: 심장·신장 강조)

### 2-3. 문맥 조립 (`agent/context_builder.py`)

LLM 프롬프트용 구조화 텍스트 구성 (8개 섹션):
1. 인구통계
2. ICD 진단 + 임상 태그
3. 활성 약물
4. 검사 트렌드 요약 (3포인트 스파크라인)
5. 변화 플래그
6. Must-check 항목
7. 퇴원 요약 (필요 시)
8. 목적별 지시사항

**토큰 예산 관리**: 최대 6000 토큰, 초과 시 점진적 축소
- 1단계: 퇴원 요약 제거
- 2단계: 트렌드 라인 축약

### 2-4. LLM 합성 (`agent/summarizer.py`)

- **모델**: OpenAI `gpt-4o-mini`
- **응답 형식**: `response_format={"type": "json_object"}`
- **Pydantic 스키마**로 응답 파싱 및 검증 (`AgentOutput`)
- 선택적: `enrich_checklist_reasons()` — LLM 기반 체크리스트 이유 보강

### 2-5. UI 표시 (`ui/app.py` — Streamlit)

```
┌─────────────────────────────────────────┐
│  사이드바                                │
│  • 환자 선택 (데모 A/B/C 또는 직접 입력) │
│  • 목적 버튼 (Rounds / PreOp / Referral) │
└─────────────────────────────────────────┘
┌──────────────┬──────────────┬───────────┐
│ 변화 플래그  │  임상 요약   │ 검사 트렌드│
│ (3계층)      │  (LLM 생성)  │ (스파크라인│
│              │              │  + 체크리스│
│              │              │  트)       │
└──────────────┴──────────────┴───────────┘
```

---

## 3. 주요 컴포넌트 구조

```
OTEMR/
├── agent/                   # LLM 통합 및 프롬프팅
│   ├── summarizer.py        # GPT-4 래퍼 + 토큰 관리
│   ├── context_builder.py   # 프롬프트 조립
│   ├── output_schema.py     # Pydantic 출력 스키마
│   └── prompts.py           # 목적별 시스템 프롬프트
│
├── analysis/                # 규칙 기반 분석
│   ├── trend.py             # 시계열 분석 (회귀, 델타)
│   ├── flags.py             # 3계층 임상 알림
│   ├── checklist.py         # 안전 규칙 엔진
│   └── diagnosis_context.py # ICD → 임상 태그 매핑
│
├── config/
│   ├── settings.py          # 환경 변수 + 상수
│   └── lab_profiles.py      # 검사 메타데이터 (200줄+)
│
├── data/
│   ├── loader.py            # 메인 오케스트레이터 (PatientRecord)
│   ├── queries.py           # BigQuery SQL 템플릿
│   ├── bq_client.py         # BQ 싱글턴 + 폴백
│   ├── cache.py             # 디스크 캐시 (pickle)
│   ├── demo_patients.py     # 데모 케이스 레지스트리
│   └── demo/                # 데모 Parquet 파일
│
├── eval/                    # 평가 프레임워크
│   ├── runner.py            # CLI 오케스트레이터
│   ├── cases/               # 테스트 케이스 시나리오
│   │   ├── case_dm_ckd.py   # DM+CKD (회진)
│   │   ├── case_cad_preop.py # CAD (수술 전)
│   │   └── case_referral.py # 다계통 (의뢰)
│   ├── evaluators/
│   │   ├── rule_eval.py     # 규칙 기반 평가
│   │   └── llm_judge.py     # GPT-4 루브릭 평가 (25점 척도)
│   └── report.py            # JSON + HTML 보고서
│
├── ui/
│   ├── app.py               # Streamlit 메인 앱
│   └── components/
│       ├── summary_panel.py # LLM 출력 + 충분성 미터
│       ├── flags_panel.py   # 3계층 플래그 시각화
│       ├── trend_chart.py   # 검사값 + 트렌드 + 날짜
│       └── checklist_panel.py # 조치 항목 + 긴급도
│
└── tests/fixtures/
    └── patient_dm_ckd.py    # 합성 테스트 환자 (subject_id 99001)
```

---

## 4. 시스템 출력 결과

### 4-1. Pre-Visit Context (LLM 생성)
- 1~2문장 환자 요약
- 활성 문제 목록
- 현재 투약 약물
- 핵심 검사 수치 + 트렌드 해석
- 데이터 충분성 평가 (부족한 항목 명시)

### 4-2. Change Flags (규칙 + 시각화)
- 항목명, 현재/이전 수치, 중증도, 임상적 의미
- 3계층 점진적 공개 방식 표시

### 4-3. Checklist (규칙 + LLM 보강)
- 조치 항목 + 긴급도 (`URGENT` / `ROUTINE` / `OPTIONAL`)
- 각 항목의 임상적 근거

### 4-4. Sparklines (트렌드 시각화)
- 최대 10포인트 이력 궤적
- 최근 3개 수치 + 날짜

### 목적별 출력 차이

| 목적 | 추가 검사 | 체크리스트 예시 |
|------|-----------|----------------|
| **Rounds** | Base labs, Lactate | "Reassess fluid status" |
| **Preop** | Troponin, BNP, INR/PT/PTT | "INR bridge plan", "Anesthesia consult" |
| **Referral** | HbA1c, Lipids, Thyroid | "Attach trend plots", "Explain treatment tried" |

---

## 5. 데이터 흐름 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│                     데이터 소스                               │
│   BigQuery (MIMIC-IV)  ·  Demo Parquet  ·  Fixture(오프라인) │
└─────────────────────┬────────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  data/loader.py        │
         │  → PatientRecord       │
         │  (labs, meds, dx, etc) │
         └───┬────────────────────┘
             │
     ┌───────┼──────────┬──────────────┐
     ▼       ▼          ▼              ▼
 ┌───────┐ ┌────────┐ ┌──────────┐ ┌──────────────┐
 │trend  │ │flags   │ │checklist │ │diagnosis_ctx │
 │.py    │ │.py     │ │.py       │ │.py           │
 │트렌드 │ │알림    │ │규칙      │ │ICD 태그      │
 └───┬───┘ └───┬────┘ └────┬─────┘ └──────┬───────┘
     │         │           │              │
     └─────────┼───────────┴──────────────┘
               │
               ▼
     ┌─────────────────────┐
     │ context_builder.py  │
     │ → 구조화 프롬프트   │
     └──────────┬──────────┘
                │
                ▼
     ┌──────────────────────────┐
     │ summarizer.py (GPT-4o)   │
     │ → AgentOutput (JSON)     │
     └──────────┬───────────────┘
                │
                ▼
     ┌──────────────────────────┐
     │  app.py (Streamlit)      │
     │  → 인터랙티브 대시보드   │
     └──────────────────────────┘
```

---

## 6. 기술 스택

| 레이어 | 기술 |
|--------|------|
| **LLM** | OpenAI API (gpt-4o-mini) |
| **데이터** | Google BigQuery + MIMIC-IV |
| **데이터 처리** | Pandas 2.2+, NumPy 2.1+, SciPy 1.14+ |
| **검증** | Pydantic 2.9+ |
| **토큰 계산** | TikToken 0.8+ |
| **UI** | Streamlit 1.40+, Altair 5.3+ |
| **인증** | google-auth 2.29+, google-cloud-bigquery 3.20+ |
| **설정** | python-dotenv 1.0+ |
| **테스트** | pytest 8.2+, pytest-mock 3.14+ |

---

## 7. 핵심 설계 패턴

| 패턴 | 구현 | 목적 |
|------|------|------|
| **Singleton 캐시** | `bq_client.get_bq_client()` + `@lru_cache` | BQ 연결 재사용 |
| **데이터클래스 모델** | `PatientRecord`, `TrendResult`, `ChangeFlag` | 타입 안전성 |
| **Pydantic 검증** | `AgentOutput` 스키마 | LLM 응답 형식 강제 |
| **점진적 축소** | 토큰 예산 → 퇴원요약 제거 → 트렌드 축약 | 대규모 문맥 처리 |
| **폴백 체인** | 캐시 → Parquet → BQ → Fixture | 오프라인 개발 지원 |
| **규칙 엔진** | `FLAG_RULES` dict + 조건 함수 | 유지보수 가능한 알림 로직 |

---

## 8. 실행 방법

### UI 실행
```bash
streamlit run ui/app.py
```

### 평가 실행
```bash
python -m eval.runner                        # 전체 케이스
python -m eval.runner --skip-llm-judge       # LLM 판정 생략 (빠름)
python -m eval.runner --cases dm_ckd         # 단일 케이스
```

### 오프라인 개발
- subject_id `99001` 사용 → `tests/fixtures/patient_dm_ckd.py` 합성 데이터 자동 로드
- 또는 데모 Parquet: `load_demo_patient(18767874, "rounds")`

---

## 9. 평가 프레임워크

3개 시나리오 내장:
- `dm_ckd`: DM+CKD 환자 회진 (Creatinine 악화 + Metformin 금기)
- `cad_preop`: CAD 수술 전 평가 (Troponin + INR 브릿지)
- `referral`: 다계통 전문과 의뢰

평가 방식:
- **규칙 기반 평가** (`rule_eval.py`): 예상 플래그/체크리스트와 실제 출력 비교
- **LLM 심판** (`llm_judge.py`): GPT-4 루브릭 기반 25점 척도 평가
- **보고서**: JSON + HTML 형식으로 `eval/reports/` 저장
