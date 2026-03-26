import os
from dotenv import load_dotenv

load_dotenv()

# --- BigQuery ---
BQ_PROJECT = os.getenv("BQ_PROJECT", "physionet-data")
BQ_BILLING_PROJECT = os.getenv("BQ_BILLING_PROJECT", "")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

BQ_DATASETS = {
    "hosp": f"{BQ_PROJECT}.mimiciv_hosp",
    "icu": f"{BQ_PROJECT}.mimiciv_icu",
    "note": f"{BQ_PROJECT}.mimiciv_note",
}

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_JUDGE_MODEL = "gpt-4o"  # LLM judge for evaluation

# --- App ---
CACHE_DIR = os.getenv("CACHE_DIR", "./data/cache")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Pipeline ---
LAB_HISTORY_DAYS = 180          # 기본 lab 조회 기간
LAB_HISTORY_DAYS_SHORT = 90     # 토큰 예산 초과 시 단축
MAX_ADMISSIONS = 10             # 최근 입원 이력 최대 수
MAX_MEDICATIONS = 15            # 처방 최대 수 (토큰 절약)
MAX_DISCHARGE_NOTES = 2         # 퇴원요약 최대 수
PROMPT_TOKEN_BUDGET = 6000      # 이 초과 시 데이터 축소
