from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from app.ml.drug_assistant import runtime
from app.ml.drug_assistant.composer import compose
from app.ml.drug_assistant.intent import classify, RULES
from app.ml.drug_assistant.provider import Evidence, ReviewedLocalProvider
from app.ml.drug_assistant.resolver import resolve
from app.schemas.drug_assistant import ChatRequest
from app.schemas.reproductive import ReproductiveFields
from app.schemas.patient_medication import MedicationCreate


def documents():
    return {name: json.loads((runtime.ROOT / name).read_bytes()) for name in runtime.HASHES}


def test_fixed_artifacts_validate_without_changes():
    loaded = runtime.load_runtime()
    assert len(loaded.drugs) == 208
    assert len(loaded.model["supported_intents"]) == 36
    assert set(name for name, _ in RULES) | {"UNSUPPORTED_DRUG", "AMBIGUOUS_DRUG", "EMERGENCY_OR_URGENT", "OUT_OF_SCOPE"} == set(loaded.policy["supported_intents"])
    for name, digest in runtime.HASHES.items():
        assert sha256((runtime.ROOT / name).read_bytes()).hexdigest() == digest
    with pytest.raises(TypeError):
        loaded.drugs["metformin"]["pregnancy"]["risk_summary"] = "safe"
    assert runtime.load_runtime() is loaded


@pytest.mark.parametrize("change", ["schema", "version", "count", "duplicate", "intent", "policy", "hash", "hierarchy", "alias", "pregnancy"])
def test_contract_mutations_fail_closed(change):
    data = documents()
    model = data["risksense_drug_assistant_model_v1.json"]
    if change == "schema": model["schema_version"] = "2"
    elif change == "version": model["knowledge_version"] = "2"
    elif change == "count": model["drug_count"] = 1
    elif change == "duplicate": model["drugs"][1]["drug_id"] = model["drugs"][0]["drug_id"]
    elif change == "intent": model["supported_intents"].pop()
    elif change == "policy": del data["drug_assistant_policy_v1.json"]["grounding"]
    elif change == "hash": data["drug_knowledge_v1_metadata.json"]["sha256"] = "bad"
    elif change == "hierarchy": data["drug_knowledge_v1_metadata.json"]["source_hierarchy"] = []
    elif change == "alias": model["drugs"][0]["aliases"] = ["metformin"]
    else: data["drug_knowledge_v1.json"]["records"][0]["pregnancy"]["section"] = "A"
    with pytest.raises(runtime.AssistantUnavailable, match="unavailable"):
        runtime.validate(data, runtime.HASHES)


@pytest.mark.parametrize("failure", ["missing", "malformed", "hash"])
def test_file_failures_sanitized(monkeypatch, failure):
    # A small path object permits error injection without temporary file permissions.
    class Path:
        def __truediv__(self, name): return self
        def read_bytes(self):
            if failure == "missing": raise FileNotFoundError("private/server/path")
            return b"{" if failure == "malformed" else b"modified"
    monkeypatch.setattr(runtime, "ROOT", Path())
    if failure == "malformed":
        monkeypatch.setattr(runtime, "HASHES", {"bad.json": sha256(b"{").hexdigest()})
    with pytest.raises(runtime.AssistantUnavailable) as error:
        runtime._load.__wrapped__()
    assert "private" not in str(error.value)


@pytest.mark.parametrize("name,drug_id", [
    ("metformin", "metformin"), (" METFORMIN ", "metformin"), ("paracetamol", "acetaminophen"),
    ("salbutamol", "albuterol"), ("glibenclamide", "glyburide"),
    ("isophane  insulin", "nph_insulin"), ("TMP-SMX", "trimethoprim_sulfamethoxazole"),
    ("co-trimoxazole", "trimethoprim_sulfamethoxazole"), ("trimethoprim/sulfamethoxazole", "trimethoprim_sulfamethoxazole"),
])
def test_drug_aliases(name, drug_id):
    assert resolve(name, runtime.load_runtime()).drug_ids == (drug_id,)


def test_unknown_ambiguous_and_no_fuzzy_matching():
    loaded = runtime.load_runtime()
    assert resolve("metforminn", loaded).status == "UNSUPPORTED_DRUG"
    assert resolve("a little blue pill", loaded, ("metformin",)).status == "AMBIGUOUS_DRUG"
    assert resolve("this medicine", loaded).status == "AMBIGUOUS_DRUG"
    assert resolve("this medicine", loaded, ("metformin",)).drug_ids == ("metformin",)
    assert resolve("What is unknownmed?", loaded, ("metformin",)).status == "UNSUPPORTED_DRUG"
    collisions = replace(loaded, aliases={"shared": ("metformin", "atorvastatin")})
    assert resolve("shared", collisions).status == "AMBIGUOUS_DRUG"
    assert resolve("What about breastfeeding?", loaded, ("atorvastatin",)).drug_ids == ("atorvastatin",)
    assert resolve("Can I take it?", loaded, ("metformin", "atorvastatin")).status == "AMBIGUOUS_DRUG"


INTENTS = [
    ("What is metformin?", "DRUG_GENERAL"), ("What is metformin used for?", "DRUG_INDICATION"),
    ("What drug class is metformin?", "DRUG_CLASS"), ("Identify metformin", "DRUG_IDENTIFICATION"),
    ("Another name for metformin?", "DRUG_ALIAS"),
    ("Can I use metformin if I'm pregnant?", "DRUG_PREGNANCY"),
    ("Is metformin okay in pregnancy?", "DRUG_PREGNANCY"),
    ("I just found out I'm pregnant and take metformin", "DRUG_PREGNANCY_EXPOSURE"),
    ("I took metformin before I knew I was pregnant", "DRUG_PREGNANCY_EXPOSURE"),
    ("First trimester metformin exposure", "DRUG_PREGNANCY_TIMING"),
    ("Is there human evidence for metformin?", "DRUG_PREGNANCY_EVIDENCE"),
    ("Is there a pregnancy exposure registry?", "DRUG_PREGNANCY_REGISTRY"),
    ("I'm breastfeeding, what information exists about metformin?", "DRUG_LACTATION"),
    ("Trying to conceive on metformin", "DRUG_REPRODUCTIVE_POTENTIAL"),
    ("Does metformin affect fertility?", "DRUG_FERTILITY"), ("Metformin contraception information", "DRUG_CONTRACEPTION"),
    ("Does the metformin label mention pregnancy testing?", "DRUG_PREGNANCY_TESTING"),
    ("What are atorvastatin's side effects?", "DRUG_SIDE_EFFECT"),
    ("Serious warnings for atorvastatin", "DRUG_SERIOUS_WARNING"),
    ("Atorvastatin contraindications", "DRUG_CONTRAINDICATION"),
    ("Does atorvastatin interact with my other medicine?", "DRUG_INTERACTION"),
    ("Atorvastatin and grapefruit", "DRUG_FOOD_INTERACTION"), ("Metformin and alcohol", "DRUG_ALCOHOL_INTERACTION"),
    ("Monitoring with metformin", "DRUG_MONITORING"), ("How to store metformin", "DRUG_STORAGE"),
    ("Metformin liquid formulation", "DRUG_FORMULATION"), ("Aspirin with my heart disease", "DRUG_HEART_CONTEXT"),
    ("Does my diabetes matter for metformin?", "DRUG_DIABETES_CONTEXT"), ("Does my profile matter for this medicine?", "DRUG_PATIENT_CONTEXT"),
    ("Compare metformin versus glipizide", "DRUG_COMPARISON"),
    ("Where did you get that information?", "DRUG_SOURCE_REQUEST"), ("How recent is the evidence?", "DRUG_EVIDENCE_STRENGTH"),
    ("What should I ask my doctor about this medicine?", "DRUG_CLINICIAN_DISCUSSION"),
    ("I missed my metformin dose", "DRUG_MISSED_DOSE_INFORMATION"), ("Write a poem about the ocean", "OUT_OF_SCOPE"),
]


@pytest.mark.parametrize("message,expected", INTENTS)
def test_intent_variants(message, expected):
    assert classify(message).name == expected


@pytest.mark.parametrize("message", ["I took 40 tablets and I feel sick", "I can't breathe after taking this", "My face is swelling",
    "I passed out", "I'm bleeding heavily", "I have a severe medication reaction", "I am in immediate danger",
    "I am pregnant with severe pain", "My baby has stopped moving", "I took too much", "I have a seizure"])
def test_urgent_precedes_resolution_and_education(message):
    provider = Mock(side_effect=AssertionError("No ordinary retrieval in an emergency"))
    result = compose(message, runtime.load_runtime(), provider=provider)
    assert result["urgent"] and result["intent"] == "EMERGENCY_OR_URGENT"
    assert result["claims"] == [] and len(result["summary"]) < 400
    provider.retrieve.assert_not_called()


@pytest.mark.parametrize("message", ["Can I take metformin while pregnant?", "I took metformin before I knew I was pregnant",
    "Can I breastfeed while taking metformin?", "Metformin and glipizide interaction", "Atorvastatin side effects", "I missed my metformin dose"])
def test_null_evidence_never_becomes_clinical_claim(message):
    empty_provider = Mock()
    empty_provider.retrieve.return_value = Evidence("INSUFFICIENT_EVIDENCE")
    result = compose(message, runtime.load_runtime(), provider=empty_provider)
    assert result["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["claims"] == result["sources"] == []
    assert result["patient_context_used"] == {}
    for prohibited in ("is safe", "no interaction", "stop taking", "double your dose", "fetal harm", "category A", "category X"):
        assert prohibited not in result["summary"]


def reviewed_runtime():
    loaded = runtime.load_runtime()
    records = runtime.thaw(loaded.drugs)
    record = records["metformin"]
    record["cache_provenance"] = {"review_status": "REVIEWED", "last_verified_at": "2026-01-01T00:00:00Z",
        "source_urls": ["https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=synthetic-test"],
        "source_hashes": ["0" * 64], "source_revision_date": "2025-12-01"}
    record["general"]["indications"] = "Synthetic reviewed excerpt for testing only."
    return replace(loaded, drugs=runtime.freeze(records))


def test_future_reviewed_content_with_provenance():
    result = compose("What is metformin used for?", reviewed_runtime())
    assert result["evidence_status"] == "SOURCE_SUPPORTED"
    assert result["claims"][0]["source_urls"] == [result["sources"][0]["url"]]
    assert result["sources"][0]["reviewed_at"]
    assert compose("What is metformin?", reviewed_runtime())["evidence_status"] == "LIMITED_EVIDENCE"


@pytest.mark.parametrize("status", ["CONFLICTING_EVIDENCE", "LIMITED_EVIDENCE", "NOT_CACHED", "INSUFFICIENT_EVIDENCE"])
def test_section_status_cannot_be_overridden_by_nonnull_text(status):
    loaded = reviewed_runtime()
    records = runtime.thaw(loaded.drugs)
    records["metformin"]["pregnancy"]["human_data"] = "Synthetic test evidence only."
    records["metformin"]["pregnancy"]["evidence_status"] = status
    altered = replace(loaded, drugs=runtime.freeze(records))
    result = compose("What human evidence exists for metformin?", altered, provider=ReviewedLocalProvider(altered))
    if status in {"INSUFFICIENT_EVIDENCE", "NOT_CACHED"}:
        assert not result["claims"] and result["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    else:
        assert result["evidence_status"] == status


@pytest.mark.parametrize("mutation", ["unreviewed", "homepage", "no_date", "no_hash", "wrong_host", "future"])
def test_provenance_is_required(mutation):
    loaded = reviewed_runtime()
    records = runtime.thaw(loaded.drugs)
    cache = records["metformin"]["cache_provenance"]
    if mutation == "unreviewed": cache["review_status"] = "NOT_REVIEWED"
    elif mutation == "homepage": cache["source_urls"] = ["https://dailymed.nlm.nih.gov/"]
    elif mutation == "no_date": cache["last_verified_at"] = None
    elif mutation == "no_hash": cache["source_hashes"] = []
    elif mutation == "wrong_host": cache["source_urls"] = ["https://untrusted.example/claim"]
    else: cache["last_verified_at"] = "2100-01-01T00:00:00Z"
    result = ReviewedLocalProvider(replace(loaded, drugs=runtime.freeze(records))).retrieve("metformin", "DRUG_INDICATION")
    assert result.status == "INSUFFICIENT_EVIDENCE" and not result.claims


def test_optional_reproductive_data_and_validation():
    assert ReproductiveFields().pregnancy_status is None
    with pytest.raises(ValidationError): ReproductiveFields(infant_date_of_birth=date.today() + timedelta(days=1))
    with pytest.raises(ValidationError): ReproductiveFields(estimated_due_date=date.today() + timedelta(days=500))
    with pytest.raises(ValidationError): ReproductiveFields(pregnancy_status="NOT_PREGNANT", estimated_due_date=date.today())
    assert ReproductiveFields(pregnancy_status="PREFER_NOT_TO_SAY").estimated_due_date is None


def test_urgent_state_continues_before_normal_education():
    result = compose("What is metformin?", runtime.load_runtime(), pending_urgent="suspected_overdose")
    assert result["urgent"] and result["intent"] == "EMERGENCY_OR_URGENT"
    assert not result["claims"]


def test_medication_input_validation():
    with pytest.raises(ValidationError): MedicationCreate(display_name=" ")
    with pytest.raises(ValidationError): MedicationCreate(display_name="metformin", start_date=date(2026, 1, 2), end_date=date(2026, 1, 1))
    assert MedicationCreate(display_name="metformin").dose is None


@pytest.mark.parametrize("message", ["password=secret", "Authorization: Bearer pretend-token", "postgresql://secret", "api_key: private"])
def test_credentials_rejected_before_persistence(message):
    with pytest.raises(ValidationError): ChatRequest(message=message)
