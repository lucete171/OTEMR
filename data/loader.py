"""
PatientRecord 데이터클래스와 멀티 테이블 fetch 오케스트레이터.

사용 예:
    from data.loader import load_patient
    record = load_patient(subject_id=12345, purpose="rounds")
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from config.lab_profiles import get_item_ids_for_purpose_and_diagnoses
from config.settings import LAB_HISTORY_DAYS
from data import cache, queries

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 데이터 모델
# ──────────────────────────────────────────────

@dataclass
class Admission:
    hadm_id: int
    admittime: datetime
    dischtime: Optional[datetime]
    admission_type: str
    diagnosis: str
    hospital_expire_flag: int


@dataclass
class Diagnosis:
    seq_num: int
    icd_code: str
    icd_version: int
    description: str


@dataclass
class LabEvent:
    labevent_id: int
    hadm_id: Optional[int]
    charttime: datetime
    itemid: int
    lab_label: str
    value: str
    valuenum: float
    valueuom: str
    flag: Optional[str]  # "abnormal" 등


@dataclass
class Prescription:
    drug: str
    drug_type: str
    starttime: Optional[datetime]
    stoptime: Optional[datetime]
    dose_val_rx: Optional[str]
    dose_unit_rx: Optional[str]
    route: Optional[str]

    @property
    def is_active(self) -> bool:
        return self.stoptime is None or self.stoptime > datetime.now()


@dataclass
class DischargeNote:
    hadm_id: Optional[int]
    charttime: Optional[datetime]
    text_excerpt: str


@dataclass
class PatientRecord:
    subject_id: int
    gender: str
    anchor_age: int
    anchor_year_group: str
    purpose: str  # "rounds" | "preop" | "referral"

    admissions: list[Admission] = field(default_factory=list)
    diagnoses: list[Diagnosis] = field(default_factory=list)
    labs: list[LabEvent] = field(default_factory=list)
    prescriptions: list[Prescription] = field(default_factory=list)
    discharge_notes: list[DischargeNote] = field(default_factory=list)

    @property
    def current_hadm_id(self) -> Optional[int]:
        return self.admissions[0].hadm_id if self.admissions else None

    @property
    def icd_prefixes(self) -> list[str]:
        """ICD 코드 앞 3자리 목록 (진단 기반 lab 선택용)."""
        return list({d.icd_code[:3] for d in self.diagnoses})

    @property
    def active_prescriptions(self) -> list[Prescription]:
        return [p for p in self.prescriptions if p.is_active]


# ──────────────────────────────────────────────
# 로더
# ──────────────────────────────────────────────

def load_patient(
    subject_id: int,
    purpose: str,
    lab_days: int = LAB_HISTORY_DAYS,
    use_cache: bool = True,
    include_notes: bool = False,
) -> PatientRecord:
    """
    MIMIC-IV에서 환자 데이터를 로드하고 PatientRecord를 반환.

    캐시가 있으면 캐시에서 로드 (BQ 쿼리 불필요).
    BQ 없으면 RuntimeError → 호출부에서 fixture로 fallback.

    Args:
        subject_id: MIMIC-IV subject_id
        purpose: "rounds" | "preop" | "referral"
        lab_days: 조회할 lab 기간 (일)
        use_cache: 디스크 캐시 사용 여부
        include_notes: 퇴원요약 포함 여부 (Note 모듈 승인 필요)
    """
    cache_key = f"{subject_id}_{purpose}_{lab_days}"

    if use_cache:
        cached = cache.load(cache_key)
        if cached is not None:
            logger.info(f"Loaded patient {subject_id} from cache")
            return cached

    logger.info(f"Fetching patient {subject_id} from BigQuery (purpose={purpose})")

    # 1. 인구통계 + 입원 이력
    demo_df = queries.fetch_demographics_and_admissions(subject_id)
    if demo_df.empty:
        raise ValueError(f"Patient {subject_id} not found in MIMIC-IV")

    admissions = _parse_admissions(demo_df)
    first_row = demo_df.iloc[0]

    # 2. 진단 (현 입원)
    current_hadm_id = admissions[0].hadm_id if admissions else None
    diagnoses = []
    if current_hadm_id:
        diag_df = queries.fetch_diagnoses(current_hadm_id)
        diagnoses = _parse_diagnoses(diag_df)

    # 3. Lab (목적 + 진단 기반 필터)
    icd_prefixes = [d.icd_code[:3] for d in diagnoses]
    item_ids = get_item_ids_for_purpose_and_diagnoses(purpose, icd_prefixes)
    lab_df = queries.fetch_labs(subject_id, item_ids, lab_days)
    labs = _parse_labs(lab_df)

    # 4. 처방
    prescriptions = []
    if current_hadm_id:
        rx_df = queries.fetch_prescriptions(current_hadm_id)
        prescriptions = _parse_prescriptions(rx_df)

    # 5. 퇴원요약 (선택)
    discharge_notes = []
    if include_notes:
        try:
            note_df = queries.fetch_discharge_notes(subject_id)
            discharge_notes = _parse_notes(note_df)
        except Exception as e:
            logger.warning(f"Could not fetch discharge notes: {e}")

    record = PatientRecord(
        subject_id=subject_id,
        gender=first_row.get("gender", ""),
        anchor_age=int(first_row.get("anchor_age", 0)),
        anchor_year_group=str(first_row.get("anchor_year_group", "")),
        purpose=purpose,
        admissions=admissions,
        diagnoses=diagnoses,
        labs=labs,
        prescriptions=prescriptions,
        discharge_notes=discharge_notes,
    )

    if use_cache:
        cache.save(cache_key, record)
        logger.info(f"Cached patient {subject_id}")

    return record


# ──────────────────────────────────────────────
# 파싱 헬퍼
# ──────────────────────────────────────────────

def _parse_admissions(df: pd.DataFrame) -> list[Admission]:
    result = []
    for _, row in df.drop_duplicates("hadm_id").iterrows():
        result.append(Admission(
            hadm_id=int(row["hadm_id"]),
            admittime=pd.to_datetime(row["admittime"]),
            dischtime=pd.to_datetime(row["dischtime"]) if pd.notna(row.get("dischtime")) else None,
            admission_type=str(row.get("admission_type", "")),
            diagnosis=str(row.get("diagnosis", "")),
            hospital_expire_flag=int(row.get("hospital_expire_flag", 0)),
        ))
    return result


def _parse_diagnoses(df: pd.DataFrame) -> list[Diagnosis]:
    result = []
    for _, row in df.iterrows():
        result.append(Diagnosis(
            seq_num=int(row["seq_num"]),
            icd_code=str(row["icd_code"]),
            icd_version=int(row["icd_version"]),
            description=str(row.get("long_title", "")),
        ))
    return result


def _parse_labs(df: pd.DataFrame) -> list[LabEvent]:
    result = []
    for _, row in df.iterrows():
        result.append(LabEvent(
            labevent_id=int(row.get("labevent_id", 0)),
            hadm_id=int(row["hadm_id"]) if pd.notna(row.get("hadm_id")) else None,
            charttime=pd.to_datetime(row["charttime"]),
            itemid=int(row["itemid"]),
            lab_label=str(row.get("lab_label", "")),
            value=str(row.get("value", "")),
            valuenum=float(row["valuenum"]),
            valueuom=str(row.get("valueuom", "")),
            flag=str(row["flag"]) if pd.notna(row.get("flag")) else None,
        ))
    return result


def _parse_prescriptions(df: pd.DataFrame) -> list[Prescription]:
    result = []
    for _, row in df.iterrows():
        result.append(Prescription(
            drug=str(row.get("drug", "")),
            drug_type=str(row.get("drug_type", "")),
            starttime=pd.to_datetime(row["starttime"]) if pd.notna(row.get("starttime")) else None,
            stoptime=pd.to_datetime(row["stoptime"]) if pd.notna(row.get("stoptime")) else None,
            dose_val_rx=str(row["dose_val_rx"]) if pd.notna(row.get("dose_val_rx")) else None,
            dose_unit_rx=str(row["dose_unit_rx"]) if pd.notna(row.get("dose_unit_rx")) else None,
            route=str(row["route"]) if pd.notna(row.get("route")) else None,
        ))
    return result


def _parse_notes(df: pd.DataFrame) -> list[DischargeNote]:
    result = []
    for _, row in df.iterrows():
        result.append(DischargeNote(
            hadm_id=int(row["hadm_id"]) if pd.notna(row.get("hadm_id")) else None,
            charttime=pd.to_datetime(row["charttime"]) if pd.notna(row.get("charttime")) else None,
            text_excerpt=str(row.get("text_excerpt", "")),
        ))
    return result


# ──────────────────────────────────────────────
# Parquet 로더
# ──────────────────────────────────────────────

DEMO_DIR = Path(__file__).parent / "demo"
PROCESSED_DIR = Path(__file__).parent / "processed"

_PARQUET_FILE_MAP = {
    # (is_demo, table) → filename
    (True,  "patients"):      "demo_patients.parquet",
    (True,  "admissions"):    "demo_admissions.parquet",
    (True,  "diagnoses"):     "demo_diagnoses.parquet",
    (True,  "labs"):          "demo_labs.parquet",
    (True,  "prescriptions"): "demo_prescriptions.parquet",
    (False, "patients"):      "patients_clean.parquet",
    (False, "admissions"):    "admissions_clean.parquet",
    (False, "diagnoses"):     "diagnoses.parquet",
    (False, "labs"):          "labs_clean.parquet",
    (False, "prescriptions"): "prescriptions_clean.parquet",
}


def _read_parquet(data_dir: Path, table: str) -> pd.DataFrame:
    """parquet 파일을 읽어 DataFrame으로 반환.
    dtype_backend='pyarrow'를 사용해 date32[day](dbdate) 타입 오류를 방지.
    """
    is_demo = "demo" in data_dir.name
    filename = _PARQUET_FILE_MAP[(is_demo, table)]
    path = data_dir / filename
    return pd.read_parquet(path, dtype_backend="pyarrow")


def load_patient_from_parquet(
    subject_id: int,
    purpose: str,
    data_dir: Path,
    lab_days: int = LAB_HISTORY_DAYS,
) -> PatientRecord:
    """
    parquet 파일에서 환자 데이터를 로드하고 PatientRecord를 반환.

    Args:
        subject_id: MIMIC-IV subject_id
        purpose: "rounds" | "preop" | "referral"
        data_dir: DEMO_DIR 또는 PROCESSED_DIR
        lab_days: 조회할 lab 기간 (일). 가장 최근 admittime 기준으로 소급.
    """
    # 1. 인구통계
    pts_df = _read_parquet(data_dir, "patients")
    pts_row = pts_df[pts_df["subject_id"] == subject_id]
    if pts_row.empty:
        raise ValueError(f"Patient {subject_id} not found in {data_dir}")
    first = pts_row.iloc[0]

    # 2. 입원 이력 (최신순)
    adm_df = _read_parquet(data_dir, "admissions")
    adm_df = adm_df[adm_df["subject_id"] == subject_id].copy()
    adm_df["admittime"] = pd.to_datetime(adm_df["admittime"])
    adm_df = adm_df.sort_values("admittime", ascending=False)
    admissions = _parse_admissions(adm_df)

    # 3. 진단 (가장 최근 입원)
    current_hadm_id = admissions[0].hadm_id if admissions else None
    diagnoses = []
    if current_hadm_id:
        diag_df = _read_parquet(data_dir, "diagnoses")
        diag_df = diag_df[
            (diag_df["subject_id"] == subject_id) &
            (diag_df["hadm_id"] == current_hadm_id)
        ]
        diagnoses = _parse_diagnoses(diag_df)

    # 4. Lab (목적 + 진단 기반 item_ids 필터, admittime 기준 날짜 필터)
    icd_prefixes = [d.icd_code[:3] for d in diagnoses]
    item_ids = get_item_ids_for_purpose_and_diagnoses(purpose, icd_prefixes)

    lab_df = _read_parquet(data_dir, "labs")
    lab_df = lab_df[lab_df["subject_id"] == subject_id].copy()
    lab_df["charttime"] = pd.to_datetime(lab_df["charttime"])

    if admissions:
        cutoff = admissions[0].admittime - timedelta(days=lab_days)
        lab_df = lab_df[lab_df["charttime"] >= cutoff]

    lab_df = lab_df[lab_df["itemid"].isin(item_ids)]
    labs = _parse_labs(lab_df)

    # 5. 처방 (가장 최근 입원)
    prescriptions = []
    if current_hadm_id:
        rx_df = _read_parquet(data_dir, "prescriptions")
        rx_df = rx_df[
            (rx_df["subject_id"] == subject_id) &
            (rx_df["hadm_id"] == current_hadm_id)
        ].copy()

        # MIMIC 날짜는 2100년대로 이동돼 있어 stoptime > datetime.now() 가 항상 True.
        # parquet의 사전 계산된 is_active 컬럼을 이용해 보정.
        if "is_active" in rx_df.columns:
            mask_inactive = rx_df["is_active"] == False  # noqa: E712
            rx_df.loc[mask_inactive, "stoptime"] = datetime(2000, 1, 1)

        prescriptions = _parse_prescriptions(rx_df)

    return PatientRecord(
        subject_id=subject_id,
        gender=str(first.get("gender", "")),
        anchor_age=int(first.get("anchor_age", 0)),
        anchor_year_group=str(first.get("anchor_year_group", "")),
        purpose=purpose,
        admissions=admissions,
        diagnoses=diagnoses,
        labs=labs,
        prescriptions=prescriptions,
    )


def load_demo_patient(
    subject_id: int,
    purpose: str,
    lab_days: int = LAB_HISTORY_DAYS,
) -> PatientRecord:
    """data/demo/ parquet에서 환자 로드."""
    return load_patient_from_parquet(subject_id, purpose, DEMO_DIR, lab_days)


def load_processed_patient(
    subject_id: int,
    purpose: str,
    lab_days: int = LAB_HISTORY_DAYS,
) -> PatientRecord:
    """data/processed/ parquet에서 환자 로드."""
    return load_patient_from_parquet(subject_id, purpose, PROCESSED_DIR, lab_days)
