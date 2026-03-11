"""
BigQuery 연결 확인 스크립트.

실행: python scripts/validate_bq_access.py

MIMIC-IV 접근 가능 여부를 빠르게 검증.
"""
import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import BQ_PROJECT, BQ_BILLING_PROJECT, GOOGLE_APPLICATION_CREDENTIALS


def main():
    print("=" * 50)
    print("MIMIC-IV BigQuery Access Validation")
    print("=" * 50)

    # 1. 환경 변수 체크
    print("\n[1] 환경 변수 확인")
    print(f"  BQ_PROJECT: {BQ_PROJECT}")
    print(f"  BQ_BILLING_PROJECT: {BQ_BILLING_PROJECT or '⚠️  미설정'}")
    print(f"  GOOGLE_APPLICATION_CREDENTIALS: {GOOGLE_APPLICATION_CREDENTIALS or '⚠️  미설정'}")

    if not BQ_BILLING_PROJECT:
        print("\n❌ BQ_BILLING_PROJECT가 .env에 설정되지 않았습니다.")
        print("   .env.example을 참고해 .env 파일을 만드세요.")
        sys.exit(1)

    if GOOGLE_APPLICATION_CREDENTIALS and not os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
        print(f"\n⚠️  Service account 파일이 없습니다: {GOOGLE_APPLICATION_CREDENTIALS}")
        print("   ADC(Application Default Credentials) 로 시도합니다.")

    # 2. 클라이언트 초기화
    print("\n[2] BigQuery 클라이언트 초기화")
    try:
        from data.bq_client import get_bq_client
        client = get_bq_client()
        if client is None:
            print("  ❌ 클라이언트 초기화 실패")
            sys.exit(1)
        print("  ✅ 클라이언트 초기화 성공")
    except Exception as e:
        print(f"  ❌ 오류: {e}")
        sys.exit(1)

    # 3. physionet-data 접근 테스트
    print("\n[3] MIMIC-IV 테이블 접근 테스트")
    test_queries = [
        (
            "mimiciv_hosp.patients",
            f"SELECT COUNT(*) as cnt FROM `{BQ_PROJECT}.mimiciv_hosp.patients` LIMIT 1"
        ),
        (
            "mimiciv_hosp.labevents",
            f"SELECT COUNT(*) as cnt FROM `{BQ_PROJECT}.mimiciv_hosp.labevents` LIMIT 1"
        ),
    ]

    for table_name, sql in test_queries:
        try:
            df = client.query(sql).to_dataframe()
            print(f"  ✅ {table_name} — 접근 가능")
        except Exception as e:
            print(f"  ❌ {table_name} — 접근 실패: {e}")

    # 4. Note 모듈 (선택적)
    print("\n[4] MIMIC-IV Note 모듈 (선택적)")
    try:
        sql = f"SELECT COUNT(*) as cnt FROM `{BQ_PROJECT}.mimiciv_note.discharge` LIMIT 1"
        df = client.query(sql).to_dataframe()
        print("  ✅ mimiciv_note.discharge — 접근 가능")
    except Exception as e:
        print(f"  ⚠️  mimiciv_note.discharge — 접근 불가 (별도 PhysioNet 승인 필요)")
        print(f"     오류: {e}")

    print("\n" + "=" * 50)
    print("검증 완료. 다음 단계: scripts/cache_demo_patients.py 실행")
    print("=" * 50)


if __name__ == "__main__":
    main()
