"""
Lab profiles: 목적별/진단별 lab 선택 기준, 정상 범위, 방향성 규칙.

MIMIC-IV itemid 참고: https://mimic.mit.edu/docs/iv/modules/hosp/d_labitems/
"""

# ──────────────────────────────────────────────
# 1. 기본 Lab (항상 조회)
# ──────────────────────────────────────────────
BASE_LAB_ITEM_IDS = [
    # CBC
    51222,  # Hemoglobin
    51301,  # White Blood Cells
    51265,  # Platelet Count
    53189,  # Platelet Count (duplicate itemid)

    # BMP
    50983,  # Sodium
    50971,  # Potassium
    50912,  # Creatinine
    51006,  # Urea Nitrogen (BUN)
    50931,  # Glucose

    # LFT
    50861,  # Alanine Aminotransferase (ALT)
    50878,  # Aspartate Aminotransferase (AST)
    50885,  # Bilirubin, Total

    # Coagulation
    51237,  # INR(PT)
    51274,  # PT
    51275,  # PTT
]

# ──────────────────────────────────────────────
# 2. 목적별 추가 Lab
# ──────────────────────────────────────────────
PURPOSE_LAB_ADDITIONS = {
    "rounds": [],  # 기본으로 충분
    "preop": [
        52546,  # Troponin T (high sensitivity)
        50963,  # BNP (NT-proBNP)
        51237,  # INR (이미 base에 있지만 명시)
        51274,  # PT
        51275,  # PTT
    ],
    "referral": [
        50852,  # Hemoglobin A1c
        50813,  # Lactate
        50907,  # Cholesterol, Total
        50905,  # Cholesterol, HDL
        50808,  # Calcium
        50893,  # Calcium, Ionized
        50970,  # Phosphate
        50910,  # TSH
    ],
}

# ──────────────────────────────────────────────
# 3. 진단 기반 추가 Lab (ICD prefix → item_ids)
# ──────────────────────────────────────────────
DIAGNOSIS_LAB_ADDITIONS = {
    # Diabetes Mellitus
    "E11": [50852],   # HbA1c
    "E10": [50852],   # Type 1 DM
    "E13": [50852],   # Other DM

    # CKD / Renal
    "N18": [50912, 51006, 50820, 50802],  # Cr, BUN, pH, Base Excess
    "N17": [50912, 51006],                # AKI

    # Heart Failure
    "I50": [50963, 52546],  # BNP, Troponin

    # Liver Disease
    "K74": [50861, 50878, 50885, 51248],  # ALT, AST, Bili, Albumin
    "K70": [50861, 50878, 50885],

    # Anticoagulation
    "Z79": [51237, 51274, 51275],  # INR, PT, PTT

    # Sepsis / Infection
    "A41": [50813, 51301, 50912],  # Lactate, WBC, Cr

    # COPD / Respiratory
    "J44": [50820, 50802, 50818],  # pH, Base Excess, pCO2
}

# ──────────────────────────────────────────────
# 4. Lab 메타데이터 (정상 범위, 단위, 방향성)
# ──────────────────────────────────────────────
# worsening_direction: "up" = 올라가면 나쁨, "down" = 내려가면 나쁨, "both" = 양쪽
# min_meaningful_delta: 이 이하 변화는 STABLE로 처리 (절대값)
LAB_META = {
    51222: {
        "label": "Hemoglobin",
        "unit": "g/dL",
        "ref_range": (12.0, 17.5),
        "worsening_direction": "down",
        "min_meaningful_delta": 0.5,
    },
    51301: {
        "label": "WBC",
        "unit": "K/uL",
        "ref_range": (4.0, 11.0),
        "worsening_direction": "both",
        "min_meaningful_delta": 1.0,
    },
    50802: {
        "label": "Base Excess",
        "unit": "mEq/L",
        "ref_range": (-2.0, 2.0),
        "worsening_direction": "both",
        "min_meaningful_delta": 1.0,
    },
    50820: {
        "label": "pH",
        "unit": "",
        "ref_range": (7.35, 7.45),
        "worsening_direction": "both",
        "min_meaningful_delta": 0.05,
    },
# lab_profiles.py 수정 — 51265, 53189 둘 다
    51265: {
        "label": "Platelet",
        "unit": "K/uL",
        "ref_range": (150, 450),  # 400 → 450으로 조정
        "worsening_direction": "down",
        "min_meaningful_delta": 20,
    },
    53189: {
        "label": "Platelet",
        "unit": "K/uL",
        "ref_range": (150, 450),  # 400 → 450으로 조정
        "worsening_direction": "down",
        "min_meaningful_delta": 20,
    },
    # lab_profiles.py 수정
    50983: {
        "label": "Sodium",
        "unit": "mEq/L",
        "ref_range": (134, 146),
        "worsening_direction": "both",
        "min_meaningful_delta": 3,
    },
    50971: {
        "label": "Potassium",
        "unit": "mEq/L",
        "ref_range": (3.5, 5.0),
        "worsening_direction": "both",
        "min_meaningful_delta": 0.3,
    },
    50912: {
        "label": "Creatinine",
        "unit": "mg/dL",
        "ref_range": (0.6, 1.2),
        "worsening_direction": "up",
        "min_meaningful_delta": 0.2,
    },
    51006: {
        "label": "BUN",
        "unit": "mg/dL",
        "ref_range": (7, 25),
        "worsening_direction": "up",
        "min_meaningful_delta": 5,
    },
    50931: {
        "label": "Glucose",
        "unit": "mg/dL",
        "ref_range": (70, 140),
        "worsening_direction": "both",
        "min_meaningful_delta": 20,
    },
    50861: {
        "label": "ALT",
        "unit": "IU/L",
        "ref_range": (7, 56),
        "worsening_direction": "up",
        "min_meaningful_delta": 10,
    },
    50878: {
        "label": "AST",
        "unit": "IU/L",
        "ref_range": (10, 40),
        "worsening_direction": "up",
        "min_meaningful_delta": 10,
    },
    50885: {
        "label": "Total Bilirubin",
        "unit": "mg/dL",
        "ref_range": (0.1, 1.2),
        "worsening_direction": "up",
        "min_meaningful_delta": 0.3,
    },
    51237: {
        "label": "INR",
        "unit": "",
        "ref_range": (0.8, 1.2),
        "worsening_direction": "up",
        "min_meaningful_delta": 0.2,
    },
    51274: {
        "label": "PT",
        "unit": "sec",
        "ref_range": (11, 13.5),
        "worsening_direction": "up",
        "min_meaningful_delta": 1.0,
    },
    51275: {
        "label": "PTT",
        "unit": "sec",
        "ref_range": (25, 35),
        "worsening_direction": "up",
        "min_meaningful_delta": 5,
    },
    52546: {
        "label": "Troponin T",
        "unit": "ng/mL",
        "ref_range": (0, 0.014),
        "worsening_direction": "up",
        "min_meaningful_delta": 0.01,
    },
    50963: {
        "label": "BNP",
        "unit": "pg/mL",
        "ref_range": (0, 100),
        "worsening_direction": "up",
        "min_meaningful_delta": 50,
    },
    50852: {
        "label": "HbA1c",
        "unit": "%",
        "ref_range": (4.0, 5.6),
        "worsening_direction": "up",
        "min_meaningful_delta": 0.3,
    },
    50813: {
        "label": "Lactate",
        "unit": "mmol/L",
        "ref_range": (0.5, 2.0),
        "worsening_direction": "up",
        "min_meaningful_delta": 0.5,
    },
    50910: {
        "label": "TSH",
        "unit": "mIU/L",
        "ref_range": (0.4, 4.0),
        "worsening_direction": "both",
        "min_meaningful_delta": 0.5,
    },
}


def get_item_ids_for_purpose_and_diagnoses(purpose: str, icd_prefixes: list[str]) -> list[int]:
    """목적 + 진단 기반으로 조회할 lab item_id 목록을 반환."""
    ids = set(BASE_LAB_ITEM_IDS)
    ids.update(PURPOSE_LAB_ADDITIONS.get(purpose, []))
    for prefix in icd_prefixes:
        for diag_prefix, extra_ids in DIAGNOSIS_LAB_ADDITIONS.items():
            if prefix.startswith(diag_prefix):
                ids.update(extra_ids)
    return sorted(ids)


def get_lab_meta(item_id: int) -> dict:
    """item_id에 대한 메타 정보 반환. 없으면 기본값."""
    return LAB_META.get(item_id, {
        "label": f"Lab#{item_id}",
        "unit": "",
        "ref_range": None,
        "worsening_direction": "both",
        "min_meaningful_delta": 0,
    })
