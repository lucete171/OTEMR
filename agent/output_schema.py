"""
GPT-4 출력 Pydantic 스키마.
json_object 모드 응답을 파싱하고 검증.
"""
from typing import Optional
from pydantic import BaseModel, Field


class LabSummary(BaseModel):
    label: str
    value: str
    date: str
    trend: str       # "IMPROVING" | "WORSENING" | "STABLE" | "UNKNOWN"
    interpretation: str


class DataSufficiency(BaseModel):
    complete: bool
    gaps: list[str] = Field(default_factory=list)


class PreVisitContext(BaseModel):
    patient_summary: str
    active_problems: list[str]
    current_medications: list[str]
    relevant_labs: list[LabSummary]
    data_sufficiency: DataSufficiency


class ChangeFlagOutput(BaseModel):
    item: str
    severity: str    # "HIGH" | "MEDIUM" | "LOW"
    previous: Optional[str] = None
    current: str
    clinical_significance: str


class ChecklistItemOutput(BaseModel):
    item: str
    reason: str
    urgency: str     # "URGENT" | "ROUTINE" | "OPTIONAL"


class AgentOutput(BaseModel):
    pre_visit_context: PreVisitContext
    change_flags: list[ChangeFlagOutput] = Field(default_factory=list)
    checklist: list[ChecklistItemOutput] = Field(default_factory=list)
