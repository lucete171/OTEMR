"""
프롬프트 + 출력 파싱 단위 테스트 (mocked OpenAI).
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from agent.prompts import build_system_prompt
from agent.output_schema import AgentOutput


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

MOCK_GPT_RESPONSE = {
    "pre_visit_context": {
        "patient_summary": "65세 남성 DM + CKD3 환자, 현재 입원 중 Creatinine 급증.",
        "active_problems": [
            "Creatinine 상승 (2.1 mg/dL, AKI 의심)",
            "Type 2 Diabetes Mellitus — 혈당 조절 불량",
            "CKD stage 3",
        ],
        "current_medications": [
            "Metformin 500 mg PO",
            "Amlodipine 5 mg PO",
            "Lisinopril 10 mg PO",
        ],
        "relevant_labs": [
            {
                "label": "Creatinine",
                "value": "2.1 mg/dL",
                "date": "2023-09-30",
                "trend": "WORSENING",
                "interpretation": "3회 입원에 걸쳐 1.2 → 2.1 mg/dL로 지속 상승, AKI 가능성"
            }
        ],
        "data_sufficiency": {
            "complete": False,
            "gaps": ["HbA1c: 최근 측정 없음 (마지막 6개월 이상 전)"]
        }
    },
    "change_flags": [
        {
            "item": "Creatinine",
            "severity": "HIGH",
            "previous": "1.6 mg/dL",
            "current": "2.1 mg/dL",
            "clinical_significance": "AKI 가능성, 신독성 약물 검토 필요"
        }
    ],
    "checklist": [
        {
            "item": "Nephrology 의뢰 고려",
            "reason": "Creatinine 3회 입원에 걸쳐 +75% 상승",
            "urgency": "URGENT"
        },
        {
            "item": "Metformin 중단 검토",
            "reason": "Cr 2.1 mg/dL — 신기능 금기 기준 초과",
            "urgency": "URGENT"
        }
    ]
}


@pytest.fixture
def mock_openai_response():
    mock = MagicMock()
    mock.choices[0].message.content = json.dumps(MOCK_GPT_RESPONSE)
    return mock


# ──────────────────────────────────────────────
# 프롬프트 구조 테스트
# ──────────────────────────────────────────────

class TestSystemPrompts:
    def test_rounds_prompt_contains_handoff(self):
        prompt = build_system_prompt("rounds")
        assert "인계용" in prompt or "Rounds" in prompt or "Handoff" in prompt

    def test_preop_prompt_contains_cardiac(self):
        prompt = build_system_prompt("preop")
        assert "Cardiac" in prompt or "cardiac" in prompt

    def test_referral_prompt_contains_specialist(self):
        prompt = build_system_prompt("referral")
        assert "specialist" in prompt.lower() or "Referral" in prompt

    def test_all_prompts_contain_json_instruction(self):
        for purpose in ("rounds", "preop", "referral"):
            prompt = build_system_prompt(purpose)
            assert "JSON" in prompt

    def test_all_prompts_contain_hallucination_guard(self):
        for purpose in ("rounds", "preop", "referral"):
            prompt = build_system_prompt(purpose)
            assert "invent" in prompt.lower() or "fabricate" in prompt.lower() or "Do NOT" in prompt


# ──────────────────────────────────────────────
# 출력 파싱 테스트
# ──────────────────────────────────────────────

class TestOutputParsing:
    def test_valid_response_parses(self):
        output = AgentOutput.model_validate(MOCK_GPT_RESPONSE)
        assert output.pre_visit_context.patient_summary
        assert len(output.pre_visit_context.active_problems) > 0

    def test_checklist_urgency_valid(self):
        output = AgentOutput.model_validate(MOCK_GPT_RESPONSE)
        valid_urgencies = {"URGENT", "ROUTINE", "OPTIONAL"}
        for item in output.checklist:
            assert item.urgency in valid_urgencies

    def test_change_flag_severity_valid(self):
        output = AgentOutput.model_validate(MOCK_GPT_RESPONSE)
        valid_severities = {"HIGH", "MEDIUM", "LOW"}
        for flag in output.change_flags:
            assert flag.severity in valid_severities

    def test_data_sufficiency_has_gaps(self):
        output = AgentOutput.model_validate(MOCK_GPT_RESPONSE)
        assert not output.pre_visit_context.data_sufficiency.complete
        assert len(output.pre_visit_context.data_sufficiency.gaps) > 0


# ──────────────────────────────────────────────
# Mocked GPT-4 호출 테스트
# ──────────────────────────────────────────────

class TestSummarizer:
    def test_generate_returns_agent_output(self, mock_openai_response):
        with patch("agent.summarizer._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_get_client.return_value = mock_client

            from agent.summarizer import generate
            output = generate(
                user_context="Test patient context",
                purpose="rounds",
            )
            assert isinstance(output, AgentOutput)
            assert output.pre_visit_context.patient_summary

    def test_generate_all_three_purposes(self, mock_openai_response):
        with patch("agent.summarizer._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_get_client.return_value = mock_client

            from agent.summarizer import generate
            for purpose in ("rounds", "preop", "referral"):
                output = generate("context", purpose)
                assert isinstance(output, AgentOutput)
