"""Fail-closed validation of composed Drug Assistant responses."""
from __future__ import annotations

# Kept local to avoid a provider/validator import cycle.
LEGACY_PREFIXES = {
    "DRUG_GENERAL": ("general.indications", "general.clinical_pharmacology"),
    "DRUG_INDICATION": ("general.indications",), "DRUG_CLASS": ("general.clinical_pharmacology",),
    "DRUG_PREGNANCY": ("pregnancy.",), "DRUG_PREGNANCY_EXPOSURE": ("pregnancy.",),
    "DRUG_PREGNANCY_TIMING": ("pregnancy.",), "DRUG_PREGNANCY_EVIDENCE": ("pregnancy.",),
    "DRUG_PREGNANCY_REGISTRY": ("pregnancy.",), "DRUG_LACTATION": ("lactation.",),
    "DRUG_REPRODUCTIVE_POTENTIAL": ("reproductive_potential.",), "DRUG_FERTILITY": ("reproductive_potential.",),
    "DRUG_CONTRACEPTION": ("reproductive_potential.",), "DRUG_PREGNANCY_TESTING": ("reproductive_potential.",),
    "DRUG_SIDE_EFFECT": ("general.adverse_reactions",), "DRUG_SERIOUS_WARNING": ("general.warnings_and_precautions",),
    "DRUG_CONTRAINDICATION": ("general.contraindications",), "DRUG_INTERACTION": ("general.drug_interactions",),
    "DRUG_FOOD_INTERACTION": ("general.food_interactions",), "DRUG_ALCOHOL_INTERACTION": ("general.alcohol_interactions",),
    "DRUG_MISSED_DOSE_INFORMATION": ("general.missed_dose_information",), "DRUG_STORAGE": ("general.storage_and_handling",),
    "DRUG_FORMULATION": ("general.dosage_forms_and_strengths",), "DRUG_MONITORING": ("monitoring",),
    "DRUG_HEART_CONTEXT": ("condition_context.heart_disease",), "DRUG_DIABETES_CONTEXT": ("condition_context.diabetes",),
    "DRUG_PATIENT_CONTEXT": ("condition_context",), "DRUG_COMPARISON": ("general.indications", "general.warnings_and_precautions"),
    "DRUG_CLINICIAN_DISCUSSION": ("general.patient_counseling_information",),
    "DRUG_SOURCE_REQUEST": ("general.indications",), "DRUG_EVIDENCE_STRENGTH": ("general.indications",),
}

TOPICS = {
    "DRUG_GENERAL": ("general_information",), "DRUG_INDICATION": ("indications",), "DRUG_CLASS": ("class",),
    "DRUG_IDENTIFICATION": ("identity",), "DRUG_ALIAS": ("identity",), "DRUG_PREGNANCY": ("pregnancy",),
    "DRUG_PREGNANCY_EXPOSURE": ("pregnancy_exposure", "pregnancy"), "DRUG_PREGNANCY_TIMING": ("pregnancy_timing",),
    "DRUG_PREGNANCY_EVIDENCE": ("pregnancy",), "DRUG_PREGNANCY_REGISTRY": ("pregnancy_registry",),
    "DRUG_LACTATION": ("lactation",), "DRUG_REPRODUCTIVE_POTENTIAL": ("reproductive_potential",),
    "DRUG_FERTILITY": ("fertility",), "DRUG_CONTRACEPTION": ("contraception",),
    "DRUG_PREGNANCY_TESTING": ("pregnancy_testing",), "DRUG_SIDE_EFFECT": ("adverse_effects",),
    "DRUG_SERIOUS_WARNING": ("serious_adverse_effects", "warnings"), "DRUG_CONTRAINDICATION": ("contraindications",),
    "DRUG_INTERACTION": ("drug_interactions",), "DRUG_FOOD_INTERACTION": ("food_alcohol_interactions",),
    "DRUG_ALCOHOL_INTERACTION": ("food_alcohol_interactions",), "DRUG_MISSED_DOSE_INFORMATION": ("missed_dose",),
    "DRUG_STORAGE": ("storage",), "DRUG_FORMULATION": ("administration",), "DRUG_MONITORING": ("monitoring",),
    "DRUG_HEART_CONTEXT": ("drug_condition_interactions",), "DRUG_DIABETES_CONTEXT": ("drug_condition_interactions",),
    "DRUG_PATIENT_CONTEXT": ("drug_condition_interactions", "drug_interactions"),
    "DRUG_COMPARISON": ("general_information", "warnings"), "DRUG_CLINICIAN_DISCUSSION": ("clinician_discussion",),
    "DRUG_SOURCE_REQUEST": ("general_information",), "DRUG_EVIDENCE_STRENGTH": ("general_information",),
}


def validate_response(payload: dict) -> tuple[bool, str | None]:
    if payload.get("urgent"):
        return (not payload.get("claims"), None if not payload.get("claims") else "urgent response contains clinical claims")
    claims = payload.get("claims", [])
    sources = payload.get("sources", [])
    if not claims:
        return True, None
    source_urls = {item.get("url") for item in sources}
    resolved = {item.get("drug_id") for item in payload.get("drugs", [])}
    allowed_topics = set(TOPICS.get(payload.get("intent"), ()))
    if not source_urls or None in source_urls:
        return False, "claim sources missing"
    for claim in claims:
        if claim.get("drug_id") not in resolved:
            return False, "claim drug does not match resolution"
        if not set(claim.get("source_urls", ())) or not set(claim.get("source_urls", ())) <= source_urls:
            return False, "claim citation was not retrieved"
        field = claim.get("field", "")
        # Legacy reviewed-cache paths and additive-store topics are both accepted.
        if "." not in field and field not in allowed_topics:
            return False, "claim topic does not match intent"
        if "." in field and not any(field == prefix or field.startswith(prefix) for prefix in LEGACY_PREFIXES.get(payload.get("intent"), ())):
            return False, "legacy claim field does not match intent"
        if payload.get("intent") == "DRUG_LACTATION" and not (field == "lactation" or field.startswith("lactation.")):
            return False, "lactation claim uses wrong domain"
        if payload.get("intent", "").startswith("DRUG_PREGNANCY") and not (field.startswith("pregnancy") or field == "pregnancy_registry"):
            return False, "pregnancy claim uses wrong domain"
    return True, None


def safe_fallback(payload: dict) -> dict:
    names = ", ".join(item["display_name"] for item in payload.get("drugs", [])) or "this medication"
    clean = dict(payload)
    clean.update(
        summary=(f"RiskSense could not validate the available evidence for this question about {names}. "
                 "It cannot provide a drug-specific clinical conclusion. Missing evidence does not establish safety or absence of risk."),
        evidence_status="INSUFFICIENT_EVIDENCE", claims=[], sources=[], pregnancy_information=[],
        lactation_information=[], reproductive_information=[], general_information=[], warnings=[],
        interactions=[], monitoring_considerations=[], response_validation_failed=True,
    )
    return clean
