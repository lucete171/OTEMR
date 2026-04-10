"""
LLM-as-Judge: GPT-4o를 이용한 임상 브리핑 품질 채점.

피평가 모델(GPT-4o-mini)보다 상위 모델로 독립 평가.
5개 차원 각 1~5점, 총 25점 만점.
"""
from __future__ import annotations

import json
import logging

from openai import OpenAI

from agent.output_schema import AgentOutput
from config.settings import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Judge LLM — 피평가 모델(GPT-4o-mini)보다 상위 모델 사용
JUDGE_MODEL = "gpt-4o"

DIMENSIONS = [
    "factual_groundedness",
    "clinical_completeness",
    "hallucination_free",
    "purpose_alignment",
    "actionability",
]

DIM_LABELS_KO = {
    "factual_groundedness": "사실 근거",
    "clinical_completeness": "임상 완결성",
    "hallucination_free": "환각 부재",
    "purpose_alignment": "목적 부합도",
    "actionability": "실행 가능성",
}

SYSTEM_PROMPT = """당신은 임상 브리핑 품질 평가 전문가입니다.
제공된 환자 컨텍스트 데이터와 AI가 생성한 임상 브리핑을 비교해 아래 5개 차원에서 채점하세요.

채점 기준 (각 1~5점):
1. factual_groundedness (사실 근거): 모든 수치/진단이 입력 context에서 추적 가능한가
2. clinical_completeness (임상 완결성): 주요 소견(HIGH flag, urgent 체크리스트)이 요약에 반영되었는가
3. hallucination_free (환각 부재): context에 없는 정보를 생성하지 않았는가 (5=완전 없음, 1=명백한 환각)
4. purpose_alignment (목적 부합도): rounds/preop/referral 목적에 맞는 내용 강조가 되었는가
5. actionability (실행 가능성): 권고 사항이 구체적이고 임상적으로 실행 가능한가

반드시 아래 JSON 형식으로만 응답하세요. 설명 문장 없이 JSON만 출력하세요:
{
  "factual_groundedness": <1-5>,
  "clinical_completeness": <1-5>,
  "hallucination_free": <1-5>,
  "purpose_alignment": <1-5>,
  "actionability": <1-5>,
  "rationales": {
    "factual_groundedness": "<한 줄 근거>",
    "clinical_completeness": "<한 줄 근거>",
    "hallucination_free": "<한 줄 근거>",
    "purpose_alignment": "<한 줄 근거>",
    "actionability": "<한 줄 근거>"
  }
}"""


def judge(
    case_name: str,
    context_str: str,
    agent_output: AgentOutput,
    purpose: str,
) -> dict:
    """
    GPT-4o를 이용해 agent_output 품질을 채점하고 결과 dict 반환.

    Returns:
        {
            "case_name": str,
            "factual_groundedness": float,
            ...
            "total": float,
            "rationales": {...},
        }
    """
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY가 설정되지 않았습니다.")
        return {"case_name": case_name, "error": "OPENAI_API_KEY not set"}

    client = OpenAI(api_key=OPENAI_API_KEY)

    user_message = (
        f"[목적] {purpose}\n\n"
        f"[환자 컨텍스트]\n{context_str}\n\n"
        f"[생성된 임상 브리핑]\n{agent_output.model_dump_json(indent=2)}"
    )

    raw = ""
    try:
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            response_format={"type": "json_object"},
            max_tokens=1024,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        raw = response.choices[0].message.content.strip()
        scores = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"[{case_name}] Judge 응답 JSON 파싱 실패: {e}\n응답: {raw[:200]}")
        return {"case_name": case_name, "error": f"json_parse_error: {e}"}
    except Exception as e:
        logger.warning(f"[{case_name}] Judge API 호출 실패: {e}")
        return {"case_name": case_name, "error": str(e)}

    # 점수 집계
    total = sum(
        float(scores.get(d, 0))
        for d in DIMENSIONS
    )
    result = {
        "case_name": case_name,
        **{d: scores.get(d) for d in DIMENSIONS},
        "total": round(total, 2),
        "rationales": scores.get("rationales", {}),
    }

    logger.info(
        f"[{case_name}] Judge 점수: "
        + " | ".join(f"{DIM_LABELS_KO[d]}={scores.get(d)}" for d in DIMENSIONS)
        + f" | 합계={total:.1f}"
    )
    return result
