"""
ICD 코드 → 임상 컨텍스트 태그 변환.

tags는 context_builder에서 프롬프트 지시어로 활용되고,
lab_profiles에서 추가 lab 선택 기준으로도 사용.
"""
from __future__ import annotations

from data.loader import Diagnosis


# ICD prefix → 태그 + 임상 의미
DIAGNOSIS_TAG_MAP: dict[str, dict] = {
    # Diabetes
    "E11": {"tag": "DM_type2",        "label": "Type 2 Diabetes Mellitus"},
    "E10": {"tag": "DM_type1",        "label": "Type 1 Diabetes Mellitus"},
    "E13": {"tag": "DM_other",        "label": "Other Diabetes"},

    # CKD / Renal
    "N18": {"tag": "CKD",             "label": "Chronic Kidney Disease"},
    "N17": {"tag": "AKI",             "label": "Acute Kidney Injury"},

    # Heart
    "I50": {"tag": "HF",              "label": "Heart Failure"},
    "I25": {"tag": "CAD",             "label": "Coronary Artery Disease"},
    "I48": {"tag": "AFib",            "label": "Atrial Fibrillation"},
    "I10": {"tag": "HTN",             "label": "Hypertension"},
    "I21": {"tag": "MI",              "label": "Myocardial Infarction"},

    # Pulmonary
    "J44": {"tag": "COPD",            "label": "COPD"},
    "J18": {"tag": "Pneumonia",       "label": "Pneumonia"},

    # Liver
    "K74": {"tag": "Cirrhosis",       "label": "Liver Cirrhosis"},
    "K70": {"tag": "ALD",             "label": "Alcoholic Liver Disease"},
    "K72": {"tag": "Liver_failure",   "label": "Hepatic Failure"},

    # Sepsis / Infection
    "A41": {"tag": "Sepsis",          "label": "Sepsis"},
    "A40": {"tag": "Sepsis",          "label": "Streptococcal Sepsis"},

    # Coagulation
    "Z79": {"tag": "Anticoagulation", "label": "Long-term Anticoagulant Use"},
    "D68": {"tag": "Coagulopathy",    "label": "Coagulation Defect"},

    # Malignancy
    "C":   {"tag": "Malignancy",      "label": "Malignant Neoplasm"},

    # Neurological
    "I63": {"tag": "Stroke",          "label": "Ischemic Stroke"},
    "G35": {"tag": "MS",              "label": "Multiple Sclerosis"},
}

# 목적별 강조 태그 (프롬프트에서 포커스 지시에 사용)
PURPOSE_CRITICAL_TAGS: dict[str, list[str]] = {
    "preop": ["CAD", "HF", "CKD", "AKI", "Anticoagulation", "Coagulopathy", "COPD", "DM_type2", "DM_type1"],
    "rounds": ["AKI", "Sepsis", "HF", "AFib", "Pneumonia"],
    "referral": ["Cirrhosis", "Malignancy", "CKD", "DM_type2", "DM_type1", "Stroke"],
}


def extract_tags(diagnoses: list[Diagnosis]) -> list[dict]:
    """
    진단 목록에서 임상 태그 추출.

    Returns:
        [{"tag": "DM_type2", "label": "Type 2 Diabetes Mellitus", "icd_code": "E11.9"}, ...]
    """
    seen_tags = set()
    result = []

    for diag in diagnoses:
        icd = diag.icd_code
        matched = None

        # 4자리 → 3자리 → 1자리 순으로 매칭
        for prefix_len in (4, 3, 1):
            prefix = icd[:prefix_len]
            if prefix in DIAGNOSIS_TAG_MAP:
                matched = DIAGNOSIS_TAG_MAP[prefix]
                break

        if matched and matched["tag"] not in seen_tags:
            seen_tags.add(matched["tag"])
            result.append({
                "tag": matched["tag"],
                "label": matched["label"],
                "icd_code": icd,
                "icd_description": diag.description,
            })

    return result


def get_critical_tags_for_purpose(tags: list[dict], purpose: str) -> list[dict]:
    """목적에 따라 중요도가 높은 태그를 앞으로 정렬."""
    critical = PURPOSE_CRITICAL_TAGS.get(purpose, [])
    critical_set = set(critical)

    high = [t for t in tags if t["tag"] in critical_set]
    low = [t for t in tags if t["tag"] not in critical_set]
    return high + low


def format_tags_for_prompt(tags: list[dict]) -> str:
    """프롬프트 삽입용 태그 문자열."""
    if not tags:
        return "No specific clinical context tags identified."
    return ", ".join(t["tag"] for t in tags)
