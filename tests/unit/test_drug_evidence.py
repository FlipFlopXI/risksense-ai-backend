from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.ml.drug_assistant.composer import compose
from app.ml.drug_assistant.evidence_pipeline import bootstrap_queue, generate_coverage, retrieve_dailymed
from app.ml.drug_assistant.evidence_store import EvidenceStoreError, canonical_hash, load_store
from app.ml.drug_assistant.provider import CompositeProvider, Evidence, PublishedEvidenceProvider, ReviewedLocalProvider
from app.ml.drug_assistant.response_validator import validate_response
from app.ml.drug_assistant.runtime import load_runtime
from app.ml.drug_assistant.source_adapters import DailyMedAdapter, SourceRetrievalError


def evidence_record(**changes):
    record = {
        "evidence_id": "synthetic-metformin-atorvastatin-interaction-v1",
        "drug_id": "metformin", "related_drug_ids": ["atorvastatin"],
        "topic": "drug_interactions", "subtopic": "pair_evidence",
        "claim": "Synthetic reviewed interaction evidence used only by this automated test.",
        "source_organisation": "DailyMed", "source_title": "Synthetic test label",
        "source_url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=synthetic-test",
        "source_identifier": "synthetic-test", "source_section": "7 DRUG INTERACTIONS",
        "source_revision_date": "2026-01-01", "retrieved_at": "2026-01-02T00:00:00Z",
        "reviewed_at": "2026-01-03T00:00:00Z", "review_state": "REVIEWED",
        "reviewer": "synthetic-test-reviewer", "review_mechanism": "two-person-test-fixture",
        "revision": "1", "content_hash": "", "evidence_status": "SOURCE_SUPPORTED",
        "applicable_population": "synthetic test population", "pregnancy_timing": None,
        "lactation_relevance": None, "notes": "Not clinical evidence.",
    }
    record.update(changes)
    record["content_hash"] = canonical_hash(record)
    return record


def write_store(path: Path, records: list[dict]):
    path.write_text(json.dumps({"schema_version": "1.0.0", "catalogue_version": "1.0.0",
                                "generated_at": "2026-01-03T00:00:00Z", "records": records}), encoding="utf-8")


def test_published_pair_evidence_and_citation_integrity(tmp_path):
    path = tmp_path / "store.json"
    write_store(path, [evidence_record()])
    provider = PublishedEvidenceProvider(load_store(path))
    result = compose("Does atorvastatin interact with metformin?", load_runtime(), provider=provider)
    assert result["evidence_status"] == "SOURCE_SUPPORTED"
    assert len(result["claims"]) == 1 and len(result["sources"]) == 1
    assert not result["response_validation_failed"]
    assert result["claims"][0]["source_urls"] == [result["sources"][0]["url"]]
    assert not any(item.get("evidence_status") == "INSUFFICIENT_EVIDENCE" for item in result["interactions"])


def test_conflicting_evidence_remains_explicit(tmp_path):
    first = evidence_record(evidence_status="CONFLICTING_EVIDENCE")
    second = evidence_record(evidence_id="synthetic-conflict-v2", claim="A second synthetic reviewed statement for conflict testing.", evidence_status="CONFLICTING_EVIDENCE")
    path = tmp_path / "store.json"
    write_store(path, [first, second])
    result = compose("Does metformin interact with atorvastatin?", load_runtime(),
                     provider=PublishedEvidenceProvider(load_store(path)))
    assert result["evidence_status"] == "CONFLICTING_EVIDENCE"
    assert len(result["claims"]) == 2


@pytest.mark.parametrize("mutation", ["changed_claim", "unreviewed", "unapproved_host"])
def test_store_fails_closed_on_ineligible_record(tmp_path, mutation):
    record = evidence_record()
    if mutation == "changed_claim":
        record["claim"] = "Changed after review."
    elif mutation == "unreviewed":
        record.update(review_state="REVIEW_REQUIRED", reviewed_at=None, reviewer=None)
        record["content_hash"] = canonical_hash(record)
    else:
        record["source_url"] = "https://example.invalid/claim"
        record["content_hash"] = canonical_hash(record)
    path = tmp_path / "store.json"
    write_store(path, [record])
    with pytest.raises(EvidenceStoreError):
        load_store(path)


def test_response_validator_rejects_fabricated_citation():
    payload = {
        "urgent": False, "intent": "DRUG_INTERACTION", "drugs": [{"drug_id": "metformin"}],
        "sources": [{"url": "https://dailymed.nlm.nih.gov/real"}],
        "claims": [{"drug_id": "metformin", "field": "drug_interactions", "source_urls": ["https://www.fda.gov/fabricated"]}],
    }
    valid, reason = validate_response(payload)
    assert not valid and reason == "claim citation was not retrieved"


def test_queue_and_coverage_process_every_catalogue_medication(tmp_path):
    queue = bootstrap_queue(tmp_path / "queue.json")
    empty_store = tmp_path / "empty-store.json"
    empty_store.write_text(json.dumps({"schema_version": "1.0.0", "catalogue_version": "1.0.0", "records": []}), encoding="utf-8")
    coverage = generate_coverage(tmp_path / "coverage.json", empty_store)
    assert len(queue["operations"]) == 416
    assert coverage["catalogue_medications"] == coverage["processed_medications"] == 208
    assert {row["overall_coverage_status"] for row in coverage["records"]} == {"INSUFFICIENT"}
    assert len({row["drug_id"] for row in coverage["records"]}) == 208


def test_dailymed_adapter_and_restartable_queue(tmp_path):
    class Transport:
        calls = []
        def get(self, url):
            self.calls.append(url)
            if "spls.json" in url:
                return json.dumps({"data": [{"setid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "title": "Synthetic"}]}).encode(), {}
            return b'<?xml version="1.0"?><document/>', {"x-dailymed-label-last-updated": "2026-01-01"}
    transport = Transport()
    adapter = DailyMedAdapter(transport)
    queue_path = tmp_path / "queue.json"
    snapshot_root = tmp_path / "snapshots"
    result = retrieve_dailymed(1, queue_path, snapshot_root, adapter)
    completed = [item for item in result["operations"] if item["status"] == "SUCCESS"]
    assert len(completed) == 1 and len(completed[0]["source_content_hash"]) == 64
    assert list(snapshot_root.rglob("*.xml"))
    previous_calls = len(transport.calls)
    retrieve_dailymed(1, queue_path, snapshot_root, adapter)
    assert len(transport.calls) > previous_calls  # next operation runs; completed one is skipped


def test_dailymed_adapter_rejects_arbitrary_identifier():
    with pytest.raises(SourceRetrievalError):
        DailyMedAdapter().retrieve("../../secrets")


def test_golden_question_set():
    cases = json.loads(Path("tests/data/drug_assistant_golden_v1.json").read_text(encoding="utf-8"))["cases"]
    runtime = load_runtime()
    class EmptyPublishedProvider:
        def retrieve(self, drug_id, intent, *, related_drug_ids=()):
            return Evidence("INSUFFICIENT_EVIDENCE")
    provider = CompositeProvider(EmptyPublishedProvider(), ReviewedLocalProvider(runtime))
    for case in cases:
        result = compose(case["question"], runtime, tuple(case.get("previous", [])), provider=provider)
        assert result["intent"] == case["intent"], case["question"]
        assert [item["drug_id"] for item in result["drugs"]] == case["drug_ids"], case["question"]
        assert result["evidence_status"] == case["evidence_status"], case["question"]
        assert result["urgent"] is case["urgent"], case["question"]
        serialized = json.dumps(result)
        for required in case.get("required", []):
            assert required.lower() in serialized.lower(), case["question"]
        for forbidden in case.get("forbidden", []):
            assert forbidden.lower() not in serialized.lower(), case["question"]


def test_real_published_metformin_coverage_and_uncovered_topics():
    runtime = load_runtime()
    for question, expected_status, expected_count in (
        ("What is metformin?", "LIMITED_EVIDENCE", 1),
        ("Can I take metformin while pregnant?", "LIMITED_EVIDENCE", 5),
        ("Can I take metformin while breastfeeding?", "LIMITED_EVIDENCE", 1),
        ("What are the side effects of metformin?", "INSUFFICIENT_EVIDENCE", 0),
        ("Does metformin interact with my other medications?", "INSUFFICIENT_EVIDENCE", 0),
    ):
        result = compose(question, runtime)
        assert result["evidence_status"] == expected_status
        assert len(result["claims"]) == expected_count
        assert not result["response_validation_failed"]
        cited = {source["url"] for source in result["sources"]}
        assert all(set(claim["source_urls"]) <= cited for claim in result["claims"])
