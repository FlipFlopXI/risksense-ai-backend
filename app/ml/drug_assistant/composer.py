"""Deterministic, source-first response composition; never fills clinical placeholders."""
from datetime import datetime, timezone
import re
from app.ml.drug_assistant.intent import classify
from app.ml.drug_assistant.provider import CompositeProvider, DrugKnowledgeProvider, PublishedEvidenceProvider, ReviewedLocalProvider
from app.ml.drug_assistant.resolver import resolve
from app.ml.drug_assistant.response_validator import safe_fallback, validate_response
from app.ml.drug_assistant.runtime import DrugRuntime, normalize

SAFETY = "RiskSense provides educational, source-grounded medication information. It is not a diagnosis, prescription, or replacement for a clinician or pharmacist. Medication decisions require your prescriber or pharmacist."
URGENT_SOURCE = {"url": "https://www.nhs.uk/conditions/poisoning/", "purpose": "general urgent-help routing", "reviewed_on": "2026-09-17"}


def public_drug(runtime: DrugRuntime, drug_id: str) -> dict:
    record = runtime.drugs[drug_id]
    return {"drug_id": drug_id, "generic_name": record["generic_name"], "display_name": record["generic_name"]}


def compose(message: str, runtime: DrugRuntime, previous: tuple[str, ...] = (),
            context: dict | None = None, provider: DrugKnowledgeProvider | None = None,
            pending_urgent: str | None = None) -> dict:
    intent = classify(message)
    if pending_urgent and not intent.urgent_category:
        from app.ml.drug_assistant.intent import Intent
        intent = Intent("EMERGENCY_OR_URGENT", pending_urgent)
    result = {
        "intent": intent.name, "drug": None, "drugs": [], "resolution_status": None,
        "patient_context_used": context or {}, "summary": "", "evidence_status": "INSUFFICIENT_EVIDENCE",
        "sources": [], "claims": [], "safety_message": SAFETY, "urgent": bool(intent.urgent_category),
        "urgent_category": intent.urgent_category, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pregnancy_information": [], "lactation_information": [], "reproductive_information": [],
        "general_information": [], "warnings": [], "interactions": [], "monitoring_considerations": [],
        "clinician_discussion_points": [],
        "response_validation_failed": False,
    }
    if intent.urgent_category:
        result.update(summary="This message may describe an emergency. Contact your local emergency service or poison information service now. Do not wait for a chat reply; ask someone nearby to help you get urgent care.", sources=[URGENT_SOURCE], patient_context_used={})
        return result
    resolution = resolve(message, runtime, previous)
    result["resolution_status"] = resolution.status
    if resolution.status != "RESOLVED":
        result["intent"] = ("AMBIGUOUS_DRUG" if resolution.status == "AMBIGUOUS_DRUG" else
                            resolution.status if intent.name != "OUT_OF_SCOPE" else "OUT_OF_SCOPE")
        if resolution.status == "AMBIGUOUS_DRUG":
            result["summary"] = "Please provide the exact medication name from its packaging or a supported generic name. RiskSense cannot identify medication from appearance or purpose alone."
        elif intent.name == "OUT_OF_SCOPE":
            result["summary"] = "RiskSense can help with source-grounded medication, pregnancy and breastfeeding information. Please name the medicine and your question."
        else:
            result.update(evidence_status="UNSUPPORTED_DRUG", summary="The medication could not be matched to the current RiskSense medication catalogue. Please check its exact name with your pharmacist.")
        return result
    if intent.name == "OUT_OF_SCOPE":
        result["intent"] = "DRUG_GENERAL"
    drugs = [public_drug(runtime, drug_id) for drug_id in resolution.drug_ids]
    result.update(drug=drugs[0] if len(drugs) == 1 else None, drugs=drugs)
    provider = provider or CompositeProvider(PublishedEvidenceProvider(), ReviewedLocalProvider(runtime))
    context_ids = tuple(dict.fromkeys(
        item.get("drug_id") for item in (context or {}).get("medications", [])
        if item.get("drug_id") in runtime.drugs
    ))
    asks_about_own_medicines = bool(re.search(
        r"\bmy (?:current |other )?(?:medications|medicines|drugs)\b", normalize(message)))
    compared = tuple(dict.fromkeys((*resolution.drug_ids,
                                    *(context_ids if asks_about_own_medicines else ()))))
    pair_question = result["intent"] == "DRUG_INTERACTION" and len(compared) > 1
    evidence = []
    for drug_id in resolution.drug_ids:
        related = tuple(item for item in compared if item != drug_id)
        evidence.append(provider.retrieve(drug_id, result["intent"], related_drug_ids=related))
    claims, claim_keys = [], set()
    for item in evidence:
        for claim in item.claims:
            if pair_question and not set(claim.get("related_drug_ids", ())).intersection(
                    set(compared) - {claim["drug_id"]}):
                continue  # General label text cannot establish a specific pair.
            key = claim.get("evidence_id") or (claim.get("drug_id"), claim.get("field"), repr(claim.get("content")))
            if key not in claim_keys:
                claim_keys.add(key)
                claims.append(claim)
    cited_urls = {url for claim in claims for url in claim.get("source_urls", ())}
    sources = {source["url"]: source for item in evidence for source in item.sources
               if source["url"] in cited_urls}
    result.update(claims=claims, sources=list(sources.values()))
    if claims:
        statuses = {claim.get("evidence_status") for claim in claims if claim.get("evidence_status")}
        if not statuses:
            statuses = {item.status for item in evidence if item.claims}
        result["evidence_status"] = ("CONFLICTING_EVIDENCE" if "CONFLICTING_EVIDENCE" in statuses else
                                     "SOURCE_SUPPORTED" if statuses == {"SOURCE_SUPPORTED"} else "LIMITED_EVIDENCE")
        result["summary"] = "Reviewed source excerpts are provided below. They do not establish individual suitability or a complete interaction assessment."
    else:
        names = ", ".join(drug["display_name"] for drug in drugs)
        result["summary"] = f"RiskSense does not currently have verified source information for this specific question about {names}. It cannot provide a drug-specific clinical conclusion from the current knowledge base. Missing evidence does not establish safety or absence of risk."
    for claim in claims:
        field = claim["field"]
        bucket = ("pregnancy_information" if field.startswith("pregnancy") else
                  "lactation_information" if field.startswith("lactation") else
                  "reproductive_information" if field.startswith("reproductive_potential") or field in {"fertility", "contraception", "pregnancy_testing"} else
                  "interactions" if "interaction" in field else
                  "warnings" if "warning" in field or "contraindication" in field else
                  "monitoring_considerations" if field == "monitoring" else "general_information")
        result[bucket].append(claim)
    if result["intent"] == "DRUG_MISSED_DOSE_INFORMATION" and not claims:
        result["summary"] += " RiskSense has no verified missed-dose instructions for this medicine; consult its prescription information and your pharmacist or prescriber."
    if result["intent"] in {"DRUG_CLINICIAN_DISCUSSION", "DRUG_PREGNANCY_EXPOSURE", "DRUG_PREGNANCY", "DRUG_LACTATION"}:
        result["clinician_discussion_points"] = ["Which current sources apply to my medication and circumstances?", "What information about exposure timing and my other medicines should I bring?", "What uncertainties should we discuss before any medication decision?"]
    if result["intent"] == "DRUG_INTERACTION":
        supported_pairs = {
            tuple(sorted((claim["drug_id"], related)))
            for claim in claims for related in claim.get("related_drug_ids", [])
        }
        for index, left in enumerate(compared):
            for right in compared[index + 1:]:
                pair = tuple(sorted((left, right)))
                if pair not in supported_pairs:
                    result["interactions"].append({
                        "drug_ids": list(pair), "evidence_status": "INSUFFICIENT_EVIDENCE",
                        "message": "No eligible reviewed pair evidence is available. This does not mean that no interaction exists.",
                    })
    valid, _ = validate_response(result)
    return result if valid else safe_fallback(result)
