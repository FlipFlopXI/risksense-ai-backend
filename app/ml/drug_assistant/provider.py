"""Evidence adapter boundary. Retrieval mappings are not retrieved clinical evidence."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit
from app.ml.drug_assistant.evidence_store import PublishedEvidenceStore, load_published_store
from app.ml.drug_assistant.runtime import DrugRuntime, thaw

FIELDS = {
    "DRUG_GENERAL": ("general.indications", "general.clinical_pharmacology"),
    "DRUG_INDICATION": ("general.indications",),
    "DRUG_CLASS": ("general.clinical_pharmacology",),
    "DRUG_PREGNANCY": ("pregnancy.risk_summary", "pregnancy.human_data", "pregnancy.animal_data", "pregnancy.clinical_considerations"),
    "DRUG_PREGNANCY_EXPOSURE": ("pregnancy.risk_summary", "pregnancy.clinical_considerations", "pregnancy.human_data", "pregnancy.animal_data"),
    "DRUG_PREGNANCY_TIMING": ("pregnancy.clinical_considerations",),
    "DRUG_PREGNANCY_EVIDENCE": ("pregnancy.human_data", "pregnancy.animal_data"),
    "DRUG_PREGNANCY_REGISTRY": ("pregnancy.pregnancy_exposure_registry",),
    "DRUG_LACTATION": ("lactation.risk_summary", "lactation.presence_in_human_milk", "lactation.effects_on_breastfed_child", "lactation.effects_on_milk_production", "lactation.clinical_considerations"),
    "DRUG_REPRODUCTIVE_POTENTIAL": ("reproductive_potential.contraception", "reproductive_potential.infertility_or_fertility", "reproductive_potential.pregnancy_testing"),
    "DRUG_FERTILITY": ("reproductive_potential.infertility_or_fertility",),
    "DRUG_CONTRACEPTION": ("reproductive_potential.contraception",),
    "DRUG_PREGNANCY_TESTING": ("reproductive_potential.pregnancy_testing",),
    "DRUG_SIDE_EFFECT": ("general.adverse_reactions",),
    "DRUG_SERIOUS_WARNING": ("general.warnings_and_precautions",),
    "DRUG_CONTRAINDICATION": ("general.contraindications",),
    "DRUG_INTERACTION": ("general.drug_interactions",),
    # Broad interaction/counselling text cannot answer a specific food/alcohol/dose question.
    "DRUG_FOOD_INTERACTION": ("general.food_interactions",),
    "DRUG_ALCOHOL_INTERACTION": ("general.alcohol_interactions",),
    "DRUG_MISSED_DOSE_INFORMATION": ("general.missed_dose_information",),
    "DRUG_STORAGE": ("general.storage_and_handling",),
    "DRUG_FORMULATION": ("general.dosage_forms_and_strengths",),
    "DRUG_MONITORING": ("monitoring",),
    "DRUG_HEART_CONTEXT": ("condition_context.heart_disease",),
    "DRUG_DIABETES_CONTEXT": ("condition_context.diabetes",),
    "DRUG_PATIENT_CONTEXT": ("condition_context",),
    "DRUG_COMPARISON": ("general.indications", "general.warnings_and_precautions"),
    "DRUG_CLINICIAN_DISCUSSION": ("general.patient_counseling_information",),
    "DRUG_SOURCE_REQUEST": ("general.indications",),
    "DRUG_EVIDENCE_STRENGTH": ("general.indications",),
}


@dataclass(frozen=True)
class Evidence:
    status: str
    claims: tuple[dict, ...] = ()
    sources: tuple[dict, ...] = ()


class DrugKnowledgeProvider(Protocol):
    def retrieve(self, drug_id: str, intent: str, *, related_drug_ids: tuple[str, ...] = ()) -> Evidence: ...


def meaningful(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(meaningful(v) for k, v in value.items() if k not in {"section", "evidence_status", "binary_safe_unsafe_label"})
    if isinstance(value, (tuple, list)):
        return any(meaningful(v) for v in value)
    return False


def reviewed_sources(record: Mapping) -> tuple[dict, ...]:
    provenance = record.get("cache_provenance", {})
    if provenance.get("review_status") != "REVIEWED":
        return ()
    try:
        verified = datetime.fromisoformat(provenance["last_verified_at"].replace("Z", "+00:00"))
        if verified.tzinfo is None or verified > datetime.now(timezone.utc):
            return ()
        urls, hashes = provenance["source_urls"], provenance["source_hashes"]
        if not urls or len(urls) != len(hashes) or not provenance["source_revision_date"]:
            return ()
        result = []
        for url, digest in zip(urls, hashes):
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in {"dailymed.nlm.nih.gov", "www.fda.gov", "www.accessdata.fda.gov", "mothertobaby.org"}:
                return ()
            if parsed.path in ("", "/", "/fact-sheets/") or url in {s["url"] for s in record["sources"].values()}:
                return ()
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                return ()
            result.append({"url": url, "sha256": digest, "reviewed_at": verified.isoformat(), "source_revision_date": provenance["source_revision_date"]})
        return tuple(result)
    except (KeyError, TypeError, ValueError, AttributeError):
        return ()


class ReviewedLocalProvider:
    def __init__(self, runtime: DrugRuntime):
        self.runtime = runtime

    def retrieve(self, drug_id: str, intent: str, *, related_drug_ids: tuple[str, ...] = ()) -> Evidence:
        record = self.runtime.drugs.get(drug_id)
        if record is None:
            return Evidence("UNSUPPORTED_DRUG")
        sources = reviewed_sources(record)
        if not sources:
            return Evidence("INSUFFICIENT_EVIDENCE")
        claims, missing, statuses = [], False, []
        for field in FIELDS.get(intent, ()):
            value = record
            for part in field.split("."):
                value = value.get(part) if isinstance(value, Mapping) else None
            section = record.get(field.split(".")[0], {})
            section_status = section.get("evidence_status") if isinstance(section, Mapping) else None
            if meaningful(value) and section_status not in {"INSUFFICIENT_EVIDENCE", "NOT_CACHED", "UNSUPPORTED_DRUG"}:
                claims.append({"drug_id": drug_id, "field": field, "content": thaw(value), "source_urls": [s["url"] for s in sources]})
                statuses.append(section_status)
            else:
                missing = True
        if not claims:
            return Evidence("INSUFFICIENT_EVIDENCE")
        status = "LIMITED_EVIDENCE" if missing or "LIMITED_EVIDENCE" in statuses else "SOURCE_SUPPORTED"
        if "CONFLICTING_EVIDENCE" in statuses:
            status = "CONFLICTING_EVIDENCE"
        return Evidence(status, tuple(claims), sources)


TOPICS = {
    "DRUG_GENERAL": ("general_information",), "DRUG_INDICATION": ("indications",),
    "DRUG_CLASS": ("class",), "DRUG_IDENTIFICATION": ("identity",), "DRUG_ALIAS": ("identity",),
    "DRUG_PREGNANCY": ("pregnancy",), "DRUG_PREGNANCY_EXPOSURE": ("pregnancy_exposure", "pregnancy"),
    "DRUG_PREGNANCY_TIMING": ("pregnancy_timing",), "DRUG_PREGNANCY_EVIDENCE": ("pregnancy",),
    "DRUG_PREGNANCY_REGISTRY": ("pregnancy_registry",), "DRUG_LACTATION": ("lactation",),
    "DRUG_REPRODUCTIVE_POTENTIAL": ("reproductive_potential",), "DRUG_FERTILITY": ("fertility",),
    "DRUG_CONTRACEPTION": ("contraception",), "DRUG_PREGNANCY_TESTING": ("pregnancy_testing",),
    "DRUG_SIDE_EFFECT": ("adverse_effects",), "DRUG_SERIOUS_WARNING": ("serious_adverse_effects", "warnings"),
    "DRUG_CONTRAINDICATION": ("contraindications",), "DRUG_INTERACTION": ("drug_interactions",),
    "DRUG_FOOD_INTERACTION": ("food_alcohol_interactions",), "DRUG_ALCOHOL_INTERACTION": ("food_alcohol_interactions",),
    "DRUG_MISSED_DOSE_INFORMATION": ("missed_dose",), "DRUG_STORAGE": ("storage",),
    "DRUG_FORMULATION": ("administration",), "DRUG_MONITORING": ("monitoring",),
    "DRUG_HEART_CONTEXT": ("drug_condition_interactions",), "DRUG_DIABETES_CONTEXT": ("drug_condition_interactions",),
    "DRUG_PATIENT_CONTEXT": ("drug_condition_interactions", "drug_interactions"),
    "DRUG_COMPARISON": ("general_information", "warnings"),
    "DRUG_CLINICIAN_DISCUSSION": ("clinician_discussion",),
    "DRUG_SOURCE_REQUEST": ("general_information",), "DRUG_EVIDENCE_STRENGTH": ("general_information",),
}


class PublishedEvidenceProvider:
    """Retrieves only validated, human-reviewed records from the additive store."""

    def __init__(self, store: PublishedEvidenceStore | None = None):
        self.store = store or load_published_store()

    def retrieve(self, drug_id: str, intent: str, *, related_drug_ids: tuple[str, ...] = ()) -> Evidence:
        records = self.store.find(drug_id, TOPICS.get(intent, ()), related_drug_ids)
        if not records:
            return Evidence("INSUFFICIENT_EVIDENCE")
        claims, sources, statuses = [], {}, set()
        for item in records:
            participants = {item["drug_id"], *item["related_drug_ids"]}
            source = {
                "organisation": item["source_organisation"], "title": item["source_title"],
                "url": item["source_url"], "identifier": item["source_identifier"],
                "section": item["source_section"], "source_revision_date": item["source_revision_date"],
                "retrieved_at": item["retrieved_at"], "reviewed_at": item["reviewed_at"],
                "revision": item["revision"], "sha256": item["content_hash"],
            }
            sources[source["url"]] = source
            claims.append({
                "evidence_id": item["evidence_id"], "drug_id": drug_id,
                "evidence_drug_id": item["drug_id"],
                "related_drug_ids": sorted(participants - {drug_id}), "field": item["topic"],
                "subtopic": item["subtopic"], "content": item["claim"],
                "source_urls": [item["source_url"]], "evidence_status": item["evidence_status"],
                "applicable_population": item["applicable_population"],
                "pregnancy_timing": item["pregnancy_timing"],
                "lactation_relevance": item["lactation_relevance"],
            })
            statuses.add(item["evidence_status"])
        status = ("CONFLICTING_EVIDENCE" if "CONFLICTING_EVIDENCE" in statuses else
                  "SOURCE_SUPPORTED" if statuses == {"SOURCE_SUPPORTED"} else "LIMITED_EVIDENCE")
        return Evidence(status, tuple(claims), tuple(sources.values()))


class CompositeProvider:
    def __init__(self, *providers: DrugKnowledgeProvider):
        self.providers = providers

    def retrieve(self, drug_id: str, intent: str, *, related_drug_ids: tuple[str, ...] = ()) -> Evidence:
        results = [provider.retrieve(drug_id, intent, related_drug_ids=related_drug_ids) for provider in self.providers]
        claims = tuple(claim for result in results for claim in result.claims)
        sources = {source["url"]: source for result in results for source in result.sources}
        if not claims:
            return Evidence("INSUFFICIENT_EVIDENCE")
        statuses = {result.status for result in results if result.claims}
        status = ("CONFLICTING_EVIDENCE" if "CONFLICTING_EVIDENCE" in statuses else
                  "SOURCE_SUPPORTED" if statuses == {"SOURCE_SUPPORTED"} else "LIMITED_EVIDENCE")
        return Evidence(status, claims, tuple(sources.values()))
