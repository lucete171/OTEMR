# OTEMR — 아키텍처 및 파일 구조

OTEMR(One-Touch EMR)은 MIMIC-IV 기반의 AI 임상 브리핑 시스템입니다.
환자 데이터를 로드 → rule-based 분석 → LLM 요약 → Streamlit UI로 제공합니다.

---

## 전체 파이프라인

```
[데이터 소스]
  data/demo/*.parquet         ← 사전 선별된 데모 환자 3명
  data/processed/*.parquet    ← 전처리된 전체 MIMIC-IV 데이터
  BigQuery (MIMIC-IV)         ← 원격 데이터 소스 (fallback)
  tests/fixtures/             ← 완전 오프라인용 합성 환자 (ID 99001)
        │
        ▼
[1. 데이터 로드]  data/loader.py
  PatientRecord 생성
  (Admission, Diagnosis, LabEvent, Prescription)
        │
        ▼
[2. Rule-based 분석]
  analysis/trend.py      → TrendResult (선형회귀 + 방향 분류)
  analysis/flags.py      → ChangeFlag (이상 변화 감지)
  analysis/checklist.py  → ChecklistItem (임상 액션 아이템)
        │
        ▼
[3. 프롬프트 조립]  agent/context_builder.py
  구조화된 텍스트 컨텍스트 생성 (6000 토큰 예산 관리)
        │
        ▼
[4. LLM 요약]  agent/summarizer.py
  GPT-4o-mini (json_object 모드)
  → AgentOutput (Pydantic 검증)
        │
        ▼
[5. UI 렌더링]  ui/app.py + ui/components/
  Change Flags / 임상 요약 / Lab 트렌드 차트 / 체크리스트
```

---

## 로딩 우선순위

```
캐시(pickle) → demo parquet → BigQuery → fixture(99001)
```

demo 환자 ID (18767874, 13303809, 12468016)는 자동으로 `data/demo/`에서 로드.
그 외 subject_id는 BigQuery 시도 → 실패 시 에러.
ID 99001은 합성 픽스처 데이터로 fallback.

---

## 목적(Purpose) 모드


| 코드         | 한국어   | 설명                           |
| ---------- | ----- | ---------------------------- |
| `rounds`   | 인계용   | 최근 72시간 변화 중심, 즉각 주의사항 강조    |
| `preop`    | 수술 전  | 심장·신장·응고 위험도, 항응고제 bridge 계획 |
| `referral` | 타과 의뢰 | 전문의용 전체 임상 요약, 의뢰 이유 선두      |


---

## 폴더 구조

```
OTEMR/
├── agent/           # LLM 연동 레이어
├── analysis/        # Rule-based 분석 엔진
├── config/          # 설정, Lab 프로파일
├── data/            # 데이터 로드, 캐시, 쿼리
│   ├── demo/        # 데모용 parquet (3명)
│   └── processed/   # 전처리된 전체 MIMIC-IV parquet
├── docs/            # 프로젝트 문서
├── scripts/         # 유틸리티 스크립트
├── tests/           # 단위 테스트 + 픽스처
│   └── fixtures/    # 오프라인 합성 환자 데이터
└── ui/              # Streamlit 앱
    └── components/  # UI 컴포넌트
```

---

## 파일별 역할

### `agent/`


| 파일                   | 역할                                                                                                                                          |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `summarizer.py`      | GPT-4o-mini API 호출 래퍼. 토큰 예산 관리(`tiktoken`), json_object 모드, Pydantic 검증, 재시도 로직 포함.                                                        |
| `context_builder.py` | `PatientRecord` + 분석 결과 → 프롬프트 user message 조립. 섹션: DEMOGRAPHICS / DIAGNOSES / TAGS / MEDICATIONS / LAB TRENDS / FLAGS / CHECKLIST / NOTES. |
| `output_schema.py`   | GPT 출력 Pydantic 스키마. `AgentOutput` = `PreVisitContext` + `ChangeFlagOutput[]` + `ChecklistItemOutput[]`.                                    |
| `prompts.py`         | 목적별 system prompt 빌더. 임상 역할 설정, JSON 출력 포맷 지정, 데이터 기반 진술 강제.                                                                                |


### `analysis/`


| 파일                     | 역할                                                                                                                                |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `trend.py`             | `LabEvent[]` → `Dict[itemid, TrendResult]`. 이상치 제거(IQR 3배), 선형회귀 slope, IMPROVING/WORSENING/STABLE 방향 분류, 스파크라인 데이터(최대 10포인트) 생성. |
| `flags.py`             | `TrendResult` 기반 이상 변화 감지. 중증도(HIGH/MEDIUM/LOW) 분류. 예: Cr +50% → HIGH (AKI 기준), Hgb < 7.0 → HIGH (중증 빈혈).                         |
| `checklist.py`         | HIGH 플래그 → 액션 아이템 변환. 약물 안전성 규칙(Metformin+AKI, NSAID+CKD 등), 데이터 갭 감지, 목적별 규칙 적용.                                                 |
| `diagnosis_context.py` | ICD 코드 목록 → 임상 컨텍스트 태그 추출 (DM, CKD, HF 등). 프롬프트 삽입용.                                                                              |


### `config/`


| 파일                | 역할                                                                                                                                   |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `lab_profiles.py` | Lab item 메타데이터 정의. BASE 항목(CBC/BMP/LFT/응고), 목적별 추가 항목, ICD prefix별 추가 항목(E11→HbA1c, N18→Cr·BUN 등), 정상 범위, 악화 방향(`up`/`down`/`both`). |
| `settings.py`     | 환경변수 로드. BQ 프로젝트, OpenAI 키, 파이프라인 상수(`LAB_HISTORY_DAYS=180`, `PROMPT_TOKEN_BUDGET=6000` 등).                                          |


### `data/`


| 파일                 | 역할                                                                                                                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `loader.py`        | 핵심 데이터 모델(`PatientRecord`, `Admission`, `LabEvent`, `Prescription` 등) 정의. BigQuery 로드 함수(`load_patient`) + parquet 로드 함수(`load_patient_from_parquet`, `load_demo_patient`, `load_processed_patient`). |
| `queries.py`       | MIMIC-IV BigQuery SQL 쿼리 템플릿. demographics+admissions, diagnoses, labs, prescriptions, discharge notes 조회.                                                                                            |
| `bq_client.py`     | BigQuery 클라이언트 싱글턴. 자격증명 없을 시 gracefully None 반환.                                                                                                                                                     |
| `cache.py`         | pickle 기반 디스크 캐시. `data/cache/`에 저장. 키 형식: `{subject_id}_{purpose}_{lab_days}`.                                                                                                                       |
| `demo_patients.py` | 데모 케이스 목록(`DEMO_CASES`). 3개 케이스의 subject_id, 기본 목적, 설명 정의.                                                                                                                                            |


#### `data/demo/` — 데모용 parquet (3명)


| 파일                           | 내용              |
| ---------------------------- | --------------- |
| `demo_patients.parquet`      | 인구통계 (3행)       |
| `demo_admissions.parquet`    | 입원 이력 (114행)    |
| `demo_diagnoses.parquet`     | ICD 진단 (2,596행) |
| `demo_labs.parquet`          | Lab 결과 (9,424행) |
| `demo_prescriptions.parquet` | 처방 (6,662행)     |


#### `data/processed/` — 전처리된 전체 MIMIC-IV parquet


| 파일                            | 내용     |
| ----------------------------- | ------ |
| `patients_clean.parquet`      | ~3MB   |
| `admissions_clean.parquet`    | ~16MB  |
| `diagnoses.parquet`           | ~75MB  |
| `labs_clean.parquet`          | ~144MB |
| `prescriptions_clean.parquet` | ~431MB |


> **parquet 읽기 주의**: `dod` 컬럼이 BigQuery `DATE` 타입(`date32[day]`)으로 저장돼 있어 `pd.read_parquet()` 직접 사용 시 오류 발생. 반드시 `dtype_backend='pyarrow'` 옵션 사용.
>
> **날짜 주의**: MIMIC-IV는 환자 식별 방지를 위해 날짜를 2100~2200년대로 이동시킴. Lab 날짜 필터는 현재 시각 기준이 아닌 **최근 입원 admittime 기준**으로 소급 적용.

### `ui/`


| 파일       | 역할                                                                      |
| -------- | ----------------------------------------------------------------------- |
| `app.py` | Streamlit 메인 앱. 사이드바(환자 선택), 목적 버튼, 파이프라인 실행(`run_pipeline`), 3패널 레이아웃. |


#### `ui/components/`


| 파일                   | 역할                              |
| -------------------- | ------------------------------- |
| `flags_panel.py`     | Change Flags 렌더링 (severity별 색상) |
| `summary_panel.py`   | LLM 생성 임상 요약 렌더링                |
| `trend_chart.py`     | Lab 트렌드 스파크라인 차트                |
| `checklist_panel.py` | Must-check 체크리스트 렌더링            |


### `tests/`


| 파일                           | 역할                                                          |
| ---------------------------- | ----------------------------------------------------------- |
| `test_trend.py`              | `compute_trends()` 단위 테스트                                   |
| `test_flags.py`              | `detect_flags()` 단위 테스트                                     |
| `test_prompts.py`            | 프롬프트 빌드 테스트                                                 |
| `fixtures/patient_dm_ckd.py` | 오프라인 테스트용 합성 환자 (ID 99001). T2DM+CKD3+HTN, 180일 Lab 시계열 포함. |


### `scripts/`


| 파일                       | 역할                             |
| ------------------------ | ------------------------------ |
| `cache_demo_patients.py` | BigQuery에서 데모 환자 데이터를 읽어 캐시 생성 |
| `validate_bq_access.py`  | BigQuery 연결 및 접근 권한 검증         |


---

## 데모 환자 3명


| Case | subject_id | 성별/나이  | 주요 진단                                   | 기본 목적    |
| ---- | ---------- | ------ | --------------------------------------- | -------- |
| A    | 18767874   | F, 71세 | T2DM + CKD stage5/ESRD + 투석 + HTN + HF  | rounds   |
| B    | 13303809   | F, 36세 | CAD + old MI + CABG 시행력 + 항응고제 + T1DM   | preop    |
| C    | 12468016   | M, 50세 | CKD + HF + COPD + AKI + Crohn's disease | referral |


---

## 핵심 데이터 모델

```python
PatientRecord
├── subject_id, gender, anchor_age, anchor_year_group, purpose
├── admissions: list[Admission]
│   └── hadm_id, admittime, dischtime, admission_type, hospital_expire_flag
├── diagnoses: list[Diagnosis]
│   └── seq_num, icd_code, icd_version, description
├── labs: list[LabEvent]
│   └── labevent_id, hadm_id, charttime, itemid, lab_label, valuenum, flag
├── prescriptions: list[Prescription]
│   └── drug, starttime, stoptime, route, is_active (property)
└── discharge_notes: list[DischargeNote]
    └── hadm_id, charttime, text_excerpt
```

---

## 환경 변수 (.env)

```
OPENAI_API_KEY=sk-...
BQ_PROJECT=physionet-data
BQ_BILLING_PROJECT=your-gcp-project
GOOGLE_APPLICATION_CREDENTIALS=./secrets/service_account.json
```

---

## 실행 방법

```bash
# 가상환경 활성화
.venv\Scripts\activate

# Streamlit 앱 실행
python -m streamlit run ui/app.py

# 단위 테스트
pytest tests/
```

