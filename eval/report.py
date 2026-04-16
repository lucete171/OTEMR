"""
평가 결과 → JSON 백업 + HTML 리포트 생성.

외부 의존성 없음 (표준 라이브러리 + f-string HTML).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.evaluators.rule_eval import RuleEvalResult

REPORTS_DIR = Path(__file__).parent / "reports"


# ──────────────────────────────────────────────
# 직렬화
# ──────────────────────────────────────────────

def build_report_data(
    rule_results: list[RuleEvalResult],
    judge_results: list[dict] | None = None,
) -> dict:
    """rule_eval + llm_judge 결과를 JSON-직렬화 가능한 dict로 변환."""
    cases = []
    for rr in rule_results:
        judge = {}
        if judge_results:
            judge = next((j for j in judge_results if j.get("case_name") == rr.case_name), {})

        cases.append({
            "name": rr.case_name,
            "rule_eval": {
                **rr.summary_by_category(),
                "pass_rate": round(rr.pass_rate, 4),
                "passed": rr.passed,
                "failed": rr.failed,
                "total": rr.total,
                "checks": [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "expected": c.expected,
                        "actual": c.actual,
                        "detail": c.detail,
                    }
                    for c in rr.all_checks
                ],
            },
            "llm_judge": judge,
        })

    total_rule_pass = sum(r.passed for r in rule_results)
    total_rule_total = sum(r.total for r in rule_results)
    judge_totals = [j.get("total", 0) for j in (judge_results or []) if j.get("total")]

    return {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "cases": cases,
        "summary": {
            "rule_eval_pass_rate": round(total_rule_pass / total_rule_total, 4) if total_rule_total else 0,
            "rule_eval_passed": total_rule_pass,
            "rule_eval_total": total_rule_total,
            "llm_judge_avg_total": round(sum(judge_totals) / len(judge_totals), 2) if judge_totals else None,
        },
    }


def save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# HTML 생성
# ──────────────────────────────────────────────

def save_html(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    html = _render_html(data)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def _render_html(data: dict) -> str:
    run_at = data["run_at"]
    summary = data["summary"]
    cases = data["cases"]

    pass_rate_pct = round(summary["rule_eval_pass_rate"] * 100, 1)
    pass_color = _traffic_light(summary["rule_eval_pass_rate"], 0.95, 0.80)
    judge_avg = summary.get("llm_judge_avg_total")
    judge_str = f"{judge_avg:.1f} / 25" if judge_avg is not None else "—"
    judge_color = _traffic_light(judge_avg / 25 if judge_avg else 0, 0.72, 0.60)

    case_sections = "\n".join(_render_case(c) for c in cases)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OTEMR Eval Report — {run_at}</title>
<style>
  :root {{
    --green: #16a34a; --yellow: #d97706; --red: #dc2626;
    --green-bg: #dcfce7; --yellow-bg: #fef3c7; --red-bg: #fee2e2;
    --gray: #6b7280; --border: #e5e7eb;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f9fafb; color: #111827; font-size: 14px; line-height: 1.5; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
  h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .meta {{ color: var(--gray); font-size: 12px; margin-bottom: 24px; }}

  /* Summary cards */
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                  gap: 12px; margin-bottom: 32px; }}
  .card {{ background: #fff; border: 1px solid var(--border); border-radius: 10px;
           padding: 16px; text-align: center; }}
  .card .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
                  color: var(--gray); margin-bottom: 6px; }}
  .card .value {{ font-size: 28px; font-weight: 700; }}
  .card .sub {{ font-size: 11px; color: var(--gray); margin-top: 2px; }}

  /* Case section */
  .case-block {{ background: #fff; border: 1px solid var(--border); border-radius: 10px;
                 margin-bottom: 20px; overflow: hidden; }}
  .case-header {{ display: flex; align-items: center; justify-content: space-between;
                  padding: 14px 18px; border-bottom: 1px solid var(--border);
                  background: #f8fafc; }}
  .case-header h2 {{ font-size: 15px; font-weight: 600; }}
  .case-body {{ padding: 18px; }}

  /* Category rows */
  .category-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                   gap: 10px; margin-bottom: 18px; }}
  .cat-item {{ background: #f9fafb; border: 1px solid var(--border); border-radius: 8px;
               padding: 10px 12px; }}
  .cat-item .cat-name {{ font-size: 11px; color: var(--gray); text-transform: uppercase;
                         letter-spacing: .04em; margin-bottom: 4px; }}
  .cat-item .cat-score {{ font-size: 18px; font-weight: 700; }}

  /* Progress bar */
  .progress-wrap {{ background: #e5e7eb; border-radius: 4px; height: 6px;
                   overflow: hidden; margin-top: 6px; }}
  .progress-bar {{ height: 100%; border-radius: 4px; transition: width .3s; }}

  /* LLM Judge scores */
  .judge-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;
                margin-bottom: 18px; }}
  .judge-dim {{ text-align: center; }}
  .judge-dim .dim-name {{ font-size: 10px; color: var(--gray); margin-bottom: 4px; }}
  .judge-dim .dim-score {{ font-size: 20px; font-weight: 700; }}
  .judge-rationale {{ background: #f9fafb; border-left: 3px solid var(--border);
                      padding: 8px 12px; font-size: 12px; color: var(--gray);
                      border-radius: 0 6px 6px 0; margin-bottom: 18px; }}

  /* Check table */
  details {{ margin-top: 4px; }}
  summary {{ cursor: pointer; font-size: 12px; color: var(--gray);
             user-select: none; padding: 4px 0; }}
  summary:hover {{ color: #374151; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 12px; }}
  th {{ text-align: left; padding: 6px 10px; background: #f3f4f6;
        border-bottom: 1px solid var(--border); font-weight: 600; color: var(--gray); }}
  td {{ padding: 5px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}

  /* Badges */
  .badge {{ display: inline-block; border-radius: 4px; padding: 1px 7px;
            font-size: 11px; font-weight: 600; }}
  .badge-pass {{ background: var(--green-bg); color: var(--green); }}
  .badge-fail {{ background: var(--red-bg); color: var(--red); }}
  .badge-high {{ background: var(--red-bg); color: var(--red); }}
  .badge-med {{ background: var(--yellow-bg); color: var(--yellow); }}
  .badge-low {{ background: #eff6ff; color: #2563eb; }}

  .no-judge {{ color: var(--gray); font-style: italic; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <h1>OTEMR 평가 리포트</h1>
  <p class="meta">실행 시각: {run_at} &nbsp;|&nbsp; 케이스 수: {len(cases)}</p>

  <div class="summary-grid">
    <div class="card">
      <div class="label">Rule Eval Pass Rate</div>
      <div class="value" style="color: var(--{pass_color})">{pass_rate_pct}%</div>
      <div class="sub">{summary['rule_eval_passed']} / {summary['rule_eval_total']} checks</div>
    </div>
    <div class="card">
      <div class="label">LLM Judge 평균</div>
      <div class="value" style="color: var(--{judge_color})">{judge_str}</div>
      <div class="sub">5개 차원 × 5점</div>
    </div>
    <div class="card">
      <div class="label">케이스 수</div>
      <div class="value">{len(cases)}</div>
      <div class="sub">평가된 환자 케이스</div>
    </div>
  </div>

  {case_sections}
</div>
</body>
</html>"""


def _render_case(case: dict) -> str:
    name = case["name"]
    re_data = case["rule_eval"]
    judge_data = case.get("llm_judge", {})

    pass_rate_pct = round(re_data["pass_rate"] * 100, 1)
    color = _traffic_light(re_data["pass_rate"], 0.95, 0.80)
    badge_cls = "badge-pass" if re_data["pass_rate"] >= 0.95 else "badge-fail"

    # category bars
    cat_names = {
        "trend_accuracy": "Trend 방향",
        "flag_detection": "Flag 감지",
        "absent_flags": "Absent Flags",
        "checklist_keywords": "Checklist",
        "schema_validation": "스키마",
    }
    cat_html = ""
    for key, label in cat_names.items():
        cat = re_data.get(key, {})
        p, f = cat.get("passed", 0), cat.get("failed", 0)
        total = p + f
        pct = round(p / total * 100) if total else 0
        bar_color = _traffic_light(p / total if total else 1, 0.95, 0.80)
        cat_html += f"""
        <div class="cat-item">
          <div class="cat-name">{label}</div>
          <div class="cat-score" style="color: var(--{bar_color})">{p}/{total}</div>
          <div class="progress-wrap">
            <div class="progress-bar" style="width:{pct}%; background: var(--{bar_color})"></div>
          </div>
        </div>"""

    # check table rows
    rows = ""
    for c in re_data.get("checks", []):
        badge = "badge-pass" if c["passed"] else "badge-fail"
        label_text = "PASS" if c["passed"] else "FAIL"
        detail = c.get("detail", "")
        rows += f"""
        <tr>
          <td>{c['name']}</td>
          <td><span class="badge {badge}">{label_text}</span></td>
          <td>{c['expected']}</td>
          <td>{c['actual']}</td>
          <td style="color: var(--gray)">{detail}</td>
        </tr>"""

    checks_table = f"""
    <details>
      <summary>전체 체크 항목 보기 ({re_data['passed']}/{re_data['total']})</summary>
      <table>
        <thead><tr><th>Check</th><th>결과</th><th>기대</th><th>실제</th><th>비고</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </details>"""

    # LLM judge section
    dims = ["factual_groundedness", "clinical_completeness", "hallucination_free",
            "purpose_alignment", "actionability"]
    dim_labels = {
        "factual_groundedness": "사실 근거",
        "clinical_completeness": "임상 완결",
        "hallucination_free": "환각 없음",
        "purpose_alignment": "목적 부합",
        "actionability": "실행 가능",
    }
    if judge_data and any(d in judge_data for d in dims):
        judge_total = judge_data.get("total", 0)
        judge_color = _traffic_light(judge_total / 25 if judge_total else 0, 0.72, 0.60)
        dim_cells = ""
        for d in dims:
            score = judge_data.get(d, "—")
            score_val = float(score) if isinstance(score, (int, float)) else 0
            d_color = _traffic_light(score_val / 5, 0.72, 0.60)
            dim_cells += f"""
            <div class="judge-dim">
              <div class="dim-name">{dim_labels[d]}</div>
              <div class="dim-score" style="color: var(--{d_color})">{score}</div>
            </div>"""

        rationales = judge_data.get("rationales", {})
        rat_lines = "".join(
            f"<div><strong>{dim_labels.get(k, k)}:</strong> {v}</div>"
            for k, v in rationales.items()
        )
        rat_block = f'<div class="judge-rationale">{rat_lines}</div>' if rat_lines else ""

        judge_section = f"""
        <div style="margin-bottom:4px; font-size:12px; font-weight:600; color:var(--gray)">
          LLM Judge 총점:
          <span style="font-size:16px; color: var(--{judge_color})">{judge_total} / 25</span>
        </div>
        <div class="judge-grid">{dim_cells}</div>
        {rat_block}"""
    else:
        judge_section = '<p class="no-judge">LLM Judge 결과 없음 (--skip-llm-judge)</p>'

    return f"""
<div class="case-block">
  <div class="case-header">
    <h2>{name}</h2>
    <span class="badge {badge_cls}">{pass_rate_pct}% ({re_data['passed']}/{re_data['total']})</span>
  </div>
  <div class="case-body">
    <div style="margin-bottom:14px">
      <div style="font-size:12px; font-weight:600; color:var(--gray); margin-bottom:8px">RULE EVAL</div>
      <div class="category-grid">{cat_html}</div>
      {checks_table}
    </div>
    <div style="margin-top:18px; padding-top:16px; border-top: 1px solid var(--border)">
      <div style="font-size:12px; font-weight:600; color:var(--gray); margin-bottom:10px">LLM JUDGE</div>
      {judge_section}
    </div>
  </div>
</div>"""


def _traffic_light(ratio: float, green_thresh: float, yellow_thresh: float) -> str:
    if ratio >= green_thresh:
        return "green"
    if ratio >= yellow_thresh:
        return "yellow"
    return "red"


# ──────────────────────────────────────────────
# 편의 함수
# ──────────────────────────────────────────────

def write_report(
    rule_results: list[RuleEvalResult],
    judge_results: list[dict] | None = None,
    timestamp: str | None = None,
) -> tuple[Path, Path]:
    """JSON + HTML 리포트를 eval/reports/ 에 저장하고 경로 튜플 반환."""
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    data = build_report_data(rule_results, judge_results)

    json_path = REPORTS_DIR / f"eval_{ts}.json"
    html_path = REPORTS_DIR / f"eval_{ts}.html"
    latest_path = REPORTS_DIR / "eval_latest.html"

    save_json(data, json_path)
    save_html(data, html_path)

    # eval_latest.html 갱신
    import shutil
    shutil.copy2(html_path, latest_path)

    return json_path, html_path
