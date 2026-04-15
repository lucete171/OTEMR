"""
평가 파이프라인 CLI 진입점.

사용:
    python -m eval.runner                         # 전체 실행
    python -m eval.runner --skip-llm-judge        # rule-based만
    python -m eval.runner --cases dm_ckd          # 특정 케이스만
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Windows 터미널 UTF-8 출력
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 프로젝트 루트를 sys.path에 추가 (모듈 import 보장)
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from agent.context_builder import build_user_context
from agent.summarizer import generate
from analysis.advanced import run_advanced_analysis
from analysis.checklist import generate_checklist
from analysis.flags import detect_flags
from analysis.trend import compute_trends
from config.lab_profiles import get_item_ids_for_purpose_and_diagnoses
from eval import report as report_module
from eval.cases.base import EvalCase
from eval.evaluators import rule_eval
from eval.evaluators.advanced_eval import (
    detect_missed_critical_cases,
    evaluate_advanced,
    generate_debug_trace,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("eval.runner")


# ──────────────────────────────────────────────
# 케이스 레지스트리
# ──────────────────────────────────────────────

def _load_all_cases() -> dict[str, EvalCase]:
    from eval.cases.case_dm_ckd import build as build_dm_ckd

    cases: dict[str, EvalCase] = {"dm_ckd": build_dm_ckd()}

    # demo parquet 기반 케이스 — 데이터 없으면 경고 후 스킵
    _optional_cases = [
        ("cad_preop", "eval.cases.case_cad_preop"),
        ("referral",  "eval.cases.case_referral"),
    ]
    for key, module_path in _optional_cases:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cases[key] = mod.build()
        except RuntimeError as e:
            logger.warning(f"케이스 '{key}' 스킵: {e}")
        except Exception as e:
            logger.warning(f"케이스 '{key}' 로드 오류: {e}")

    return cases


# ──────────────────────────────────────────────
# 단일 케이스 실행
# ──────────────────────────────────────────────

def run_case(
    case: EvalCase,
    skip_llm_judge: bool = False,
) -> tuple[rule_eval.RuleEvalResult, dict, dict]:
    """한 케이스에 대해 전체 파이프라인 실행 + 평가."""
    logger.info(f"[{case.name}] 파이프라인 실행 중...")
    t0 = time.time()

    record = case.patient_record
    purpose = case.purpose

    # --- 분석 ---
    item_ids = get_item_ids_for_purpose_and_diagnoses(purpose, record.icd_prefixes)
    trends = compute_trends(record.labs, item_ids)
    flags = detect_flags(trends)
    checklist = generate_checklist(record, trends, flags)

    # --- 고급 분석 ---
    advanced = run_advanced_analysis(
        subject_id=record.subject_id,
        trends=trends,
        flags=flags,
    )
    logger.info(
        f"[{case.name}] 고급 분석 완료 — "
        f"patient_state={advanced.patient_state}, score={advanced.deterioration_score}"
    )

    # --- LLM 요약 ---
    user_context = build_user_context(record, trends, flags, checklist, advanced=advanced)
    try:
        agent_output = generate(user_context=user_context, purpose=purpose)
    except Exception as e:
        logger.warning(f"[{case.name}] LLM 호출 실패: {e}")
        agent_output = None

    elapsed = round(time.time() - t0, 1)
    logger.info(f"[{case.name}] 파이프라인 완료 ({elapsed}s)")

    # --- 1차 평가 ---
    re_result = rule_eval.evaluate(
        case=case,
        trends=trends,
        flags=flags,
        checklist=checklist,
        agent_output=agent_output,
    )

    # --- 고급 분석 평가 ---
    adv_result = evaluate_advanced(case=case, advanced=advanced)
    missed = detect_missed_critical_cases(flags=flags, advanced=advanced)
    if missed:
        for m in missed:
            logger.warning(f"[{case.name}] {m}")
    if adv_result.total > 0:
        logger.info(
            f"[{case.name}] 고급 평가: {adv_result.passed}/{adv_result.total} 통과"
        )

    # --- 2차 평가 ---
    judge_result: dict = {"case_name": case.name}
    if not skip_llm_judge and agent_output is not None:
        logger.info(f"[{case.name}] LLM Judge 실행 중...")
        try:
            from eval.evaluators.llm_judge import judge
            judge_result = judge(
                case_name=case.name,
                context_str=user_context,
                agent_output=agent_output,
                purpose=purpose,
            )
        except Exception as e:
            logger.warning(f"[{case.name}] LLM Judge 실패: {e}")

    _print_case_summary(case.name, re_result, judge_result, adv_result)
    return re_result, judge_result, generate_debug_trace(advanced)


# ──────────────────────────────────────────────
# 출력
# ──────────────────────────────────────────────

def _print_case_summary(
    name: str,
    re_result: rule_eval.RuleEvalResult,
    judge_result: dict,
    adv_result=None,
) -> None:
    from eval.evaluators.advanced_eval import AdvancedEvalResult
    ok = "PASS" if re_result.pass_rate >= 0.95 else "FAIL"
    print(f"\n{'='*60}")
    print(f"  Case: {name}")
    print(f"  Rule Eval [{ok}] {re_result.passed}/{re_result.total} ({re_result.pass_rate*100:.1f}%)")

    # 실패 항목 표시
    failed = [c for c in re_result.all_checks if not c.passed]
    if failed:
        for c in failed:
            print(f"    [FAIL] {c.name}: expected={c.expected!r} actual={c.actual!r}")

    # 고급 분석 평가
    if isinstance(adv_result, AdvancedEvalResult) and adv_result.total > 0:
        adv_ok = "PASS" if adv_result.pass_rate >= 1.0 else "FAIL"
        print(f"  Adv Eval  [{adv_ok}] {adv_result.passed}/{adv_result.total}")
        for c in adv_result.all_checks:
            if not c.passed:
                print(f"    [FAIL] {c.name}: expected={c.expected!r} actual={c.actual!r}")

    # Judge 점수
    total = judge_result.get("total")
    if total is not None:
        print(f"  LLM Judge  {total:.1f}/25")
    print(f"{'='*60}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="OTEMR 평가 파이프라인")
    parser.add_argument(
        "--cases",
        default="all",
        help="실행할 케이스 (all | dm_ckd | cad_preop | referral, 콤마 구분)",
    )
    parser.add_argument(
        "--skip-llm-judge",
        action="store_true",
        help="LLM Judge 단계를 건너뜀 (빠른 rule-based만 실행)",
    )
    args = parser.parse_args()

    all_cases = _load_all_cases()

    if args.cases == "all":
        selected = list(all_cases.values())
    else:
        keys = [k.strip() for k in args.cases.split(",")]
        selected = []
        for k in keys:
            if k not in all_cases:
                logger.error(f"알 수 없는 케이스: {k}. 선택 가능: {list(all_cases.keys())}")
                sys.exit(1)
            selected.append(all_cases[k])

    print(f"\nOTEMR 평가 파이프라인 - {len(selected)}개 케이스")
    print(f"LLM Judge: {'건너뜀' if args.skip_llm_judge else '실행'}\n")

    rule_results = []
    judge_results = []

    for case in selected:
        rr, jr, _ = run_case(case, skip_llm_judge=args.skip_llm_judge)
        rule_results.append(rr)
        if jr:
            judge_results.append(jr)

    # 리포트 저장
    json_path, html_path = report_module.write_report(rule_results, judge_results or None)

    # 최종 요약
    total_pass = sum(r.passed for r in rule_results)
    total_checks = sum(r.total for r in rule_results)
    overall_rate = total_pass / total_checks if total_checks else 0
    judge_totals = [j.get("total") for j in judge_results if j.get("total") is not None]
    judge_avg = sum(judge_totals) / len(judge_totals) if judge_totals else None

    print(f"\n{'='*60}")
    print(f"  최종 결과")
    print(f"  Rule Eval:  {total_pass}/{total_checks} ({overall_rate*100:.1f}%)")
    if judge_avg is not None:
        print(f"  LLM Judge:  {judge_avg:.1f}/25 평균")
    print(f"\n  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    print(f"{'='*60}\n")

    # 성공 기준 미달 시 exit code 1
    if overall_rate < 0.95:
        sys.exit(1)


if __name__ == "__main__":
    main()
