"""Versioned, review-gated evidence store for the Drug Assistant.

The supplied v1 catalogue remains immutable.  This additive store holds reviewed
paraphrases and provenance that can be replaced through the ingestion workflow.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlsplit

from app.ml.drug_assistant.runtime import DrugRuntime, freeze

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "published_evidence_v1.json"
SCHEMA_VERSION = "1.0.0"

REVIEW_STATES = frozenset({"INGESTED", "VALIDATED_STRUCTURE", "REVIEW_REQUIRED", "REVIEWED", "REJECTED", "SUPERSEDED"})
EVIDENCE_STATUSES = frozenset({"SOURCE_SUPPORTED", "LIMITED_EVIDENCE", "CONFLICTING_EVIDENCE"})
ALLOWED_TOPICS = frozenset({
    "general_information", "indications", "class", "identity", "pregnancy",
    "pregnancy_exposure", "pregnancy_timing", "pregnancy_registry", "lactation",
    "reproductive_potential", "fertility", "contraception", "pregnancy_testing",
    "adverse_effects", "serious_adverse_effects", "warnings", "precautions",
    "contraindications", "drug_interactions", "food_alcohol_interactions",
    "missed_dose", "storage", "administration", "monitoring",
    "drug_condition_interactions", "clinician_discussion",
})
ALLOWED_HOSTS = frozenset({
    "dailymed.nlm.nih.gov", "www.fda.gov", "www.accessdata.fda.gov",
    "mothertobaby.org", "www.nhs.uk", "www.sps.nhs.uk", "www.who.int",
    "www.acog.org", "www.heart.org", "diabetes.org",
})


class EvidenceStoreError(Exception):
    """Sanitized evidence-store failure."""


def canonical_hash(record: dict) -> str:
    """Hash content that must trigger re-review when it changes."""
    material = {
        key: record.get(key)
        for key in (
            "drug_id", "related_drug_ids", "topic", "subtopic", "claim",
            "source_organisation", "source_title", "source_url",
            "source_identifier", "source_section", "source_revision_date",
            "applicable_population", "pregnancy_timing", "lactation_relevance",
        )
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _timestamp(value: object, *, required: bool = True) -> datetime | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        raise ValueError("invalid timestamp")
    return parsed


def validate_record(record: dict, runtime: DrugRuntime, *, require_reviewed: bool = False) -> dict:
    required = {
        "evidence_id", "drug_id", "related_drug_ids", "topic", "subtopic", "claim",
        "source_organisation", "source_title", "source_url", "source_identifier",
        "source_section", "source_revision_date", "retrieved_at", "reviewed_at",
        "review_state", "reviewer", "review_mechanism", "revision", "content_hash",
        "evidence_status", "applicable_population", "pregnancy_timing",
        "lactation_relevance", "notes",
    }
    if set(record) != required:
        raise ValueError("evidence fields do not match schema")
    if record["drug_id"] not in runtime.drugs:
        raise ValueError("unknown drug")
    if not isinstance(record.get("evidence_id"), str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{2,199}", record["evidence_id"]):
        raise ValueError("invalid evidence id")
    if record["topic"] not in ALLOWED_TOPICS:
        raise ValueError("unknown evidence topic")
    related = record["related_drug_ids"]
    if not isinstance(related, list) or record["drug_id"] in related or any(item not in runtime.drugs for item in related):
        raise ValueError("invalid related drug")
    if not all(isinstance(record[key], str) and record[key].strip() for key in (
        "evidence_id", "topic", "subtopic", "claim", "source_organisation",
        "source_title", "source_url", "source_identifier", "source_section",
        "source_revision_date", "review_state", "review_mechanism", "revision",
        "content_hash", "evidence_status",
    )):
        raise ValueError("required evidence text is empty")
    parsed = urlsplit(record["source_url"])
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("source is not approved")
    if record["review_state"] not in REVIEW_STATES or record["evidence_status"] not in EVIDENCE_STATUSES:
        raise ValueError("invalid evidence state")
    _timestamp(record["retrieved_at"])
    reviewed_at = _timestamp(record["reviewed_at"], required=False)
    if record["review_state"] == "REVIEWED":
        if reviewed_at is None or not isinstance(record["reviewer"], str) or not record["reviewer"].strip():
            raise ValueError("review metadata required")
        if canonical_hash(record) != record["content_hash"].lower():
            raise ValueError("reviewed content hash mismatch")
    elif require_reviewed:
        raise ValueError("record is not reviewed")
    if len(record["claim"]) > 1600:
        raise ValueError("claim exceeds paraphrase limit")
    return record


@dataclass(frozen=True)
class PublishedEvidenceStore:
    records: tuple[dict, ...]
    by_drug_topic: MappingProxyType
    digest: str

    def find(self, drug_id: str, topics: tuple[str, ...], related_drug_ids: tuple[str, ...] = ()) -> tuple[dict, ...]:
        matches: list[dict] = []
        related = set(related_drug_ids)
        for topic in topics:
            for item in self.by_drug_topic.get((drug_id, topic), ()):
                item_related = set(item["related_drug_ids"])
                participants = {item["drug_id"], *item_related}
                counterparts = participants - {drug_id}
                if item_related and not counterparts.intersection(related):
                    continue
                matches.append(item)
        return tuple(matches)


def load_store(path: Path = STORE_PATH, runtime: DrugRuntime | None = None) -> PublishedEvidenceStore:
    from app.ml.drug_assistant.runtime import load_runtime
    runtime = runtime or load_runtime()
    try:
        data = path.read_bytes()
        document = json.loads(data)
        if document.get("schema_version") != SCHEMA_VERSION or document.get("catalogue_version") != "1.0.0":
            raise ValueError("unsupported store version")
        records = document.get("records")
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        seen, validated, index = set(), [], defaultdict(list)
        for raw in records:
            item = validate_record(raw, runtime, require_reviewed=True)
            if item["evidence_id"] in seen:
                raise ValueError("duplicate evidence id")
            seen.add(item["evidence_id"])
            frozen = freeze(item)
            validated.append(frozen)
            index[(item["drug_id"], item["topic"])].append(frozen)
            for related_id in item["related_drug_ids"]:
                index[(related_id, item["topic"])].append(frozen)
        return PublishedEvidenceStore(tuple(validated), MappingProxyType({key: tuple(value) for key, value in index.items()}), sha256(data).hexdigest())
    except Exception:
        raise EvidenceStoreError("Published drug evidence is unavailable.") from None


@lru_cache(maxsize=1)
def load_published_store() -> PublishedEvidenceStore:
    return load_store()
