"""
Demo 환자 데이터를 BigQuery에서 조회하고 로컬 캐시에 저장.

실행: python scripts/cache_demo_patients.py

BQ 접근 후 한 번만 실행하면 됨.
이후 Streamlit 데모는 캐시에서 즉시 로드 (<2초).

subject_id 선정 전략:
  - Case A (DM+CKD): DM + N18 진단 + 3회 이상 입원 + Creatinine 상승 이력
  - Case B (Pre-op): CAD + 항응고제 복용 환자
  - Case C (Referral): 복잡 다계통 (간경화 등)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from data.bq_client import get_bq_client, run_query
from data.loader import load_patient
from data.demo_patients import DEMO_CASES, get_case
from config.settings import BQ_PROJECT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HOSP = f"{BQ_PROJECT}.mimiciv_hosp"


# ──────────────────────────────────────────────
# 케이스별 환자 검색 쿼리
# ──────────────────────────────────────────────

def find_dm_ckd_patient() -> int:
    """Case A: DM + CKD, Creatinine 상승 이력 있는 환자."""
    sql = f"""
    WITH dm_ckd AS (
        SELECT DISTINCT d1.subject_id
        FROM `{HOSP}.diagnoses_icd` d1
        JOIN `{HOSP}.diagnoses_icd` d2 USING (hadm_id)
        WHERE d1.icd_code LIKE 'E11%'
          AND d2.icd_code LIKE 'N18%'
    ),
    multi_admit AS (
        SELECT subject_id
        FROM `{HOSP}.admissions`
        WHERE subject_id IN (SELECT subject_id FROM dm_ckd)
        GROUP BY subject_id
        HAVING COUNT(*) >= 3
    )
    SELECT subject_id FROM multi_admit LIMIT 1
    """
    df = run_query(sql)
    if df.empty:
        raise ValueError("DM+CKD 환자를 찾지 못했습니다.")
    return int(df.iloc[0]["subject_id"])


def find_preop_patient() -> int:
    """Case B: CAD + 항응고제 복용 환자."""
    sql = f"""
    WITH cad AS (
        SELECT DISTINCT hadm_id, subject_id
        FROM `{HOSP}.diagnoses_icd`
        WHERE icd_code LIKE 'I25%'
    ),
    anticoag AS (
        SELECT DISTINCT hadm_id
        FROM `{HOSP}.prescriptions`
        WHERE LOWER(drug) IN ('warfarin', 'heparin', 'rivaroxaban', 'apixaban', 'dabigatran')
    )
    SELECT c.subject_id
    FROM cad c
    JOIN anticoag a USING (hadm_id)
    LIMIT 1
    """
    df = run_query(sql)
    if df.empty:
        raise ValueError("CAD+항응고제 환자를 찾지 못했습니다.")
    return int(df.iloc[0]["subject_id"])


def find_referral_patient() -> int:
    """Case C: 간경화 + 복수 환자."""
    sql = f"""
    WITH cirrhosis AS (
        SELECT DISTINCT d1.subject_id
        FROM `{HOSP}.diagnoses_icd` d1
        JOIN `{HOSP}.diagnoses_icd` d2 USING (hadm_id)
        WHERE d1.icd_code LIKE 'K74%'
          AND d2.icd_code LIKE 'R18%'
    )
    SELECT subject_id FROM cirrhosis LIMIT 1
    """
    df = run_query(sql)
    if df.empty:
        raise ValueError("간경화+복수 환자를 찾지 못했습니다.")
    return int(df.iloc[0]["subject_id"])


CASE_FINDERS = {
    "A": (find_dm_ckd_patient, "rounds"),
    "B": (find_preop_patient, "preop"),
    "C": (find_referral_patient, "referral"),
}


def main():
    client = get_bq_client()
    if client is None:
        print("❌ BigQuery 클라이언트를 초기화할 수 없습니다.")
        print("   먼저 scripts/validate_bq_access.py를 실행하세요.")
        sys.exit(1)

    print("Demo 환자 캐시 생성 시작")
    print("=" * 50)

    for case_id, (finder_fn, purpose) in CASE_FINDERS.items():
        case = get_case(case_id)
        print(f"\n[Case {case_id}] {case.label}")

        try:
            subject_id = finder_fn()
            print(f"  Found subject_id: {subject_id}")

            # 로드 + 캐시 저장
            record = load_patient(
                subject_id=subject_id,
                purpose=purpose,
                use_cache=True,
                include_notes=False,
            )
            print(f"  ✅ 캐시 저장 완료 — {len(record.labs)} lab events, {len(record.admissions)} admissions")

            # demo_patients.py의 subject_id 업데이트 안내
            print(f"  → demo_patients.py의 Case {case_id} subject_id를 {subject_id}로 업데이트하세요.")

        except Exception as e:
            print(f"  ❌ 실패: {e}")

    print("\n" + "=" * 50)
    print("캐시 생성 완료. 이제 streamlit run ui/app.py 를 실행하세요.")


if __name__ == "__main__":
    main()
