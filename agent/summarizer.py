"""
GPT-4o-mini API 호출 래퍼.

- tiktoken으로 토큰 예산 관리
- json_object 모드로 파싱 가능한 응답 보장
- Pydantic으로 스키마 검증
- 재시도 로직 포함
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from openai import OpenAI

from agent.output_schema import AgentOutput
from agent.prompts import build_system_prompt
from config.settings import OPENAI_API_KEY, OPENAI_MODEL, PROMPT_TOKEN_BUDGET

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def generate(
    user_context: str,
    purpose: str,
    max_retries: int = 2,
) -> AgentOutput:
    """
    GPT-4o-mini에 요청하고 AgentOutput을 반환.

    Args:
        user_context: context_builder.build_user_context() 결과
        purpose: "rounds" | "preop" | "referral"
        max_retries: 파싱 실패 시 재시도 횟수
    """
    system_prompt = build_system_prompt(purpose)
    trimmed_context = _trim_to_budget(user_context, system_prompt)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trimmed_context},
    ]

    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Calling GPT-4o-mini (purpose={purpose}, attempt={attempt + 1})")
            response = _get_client().chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,  # 임상 정확성 우선 — 창의성 낮게
                max_tokens=2000,
            )
            raw = response.choices[0].message.content
            logger.debug(f"Raw response: {raw[:200]}...")

            parsed = json.loads(raw)
            output = AgentOutput.model_validate(parsed)
            return output

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
            last_exc = e
        except Exception as e:
            logger.warning(f"GPT-4o-mini call failed (attempt {attempt + 1}): {type(e).__name__}: {e}")
            last_exc = e
            if attempt < max_retries:
                time.sleep(1)

    raise RuntimeError(f"GPT-4o-mini failed after {max_retries + 1} attempts") from last_exc


def enrich_checklist_reasons(
    checklist_items: list[dict],
    patient_context: str,
) -> list[dict]:
    """
    Rule-based 체크리스트의 reason을 LLM으로 보강.
    (간결하고 임상적으로 설득력 있는 이유 문장 생성)

    별도 API 호출 — generate()와 분리해서 선택적으로 사용.
    """
    if not checklist_items:
        return checklist_items

    items_str = "\n".join(
        f"- {item['item']}: {item['reason']}" for item in checklist_items
    )

    prompt = f"""다음은 환자 데이터에서 rule-based로 생성된 must-check 항목 목록입니다.
각 항목의 reason을 임상적으로 더 설득력 있고 구체적으로 다듬어 주세요.
환자 컨텍스트를 참고하되, 데이터에 없는 내용은 추가하지 마세요.

환자 컨텍스트:
{patient_context[:2000]}

체크리스트 항목:
{items_str}

JSON 배열로 반환하세요:
[{{"item": "...", "reason": "...", "urgency": "..."}}]
"""

    try:
        response = _get_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1000,
        )
        raw = response.choices[0].message.content
        enriched = json.loads(raw)
        if isinstance(enriched, list):
            return enriched
        if isinstance(enriched, dict) and len(enriched) == 1:
            return list(enriched.values())[0]
    except Exception as e:
        logger.warning(f"Checklist enrichment failed: {e}. Using original.")

    return checklist_items


def _trim_to_budget(user_context: str, system_prompt: str) -> str:
    """
    토큰 예산 초과 시 user_context를 점진적으로 축소.
    tiktoken이 없으면 문자 수 기반 근사값 사용.
    """
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        system_tokens = len(enc.encode(system_prompt))
        context_tokens = len(enc.encode(user_context))
        total = system_tokens + context_tokens

        if total <= PROMPT_TOKEN_BUDGET:
            return user_context

        logger.warning(f"Token budget exceeded ({total} > {PROMPT_TOKEN_BUDGET}). Trimming context.")
        # 퇴원요약 제거 (가장 큰 블록)
        if "=== RECENT DISCHARGE NOTES" in user_context:
            user_context = user_context[:user_context.index("=== RECENT DISCHARGE NOTES")]
            context_tokens = len(enc.encode(user_context))
            if system_tokens + context_tokens <= PROMPT_TOKEN_BUDGET:
                return user_context

        # 그래도 초과 → 트렌드 포인트 제거 (Trend: 라인 삭제)
        lines = user_context.split("\n")
        trimmed = [l for l in lines if not l.strip().startswith("Trend:")]
        user_context = "\n".join(trimmed)

    except ImportError:
        # tiktoken 없으면 문자 수 근사 (1토큰 ≈ 4자)
        if len(system_prompt + user_context) > PROMPT_TOKEN_BUDGET * 4:
            user_context = user_context[:PROMPT_TOKEN_BUDGET * 3]

    return user_context
