"""
Fixture: DM + CKD 진행 환자 (Case A).

BQ 없이 오프라인 테스트/데모에 사용.
MIMIC-IV 데이터 구조를 모방한 합성 데이터.
"""
from datetime import datetime, timedelta

from data.loader import (
    Admission, Diagnosis, DischargeNote, LabEvent,
    PatientRecord, Prescription,
)

BASE_DATE = datetime(2023, 10, 1)


def make_lab(item_id: int, label: str, value: float, unit: str,
             days_ago: int, hadm_id: int = 10001, flag: str = None) -> LabEvent:
    return LabEvent(
        labevent_id=item_id * 1000 + days_ago,
        hadm_id=hadm_id,
        charttime=BASE_DATE - timedelta(days=days_ago),
        itemid=item_id,
        lab_label=label,
        value=str(value),
        valuenum=value,
        valueuom=unit,
        flag=flag,
    )


def get_fixture() -> PatientRecord:
    """DM + CKD 환자 fixture 반환."""

    admissions = [
        Admission(
            hadm_id=10001,
            admittime=BASE_DATE - timedelta(days=3),
            dischtime=None,
            admission_type="URGENT",
            diagnosis="CHRONIC KIDNEY DISEASE WITH DIABETES",
            hospital_expire_flag=0,
        ),
        Admission(
            hadm_id=10000,
            admittime=BASE_DATE - timedelta(days=90),
            dischtime=BASE_DATE - timedelta(days=85),
            admission_type="ELECTIVE",
            diagnosis="DIABETES MELLITUS FOLLOW-UP",
            hospital_expire_flag=0,
        ),
        Admission(
            hadm_id=9999,
            admittime=BASE_DATE - timedelta(days=180),
            dischtime=BASE_DATE - timedelta(days=175),
            admission_type="ELECTIVE",
            diagnosis="HYPERTENSION MANAGEMENT",
            hospital_expire_flag=0,
        ),
    ]

    diagnoses = [
        Diagnosis(seq_num=1, icd_code="E11.9", icd_version=10, description="Type 2 diabetes mellitus without complications"),
        Diagnosis(seq_num=2, icd_code="N18.3", icd_version=10, description="Chronic kidney disease, stage 3 (moderate)"),
        Diagnosis(seq_num=3, icd_code="I10",   icd_version=10, description="Essential (primary) hypertension"),
        Diagnosis(seq_num=4, icd_code="E78.5", icd_version=10, description="Hyperlipidemia, unspecified"),
    ]

    # Creatinine 3회 입원에 걸쳐 상승 (1.2 → 1.6 → 2.1)
    labs = [
        # Creatinine — 180일 전 입원
        make_lab(50912, "Creatinine", 1.2, "mg/dL", 178),
        make_lab(50912, "Creatinine", 1.3, "mg/dL", 175),
        # Creatinine — 90일 전 입원
        make_lab(50912, "Creatinine", 1.5, "mg/dL", 88),
        make_lab(50912, "Creatinine", 1.6, "mg/dL", 85, flag="abnormal"),
        # Creatinine — 현재 입원
        make_lab(50912, "Creatinine", 1.9, "mg/dL", 3, flag="abnormal"),
        make_lab(50912, "Creatinine", 2.1, "mg/dL", 1, flag="abnormal"),

        # BUN
        make_lab(51006, "BUN", 18, "mg/dL", 178),
        make_lab(51006, "BUN", 22, "mg/dL", 88),
        make_lab(51006, "BUN", 31, "mg/dL", 3, flag="abnormal"),
        make_lab(51006, "BUN", 35, "mg/dL", 1, flag="abnormal"),

        # Hemoglobin — 서서히 감소
        make_lab(51222, "Hemoglobin", 12.5, "g/dL", 178),
        make_lab(51222, "Hemoglobin", 11.8, "g/dL", 88),
        make_lab(51222, "Hemoglobin", 10.9, "g/dL", 3),
        make_lab(51222, "Hemoglobin", 10.7, "g/dL", 1, flag="abnormal"),

        # HbA1c (6개월 전 측정 — gap 있음)
        make_lab(50852, "Hemoglobin A1c", 8.2, "%", 175),

        # Potassium (현재 입원 — 경계치)
        make_lab(50971, "Potassium", 4.1, "mEq/L", 178),
        make_lab(50971, "Potassium", 4.5, "mEq/L", 88),
        make_lab(50971, "Potassium", 5.1, "mEq/L", 3, flag="abnormal"),
        make_lab(50971, "Potassium", 5.3, "mEq/L", 1, flag="abnormal"),

        # Sodium
        make_lab(50983, "Sodium", 139, "mEq/L", 88),
        make_lab(50983, "Sodium", 137, "mEq/L", 1),

        # Glucose
        make_lab(50931, "Glucose", 185, "mg/dL", 88),
        make_lab(50931, "Glucose", 210, "mg/dL", 3, flag="abnormal"),
        make_lab(50931, "Glucose", 198, "mg/dL", 1, flag="abnormal"),

        # WBC
        make_lab(51301, "WBC", 7.2, "K/uL", 88),
        make_lab(51301, "WBC", 8.1, "K/uL", 1),

        # INR
        make_lab(51237, "INR", 1.0, "", 88),
        make_lab(51237, "INR", 1.1, "", 1),
    ]

    prescriptions = [
        Prescription(
            drug="Metformin",
            drug_type="MAIN",
            starttime=BASE_DATE - timedelta(days=365),
            stoptime=None,
            dose_val_rx="500",
            dose_unit_rx="mg",
            route="PO",
        ),
        Prescription(
            drug="Amlodipine",
            drug_type="MAIN",
            starttime=BASE_DATE - timedelta(days=365),
            stoptime=None,
            dose_val_rx="5",
            dose_unit_rx="mg",
            route="PO",
        ),
        Prescription(
            drug="Lisinopril",
            drug_type="MAIN",
            starttime=BASE_DATE - timedelta(days=180),
            stoptime=None,
            dose_val_rx="10",
            dose_unit_rx="mg",
            route="PO",
        ),
        Prescription(
            drug="Atorvastatin",
            drug_type="MAIN",
            starttime=BASE_DATE - timedelta(days=365),
            stoptime=None,
            dose_val_rx="40",
            dose_unit_rx="mg",
            route="PO",
        ),
        Prescription(
            drug="Normal Saline",
            drug_type="MAIN",
            starttime=BASE_DATE - timedelta(days=3),
            stoptime=None,
            dose_val_rx="1000",
            dose_unit_rx="mL",
            route="IV",
        ),
    ]

    return PatientRecord(
        subject_id=99001,
        gender="M",
        anchor_age=65,
        anchor_year_group="2015 - 2019",
        purpose="rounds",
        admissions=admissions,
        diagnoses=diagnoses,
        labs=labs,
        prescriptions=prescriptions,
        discharge_notes=[],
    )
