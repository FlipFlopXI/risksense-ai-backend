"""Fixed JSON configuration. No clinical generation, network access or mutable patient state."""
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Lock
from types import MappingProxyType
import unicodedata

ROOT = Path(__file__).resolve().parent
HASHES = {
    "risksense_drug_assistant_model_v1.json": "204b226dd6dadec6395af07b8e6bc4accadd886de8dcf019db1a94f47bb397e8",
    "risksense_drug_assistant_model_v1_metadata.json": "445695b68e7bbd0859b8d1daa2fa96820dd534031bbf1815e545df9ae3e8c825",
    "drug_knowledge_v1.json": "87286993cfe138528babfb7e313f7b39ae4ba40abe87b48715cdb3c1107b2ceb",
    "drug_knowledge_v1_metadata.json": "5d965635f61dabb904a892b30e9c4deb0eeb63125c0459a70d8f913fb2ae1035",
    "drug_assistant_policy_v1.json": "6efcbedd976b3634eec6b7c47ae2787ca9d04b35eb743aafeb0c2e49352e2876",
}
EVIDENCE_STATES = frozenset({"SOURCE_SUPPORTED", "LIMITED_EVIDENCE", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE", "UNSUPPORTED_DRUG"})
_lock = Lock()


class AssistantUnavailable(Exception):
    def __init__(self):
        super().__init__("Drug Assistant is unavailable.")


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+|_", " ", value).split())


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class DrugRuntime:
    model: Mapping
    knowledge: Mapping
    policy: Mapping
    drugs: Mapping
    aliases: Mapping
    hashes: Mapping


def validate(documents: dict, hashes: dict) -> DrugRuntime:
    try:
        model = documents["risksense_drug_assistant_model_v1.json"]
        meta = documents["risksense_drug_assistant_model_v1_metadata.json"]
        knowledge = documents["drug_knowledge_v1.json"]
        km = documents["drug_knowledge_v1_metadata.json"]
        policy = documents["drug_assistant_policy_v1.json"]
        assert model["artifact_type"] == "source_grounded_assistant_configuration"
        assert all(item["schema_version"] == "1.0.0" and item["knowledge_version"] == "1.0.0"
                   for item in (model, meta, knowledge, km))
        assert policy["policy_version"] == "1.0.0"
        assert km["compatible_with"] == {"assistant_model": "risksense_drug_assistant_model_v1.json", "assistant_model_schema": "1.0.0"}
        for metadata in (meta, km):
            assert metadata["sha256"] == hashes[metadata["artifact_filename"]]
        assert len(model["drugs"]) == len(knowledge["records"]) == 208
        assert all(item["drug_count"] == 208 for item in (model, meta, knowledge, km))
        ids = [item["drug_id"] for item in model["drugs"]]
        records = {item["drug_id"]: item for item in knowledge["records"]}
        assert len(set(ids)) == len(records) == 208 and set(ids) == set(records)
        assert len(model["supported_intents"]) == len(set(model["supported_intents"])) == meta["intent_count"] == 36
        assert model["supported_intents"] == policy["supported_intents"]
        assert set(policy["response_contract"]["evidence_status_values"]) == EVIDENCE_STATES
        assert set(model["pregnancy_framework"]["evidence_states"]) == EVIDENCE_STATES
        assert km["pregnancy_framework"] == {"pregnancy": "8.1", "lactation": "8.2", "females_and_males_of_reproductive_potential": "8.3", "old_A_B_C_D_X_categories_used_by_assistant": False}
        assert policy["grounding"]["clinical_claim_requires_source"] is True
        assert policy["grounding"]["source_citations_required_in_response"] is True
        assert policy["grounding"]["if_no_current_source_and_no_reviewed_cache"] == "RETURN_INSUFFICIENT_EVIDENCE_OR_UNSUPPORTED"
        assert policy["pregnancy"]["never_infer_pregnancy_status"] is True
        assert policy["pregnancy"]["binary_safe_unsafe_output"] is False
        assert policy["pregnancy"]["old_letter_categories_as_primary_risk_system"] is False
        assert policy["patient_context"]["never_fabricate_missing_data"] is True
        assert policy["patient_context"]["minimum_necessary"] is True
        assert policy["authorization"]["effective_entitlement_required_for_patient_specific_chat"] is True
        assert policy["conversation"]["save_sessions"] is True
        assert policy["conversation"]["do_not_assume_across_sessions_without_persisted_authorized_context"] is True
        assert policy["persistence"]["source_provenance_required"] is True
        assert {"prescribe", "change_dose", "stop_medication", "claim_safety_from_missing_evidence", "predict_fetal_outcome"} <= set(policy["prohibited_actions"])
        assert policy["urgent_routing"]["bypass_normal_chat"] is True
        assert policy["urgent_routing"]["categories"] == model["urgent_router"]["triggers"]
        assert km["source_hierarchy"] == ["DailyMed/current prescribing information", "FDA PLLR resources", "MotherToBaby"]
        assert [s["priority"] for s in knowledge["authoritative_source_hierarchy"]] == [1, 1, 2]
        assert [s["url"] for s in model["sources"]] == [s["url"] for s in knowledge["authoritative_source_hierarchy"]]
        aliases: dict[str, set[str]] = {}
        for item in model["drugs"]:
            record = records[item["drug_id"]]
            assert re.fullmatch(r"[a-z0-9_]+", item["drug_id"])
            assert item["generic_name"] == record["generic_name"]
            assert {normalize(a) for a in item["aliases"]} == {normalize(a) for a in record["aliases"]}
            assert item["therapeutic_group"] == record["therapeutic_group"]
            for section, number in (("pregnancy", "8.1"), ("lactation", "8.2"), ("reproductive_potential", "8.3")):
                assert record[section]["section"] == number
            assert {"general", "sources", "cache_provenance", "condition_context", "monitoring"} <= record.keys()
            for alias in (item["generic_name"], item["drug_id"], *item["aliases"]):
                key = normalize(alias)
                assert key
                aliases.setdefault(key, set()).add(item["drug_id"])
        return DrugRuntime(freeze(model), freeze(knowledge), freeze(policy), freeze(records),
                           MappingProxyType({key: tuple(sorted(ids)) for key, ids in aliases.items()}), freeze(hashes))
    except Exception:
        raise AssistantUnavailable() from None


@lru_cache(maxsize=1)
def _load() -> DrugRuntime:
    try:
        documents, hashes = {}, {}
        for filename, expected in HASHES.items():
            data = (ROOT / filename).read_bytes()
            digest = sha256(data).hexdigest()
            if digest != expected:
                raise AssistantUnavailable()
            hashes[filename] = digest
            documents[filename] = json.loads(data)
        return validate(documents, hashes)
    except Exception:
        raise AssistantUnavailable() from None


def load_runtime() -> DrugRuntime:
    with _lock:
        return _load()
