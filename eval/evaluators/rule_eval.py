"""
1차 평가: Rule-based 자동 검증.

EvalCase의 기대값(expected_*)과 파이프라인 실제 출력을 비교해
pass/fail 결과를 반환한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.output_schema import AgentOutput
from analysis.checklist import ChecklistItem
from analysis.flags import ChangeFlag
from analysis.trend import TrendResult
from eval.cases.base import EvalCase


# ──────────────────────────────────────────────
# 결과 데이터 구조
# ──────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    expected: str
    actual: str
    detail: str = ""


@dataclass
class RuleEvalResult:
    case_name: str
    trend_checks: list[CheckResult] = field(default_factory=list)
    flag_checks: list[CheckResult] = field(default_factory=list)
    absent_flag_checks: list[CheckResult] = field(default_factory=list)
    checklist_checks: list[CheckResult] = field(default_factory=list)
    schema_checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_checks(self) -> list[CheckResult]:
        return (
            self.trend_checks
            + self.flag_checks
            + self.absent_flag_checks
            + self.checklist_checks
            + self.schema_checks
        )

    @property
    def passed(self) -> int:
        return sum(1 for c in self.all_checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.all_checks if not c.passed)

    @property
    def total(self) -> int:
        return len(self.all_checks)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    def summary_by_category(self) -> dict[str, dict]:
        categories = {
            "trend_accuracy": self.trend_checks,
            "flag_detection": self.flag_checks,
            "absent_flags": self.absent_flag_checks,
            "checklist_keywords": self.checklist_checks,
            "schema_validation": self.schema_checks,
        }
        return {
            cat: {"passed": sum(1 for c in checks if c.passed), "failed": sum(1 for c in checks if not c.passed)}
            for cat, checks in categories.items()
        }


# ──────────────────────────────────────────────
# 메인 평가 함수
# ──────────────────────────────────────────────

def evaluate(
    case: EvalCase,
    trends: dict[int, TrendResult],
    flags: list[ChangeFlag],
    checklist: list[ChecklistItem],
    agent_output: AgentOutput | None,
) -> RuleEvalResult:
    """케이스 기대값과 실제 파이프라인 출력을 비교해 RuleEvalResult 반환."""
    result = RuleEvalResult(case_name=case.name)

    # 1. Trend 방향 검증
    label_to_trend = {t.label: t for t in trends.values()}
    for label, expected_dir in case.expected_trend_directions.items():
        trend = label_to_trend.get(label)
        actual_dir = trend.direction if trend else "NOT_FOUND"
        passed = actual_dir == expected_dir
        result.trend_checks.append(CheckResult(
            name=f"trend_direction:{label}",
            passed=passed,
            expected=expected_dir,
            actual=actual_dir,
            detail=f"last_value={trend.last_value:.2f}" if trend and trend.last_value else "",
        ))

    # 2. Flag 감지 검증
    flag_by_label: dict[str, ChangeFlag] = {f.label: f for f in flags}
    for expected in case.expected_flags:
        actual_flag = flag_by_label.get(expected.lab_label)
        if actual_flag is None:
            result.flag_checks.append(CheckResult(
                name=f"flag_detected:{expected.lab_label}",
                passed=False,
                expected=f"{expected.lab_label} severity={expected.severity}",
                actual="NOT_FOUND",
            ))
        else:
            sev_match = actual_flag.severity == expected.severity
            result.flag_checks.append(CheckResult(
                name=f"flag_severity:{expected.lab_label}",
                passed=sev_match,
                expected=expected.severity,
                actual=actual_flag.severity,
                detail=actual_flag.message,
            ))

    # 3. Absent flag 검증 (없어야 할 flag)
    for label in case.expected_absent_flag_labels:
        present = label in flag_by_label
        result.absent_flag_checks.append(CheckResult(
            name=f"absent_flag:{label}",
            passed=not present,
            expected="NOT_FLAGGED",
            actual="FLAGGED" if present else "NOT_FLAGGED",
            detail=flag_by_label[label].message if present else "",
        ))

    # 4. Checklist 키워드 검증
    checklist_text = " ".join(
        (item.item + " " + item.reason).lower()
        for item in checklist
    )
    for keyword in case.expected_checklist_keywords:
        found = re.search(re.escape(keyword.lower()), checklist_text) is not None
        result.checklist_checks.append(CheckResult(
            name=f"checklist_keyword:{keyword}",
            passed=found,
            expected=f"contains '{keyword}'",
            actual="found" if found else "not found",
        ))

    # 5. LLM 출력 스키마 검증
    if agent_output is not None:
        result.schema_checks.extend(_validate_schema(agent_output))

    return result


# ──────────────────────────────────────────────
# 스키마 검증
# ──────────────────────────────────────────────

FORBIDDEN_PHRASES = [
    "i don't know",
    "i do not know",
    "hallucinate",
    "as an ai",
    "i cannot",
    "n/a",
]


def _validate_schema(output: AgentOutput) -> list[CheckResult]:
    checks: list[CheckResult] = []

    # one_liner 비어있지 않음
    one_liner = output.pre_visit_context.patient_summary
    checks.append(CheckResult(
        name="schema:patient_summary_nonempty",
        passed=bool(one_liner and one_liner.strip()),
        expected="non-empty string",
        actual=repr(one_liner[:60]) if one_liner else "empty",
    ))

    # change_flags 각 항목 severity 필드
    for i, flag in enumerate(output.change_flags):
        valid_sev = flag.severity in ("HIGH", "MEDIUM", "LOW")
        checks.append(CheckResult(
            name=f"schema:flag[{i}].severity",
            passed=valid_sev,
            expected="HIGH|MEDIUM|LOW",
            actual=flag.severity,
        ))

    # checklist 각 항목 urgency 필드
    for i, item in enumerate(output.checklist):
        valid_urg = item.urgency in ("URGENT", "ROUTINE", "OPTIONAL")
        checks.append(CheckResult(
            name=f"schema:checklist[{i}].urgency",
            passed=valid_urg,
            expected="URGENT|ROUTINE|OPTIONAL",
            actual=item.urgency,
        ))

    # 금지 표현 미포함
    full_text = output.model_dump_json().lower()
    for phrase in FORBIDDEN_PHRASES:
        found = phrase in full_text
        checks.append(CheckResult(
            name=f"schema:no_forbidden:'{phrase}'",
            passed=not found,
            expected="absent",
            actual="found" if found else "absent",
        ))

    return checks
