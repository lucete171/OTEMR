"""
디스크 캐시 (pickle).
BQ 쿼리 결과를 로컬에 저장해 데모 시 빠른 로딩 보장.
"""
import logging
import os
import pickle
from typing import Optional

from config.settings import CACHE_DIR

logger = logging.getLogger(__name__)


def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe_key = key.replace("/", "_").replace("\\", "_")
    return os.path.join(CACHE_DIR, f"{safe_key}.pkl")


def save(key: str, obj) -> None:
    path = _cache_path(key)
    with open(path, "wb") as f:
        pickle.dump(obj, f)
    logger.debug(f"Cached: {path}")


def load(key: str) -> Optional[object]:
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"Cache load failed for {key}: {e}")
        return None


def exists(key: str) -> bool:
    return os.path.exists(_cache_path(key))


def clear(key: str) -> None:
    path = _cache_path(key)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"Cache cleared: {path}")


def list_cached() -> list[str]:
    if not os.path.exists(CACHE_DIR):
        return []
    return [f.replace(".pkl", "") for f in os.listdir(CACHE_DIR) if f.endswith(".pkl")]
