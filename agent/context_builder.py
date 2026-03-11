"""
PatientRecord + 분석 결과 → 프롬프트 user message 조립.

구조:
  PATIENT DEMOGRAPHICS
  DIAGNOSES (ICD)
  CLINICAL CONTEXT TAGS
  ACTIVE MEDICATIONS
  LAB TRENDS
  CHANGE FLAGS (rule-based)
  MUST-CHECK ITEMS (rule-based, LLM이 reason 보강 예정)
"""
from __future__ import annotations

from analysis.checklist import ChecklistItem
from analysis.diagnosis_context import extract_tags, format_tags_for_prompt
from analysis.flags import ChangeFlag
from analysis.trend import TrendResult
from config.settings import MAX_MEDICATIONS
from data.loader import PatientRecord


def build_user_context(
    record: PatientRecord,
    trends: dict[int, TrendResult],
    flags: list[ChangeFlag],
    checklist: list[ChecklistItem],
) -> str:
    """프롬프트에 삽입할 구조화된 환자 컨텍스트 문자열 생성."""
    sections = [
        _demographics_section(record),
        _diagnoses_section(record),
        _tags_section(record),
        _medications_section(record),
        _labs_section(trends),
        _flags_section(flags),
        _checklist_section(checklist),
        _notes_section(record),
    ]
    return "\n\n".join(s for s in sections if s)


# ──────────────────────────────────────────────
# 섹션별 빌더
# ──────────────────────────────────────────────

def _demographics_section(record: PatientRecord) -> str:
    admissions = record.admissions
    current_adm = admissions[0] if admissions else None
    n_admissions = len(admissions)

    lines = [
        "=== PATIENT DEMOGRAPHICS ===",
        f"Subject ID: {record.subject_id}",
        f"Gender: {record.gender}",
        f"Age group: {record.anchor_year_group} (anchor age ~{record.anchor_age})",
        f"Total admissions in record: {n_admissions}",
    ]
    if current_adm:
        lines.append(f"Current admission: {current_adm.admittime.strftime('%Y-%m-%d')} | Type: {current_adm.admission_type}")
        if current_adm.dischtime:
            lines.append(f"Discharged: {current_adm.dischtime.strftime('%Y-%m-%d')}")
        else:
            lines.append("Status: Currently admitted")
        if current_adm.diagnosis:
            lines.append(f"Admission diagnosis: {current_adm.diagnosis}")

    return "\n".join(lines)


def _diagnoses_section(record: PatientRecord) -> str:
    if not record.diagnoses:
        return "=== DIAGNOSES ===\nNo diagnoses recorded for current admission."

    lines = ["=== DIAGNOSES (current admission, ICD) ==="]
    for d in record.diagnoses[:15]:  # 상위 15개
        lines.append(f"  {d.seq_num}. [{d.icd_code}] {d.description}")
    if len(record.diagnoses) > 15:
        lines.append(f"  ... and {len(record.diagnoses) - 15} more")
    return "\n".join(lines)


def _tags_section(record: PatientRecord) -> str:
    tags = extract_tags(record.diagnoses)
    tag_str = format_tags_for_prompt(tags)
    return f"=== CLINICAL CONTEXT TAGS ===\n{tag_str}"


def _medications_section(record: PatientRecord) -> str:
    active = record.active_prescriptions[:MAX_MEDICATIONS]
    if not active:
        return "=== ACTIVE MEDICATIONS ===\nNo active prescriptions recorded."

    lines = ["=== ACTIVE MEDICATIONS ==="]
    for p in active:
        dose_str = f"{p.dose_val_rx} {p.dose_unit_rx}".strip() if p.dose_val_rx else ""
        route_str = f"({p.route})" if p.route else ""
        started = p.starttime.strftime("%Y-%m-%d") if p.starttime else "unknown"
        lines.append(f"  - {p.drug} {dose_str} {route_str} — started {started}")

    total = len(record.active_prescriptions)
    if total > MAX_MEDICATIONS:
        lines.append(f"  ... and {total - MAX_MEDICATIONS} more active medications")
    return "\n".join(lines)


def _labs_section(trends: dict[int, TrendResult]) -> str:
    if not trends:
        return "=== LAB TRENDS ===\nNo lab data available."

    lines = ["=== LAB TRENDS (180-day history) ==="]

    # 데이터 있는 것 먼저
    has_data = {iid: t for iid, t in trends.items() if t.has_recent_data}
    no_data = {iid: t for iid, t in trends.items() if not t.has_recent_data}

    for iid, trend in has_data.items():
        lines.append(f"  {trend.summary_str}")
        if trend.sparkline and len(trend.sparkline) >= 2:
            # 최근 3개 포인트만 표시 (너무 길면 토큰 낭비)
            recent_pts = trend.sparkline[-3:]
            pts_str = " → ".join(
                f"{v:.2f}({d.strftime('%m/%d')})" for d, v in recent_pts
            )
            lines.append(f"    Trend: {pts_str}")

    if no_data:
        lines.append("")
        lines.append("  [DATA GAPS — no recent values:]")
        for iid, trend in no_data.items():
            lines.append(f"  - {trend.label}: 데이터 없음")

    return "\n".join(lines)


def _flags_section(flags: list[ChangeFlag]) -> str:
    if not flags:
        return ""

    lines = ["=== CHANGE FLAGS (rule-detected) ==="]
    for f in flags:
        lines.append(f"  [{f.severity}] {f.message}")
    return "\n".join(lines)


def _checklist_section(checklist: list[ChecklistItem]) -> str:
    if not checklist:
        return ""

    lines = ["=== MUST-CHECK ITEMS (rule-based) ==="]
    for item in checklist:
        lines.append(f"  [{item.urgency}] {item.item}")
        lines.append(f"    WHY: {item.reason}")
    return "\n".join(lines)


def _notes_section(record: PatientRecord) -> str:
    if not record.discharge_notes:
        return ""

    lines = ["=== RECENT DISCHARGE NOTES (excerpts) ==="]
    for note in record.discharge_notes:
        date_str = note.charttime.strftime("%Y-%m-%d") if note.charttime else "unknown"
        lines.append(f"--- Note ({date_str}) ---")
        lines.append(note.text_excerpt[:1000])  # 최대 1000자
        lines.append("")
    return "\n".join(lines)
