"""
MIMIC-IV BigQuery SQL 쿼리 템플릿.
모든 쿼리는 bq_client.run_query()를 통해 실행.
"""
import pandas as pd

from config.settings import BQ_DATASETS, MAX_ADMISSIONS, MAX_DISCHARGE_NOTES
from data.bq_client import bq_param, run_query

HOSP = BQ_DATASETS["hosp"]
NOTE = BQ_DATASETS["note"]


def fetch_demographics_and_admissions(subject_id: int) -> pd.DataFrame:
    """환자 인구통계 + 최근 입원 이력."""
    sql = f"""
    SELECT
        p.subject_id,
        p.gender,
        p.anchor_age,
        p.anchor_year_group,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_type,
        a.admission_location,
        a.discharge_location,
        a.diagnosis,
        a.hospital_expire_flag
    FROM `{HOSP}.patients` p
    JOIN `{HOSP}.admissions` a USING (subject_id)
    WHERE p.subject_id = @subject_id
    ORDER BY a.admittime DESC
    LIMIT @limit
    """
    params = [
        bq_param("subject_id", subject_id, "INT64"),
        bq_param("limit", MAX_ADMISSIONS, "INT64"),
    ]
    return run_query(sql, params)


def fetch_diagnoses(hadm_id: int) -> pd.DataFrame:
    """현재 입원의 진단 목록 (ICD 코드 + 설명)."""
    sql = f"""
    SELECT
        d.hadm_id,
        d.seq_num,
        d.icd_code,
        d.icd_version,
        i.long_title
    FROM `{HOSP}.diagnoses_icd` d
    JOIN `{HOSP}.d_icd_diagnoses` i
        ON d.icd_code = i.icd_code AND d.icd_version = i.icd_version
    WHERE d.hadm_id = @hadm_id
    ORDER BY d.seq_num
    """
    params = [bq_param("hadm_id", hadm_id, "INT64")]
    return run_query(sql, params)


def fetch_labs(subject_id: int, item_ids: list[int], days: int) -> pd.DataFrame:
    """
    subject_id에 대한 lab 시계열 (최근 days일, 지정된 item_id만).
    item_ids는 진단+목적 기반으로 필터링된 목록.
    """
    sql = f"""
    SELECT
        le.labevent_id,
        le.subject_id,
        le.hadm_id,
        le.charttime,
        le.itemid,
        di.label AS lab_label,
        di.fluid,
        di.category,
        le.value,
        le.valuenum,
        le.valueuom,
        le.flag
    FROM `{HOSP}.labevents` le
    JOIN `{HOSP}.d_labitems` di USING (itemid)
    WHERE le.subject_id = @subject_id
      AND le.itemid IN UNNEST(@item_ids)
      AND le.charttime >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
      AND le.valuenum IS NOT NULL
    ORDER BY le.itemid, le.charttime
    """
    params = [
        bq_param("subject_id", subject_id, "INT64"),
        bq_param("item_ids", item_ids, "ARRAY<INT64>"),
        bq_param("days", days, "INT64"),
    ]
    return run_query(sql, params)


def fetch_prescriptions(hadm_id: int) -> pd.DataFrame:
    """현재 입원의 활성 처방 목록."""
    sql = f"""
    SELECT
        drug,
        drug_type,
        starttime,
        stoptime,
        dose_val_rx,
        dose_unit_rx,
        route,
        formulary_drug_cd
    FROM `{HOSP}.prescriptions`
    WHERE hadm_id = @hadm_id
    ORDER BY starttime DESC
    """
    params = [bq_param("hadm_id", hadm_id, "INT64")]
    return run_query(sql, params)


def fetch_discharge_notes(subject_id: int) -> pd.DataFrame:
    """최근 퇴원요약 (MIMIC-IV Note 모듈 별도 승인 필요)."""
    sql = f"""
    SELECT
        subject_id,
        hadm_id,
        charttime,
        SUBSTR(text, 1, 3000) AS text_excerpt
    FROM `{NOTE}.discharge`
    WHERE subject_id = @subject_id
    ORDER BY charttime DESC
    LIMIT @limit
    """
    params = [
        bq_param("subject_id", subject_id, "INT64"),
        bq_param("limit", MAX_DISCHARGE_NOTES, "INT64"),
    ]
    return run_query(sql, params)
