"""
BigQuery 클라이언트 싱글턴.

BQ 자격증명이 없는 경우 gracefully 실패하며,
fixture 데이터로 오프라인 작업이 가능하도록 설계.
"""
import logging
import os
from functools import lru_cache
from typing import Optional

import pandas as pd

from config.settings import BQ_BILLING_PROJECT, GOOGLE_APPLICATION_CREDENTIALS

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_bq_client():
    """BigQuery Client 싱글턴 반환. 자격증명 없으면 None."""
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_APPLICATION_CREDENTIALS,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            client = bigquery.Client(
                project=BQ_BILLING_PROJECT,
                credentials=credentials,
            )
        else:
            # ADC (Application Default Credentials) 시도
            client = bigquery.Client(project=BQ_BILLING_PROJECT)

        logger.info(f"BigQuery client initialized (billing project: {BQ_BILLING_PROJECT})")
        return client

    except Exception as e:
        logger.warning(f"BigQuery client unavailable: {e}. Falling back to fixture data.")
        return None


def run_query(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    """
    SQL을 실행하고 DataFrame을 반환.
    BQ가 없으면 RuntimeError 발생 → 호출부에서 캐시로 fallback.
    """
    client = get_bq_client()
    if client is None:
        raise RuntimeError("BigQuery client not available")

    try:
        from google.cloud import bigquery

        job_config = bigquery.QueryJobConfig(query_parameters=params or [])
        df = client.query(sql, job_config=job_config).to_dataframe()
        return df
    except Exception as e:
        logger.error(f"BigQuery query failed: {e}")
        raise


def bq_param(name: str, value, param_type: str = "INT64"):
    """BigQuery 파라미터 헬퍼."""
    from google.cloud import bigquery

    type_map = {
        "INT64": bigquery.ScalarQueryParameter,
        "STRING": bigquery.ScalarQueryParameter,
        "ARRAY<INT64>": bigquery.ArrayQueryParameter,
    }
    if param_type == "ARRAY<INT64>":
        return bigquery.ArrayQueryParameter(name, "INT64", value)
    return bigquery.ScalarQueryParameter(name, param_type, value)
