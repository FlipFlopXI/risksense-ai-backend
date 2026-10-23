from hashlib import sha256
import json
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from app.ml.drug_assistant.composer import compose
from app.ml.drug_assistant.evidence_normalization import (
    daily_med_sections, mother_sections, normalize_operation, verify_source,
)
from app.ml.drug_assistant.evidence_pipeline import publish, retrieve_dailymed
from app.ml.drug_assistant.evidence_store import load_store
from app.ml.drug_assistant.evidence_store import validate_record
from app.ml.drug_assistant.provider import PublishedEvidenceProvider
from app.ml.drug_assistant.runtime import load_runtime
from app.ml.drug_assistant.source_adapters import DailyMedAdapter
from scripts.review_drug_evidence import record_decision, batch_attest

MOTHER = b'''<!doctype html><html><article><h1 class="entry-title">Metformin</h1>
<div class="entry-content">
<h2>What is metformin?</h2><p>Metformin is a synthetic medicine for test use.</p>
<h2>Breastfeeding while taking metformin:</h2>
<p>Synthetic metformin lactation evidence for testing only.</p>
<h2>Does metformin increase the chance of miscarriage?</h2>
<p>Synthetic metformin pregnancy evidence for testing only.</p>
<h2>Unrelated question</h2><p>No metformin-specific information.</p>
</div></article></html>'''

SPL = b'''<?xml version="1.0"?><document><title>METFORMIN LABEL</title>
<versionNumber value="2"/><section>
<code code="34084-4"/><title>6 ADVERSE REACTIONS</title>
<component><section><text>Synthetic metformin adverse reactions for testing.</text></section></component>
</section><section><code code="42228-7"/><title>8.1 Pregnancy</title>
<text>Synthetic metformin pregnancy information for testing.</text></section>
</document>'''


def _fixture(tmp_path):
    root = tmp_path / "snapshots"
    path = root / "metformin" / "mothertobaby.html"
    path.parent.mkdir(parents=True)
    path.write_bytes(MOTHER)
    operation = {
        "drug_id": "metformin", "canonical_name": "metformin",
        "source_family": "MOTHERTOBABY", "status": "SUCCESS",
        "source_identifier": "fact-sheets:metformin-pregnancy",
        "source_url": "https://mothertobaby.org/fact-sheets/metformin-pregnancy/",
        "source_revision_date": "2026-01-01",
        "retrieved_at": "2026-01-02T00:00:00Z",
        "source_content_hash": sha256(MOTHER).hexdigest(),
    }
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps({"operations": [operation]}))
    candidate_root = tmp_path / "candidates"
    assert normalize_operation(operation, candidate_root, root) == 3
    packages = [
        (path, json.loads(path.read_text()))
        for path in sorted(candidate_root.glob("*.json"))
    ]
    return root, queue_path, packages


def test_mother_and_dailymed_extract_only_present_sections():
    title, sections = mother_sections(MOTHER, "metformin")
    assert title == "Metformin"
    assert {topic for topic, _, _, _ in sections} == {
        "general_information", "lactation", "pregnancy"}
    assert all("metformin" in excerpt.lower() for _, _, _, excerpt in sections)
    title, version, sections = daily_med_sections(SPL)
    assert (title, version) == ("METFORMIN LABEL", "2")
    assert {topic for topic, _, _, _ in sections} == {"adverse_effects", "pregnancy"}
    assert next(excerpt for topic, _, _, excerpt in sections
                if topic == "adverse_effects").startswith("Synthetic metformin")


def test_candidate_provenance_and_review_default(tmp_path):
    root, _, packages = _fixture(tmp_path)
    assert len(packages) == 3
    for _, package in packages:
        record = package["records"][0]
        assert record["review_state"] == "REVIEW_REQUIRED"
        assert record["reviewer"] is None and record["reviewed_at"] is None
        assert record["source_url"].startswith("https://mothertobaby.org/")
        assert package["provenance"]["source_content_hash"] == sha256(MOTHER).hexdigest()
        verify_source(package, root)


def test_review_decisions_and_publication_gate(tmp_path):
    root, queue, packages = _fixture(tmp_path)
    pending_path, pending = packages[0]
    store_path = tmp_path / "published.json"
    with pytest.raises(ValueError, match="not reviewed"):
        publish([pending_path], store_path, queue_path=queue, snapshot_root=root)
    approved = record_decision(pending["records"][0], reviewer="Test reviewer",
                               decision="approve")
    pending["records"][0] = approved
    pending_path.write_text(json.dumps(pending))
    published = publish([pending_path], store_path, queue_path=queue, snapshot_root=root)
    assert len(published["records"]) == 1
    assert published["records"][0]["review_state"] == "REVIEWED"
    assert len(load_store(store_path).records) == 1
    partial = record_decision(packages[1][1]["records"][0], reviewer="Test reviewer",
                              decision="partial")
    rejected = record_decision(packages[2][1]["records"][0], reviewer="Test reviewer",
                               decision="reject")
    assert partial["evidence_status"] == "LIMITED_EVIDENCE"
    assert rejected["review_state"] == "REJECTED"
    with pytest.raises(ValueError, match="not reviewed"):
        packages[2][1]["records"][0] = rejected
        packages[2][0].write_text(json.dumps(packages[2][1]))
        publish([packages[2][0]], store_path, queue_path=queue, snapshot_root=root)


def test_source_change_and_mismatch_block_publication(tmp_path):
    root, queue, packages = _fixture(tmp_path)
    path, package = packages[0]
    package["records"][0] = record_decision(
        package["records"][0], reviewer="Test reviewer", decision="approve")
    path.write_text(json.dumps(package))
    package["records"][0]["drug_id"] = "atorvastatin"
    with pytest.raises(ValueError, match="does not match"):
        verify_source(package, root)
    package["records"][0]["drug_id"] = "metformin"
    package["records"][0]["source_url"] = "https://mothertobaby.org/fact-sheets/other/"
    with pytest.raises(ValueError, match="does not match"):
        verify_source(package, root)
    package["records"][0]["source_url"] = package["provenance"]["operation"]["source_url"]
    package["records"][0]["topic"] = "invented_topic"
    with pytest.raises(ValueError, match="unknown evidence topic"):
        validate_record(package["records"][0], load_runtime())
    package["records"][0]["topic"] = "general_information"
    (root / "metformin" / "mothertobaby.html").write_bytes(MOTHER + b"changed")
    with pytest.raises(ValueError, match="changed"):
        publish([path], tmp_path / "store.json", queue_path=queue, snapshot_root=root)


def test_ambiguous_product_needs_explicit_selection(tmp_path):
    class Transport:
        def get(self, url):
            return json.dumps({"data": [
                {"setid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "title": "Metformin A"},
                {"setid": "ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee", "title": "Metformin B"},
            ]}).encode(), {}

    queue = retrieve_dailymed(
        1, tmp_path / "queue.json", tmp_path / "snapshots",
        DailyMedAdapter(Transport()))
    row = next(item for item in queue["operations"]
               if item["source_family"] == "DAILYMED")
    assert row["status"] == "PARTIAL"
    assert row["source_identifier"] is None
    assert len(row["candidates"]) == 2
    assert not list((tmp_path / "snapshots").rglob("*.xml"))


def test_published_candidate_keeps_citation_integrity(tmp_path):
    root, queue, packages = _fixture(tmp_path)
    path, package = next((path, package) for path, package in packages
                         if package["records"][0]["topic"] == "pregnancy")
    package["records"][0] = record_decision(
        package["records"][0], reviewer="Test reviewer", decision="approve")
    path.write_text(json.dumps(package))
    store_path = tmp_path / "published.json"
    publish([path], store_path, queue_path=queue, snapshot_root=root)
    result = compose("Can I take metformin while pregnant?", load_runtime(),
                     provider=PublishedEvidenceProvider(load_store(store_path)))
    assert result["evidence_status"] == "SOURCE_SUPPORTED"
    assert result["response_validation_failed"] is False
    assert result["claims"][0]["source_urls"] == [result["sources"][0]["url"]]


def test_batch_attestation_requires_explicit_scope_and_preserves_claims(tmp_path, monkeypatch):
    root, queue, packages = _fixture(tmp_path)
    candidate_root = tmp_path / "candidates"
    args = SimpleNamespace(
        attest_reviewed=False, reviewer="External reviewer", dry_run=True)
    with pytest.raises(SystemExit, match="attest-reviewed"):
        batch_attest(args, candidate_root=candidate_root, queue_path=queue,
                     snapshot_root=root, backup_root=tmp_path / "backups")
    args.attest_reviewed = True
    before = {path.name: path.read_bytes() for path, _ in packages}
    dry = batch_attest(args, candidate_root=candidate_root, queue_path=queue,
                       snapshot_root=root, backup_root=tmp_path / "backups")
    assert dry["APPROVED"] == 0
    assert all(path.read_bytes() == before[path.name] for path, _ in packages)
    assert not (tmp_path / "backups").exists()
    args.dry_run = False
    monkeypatch.setattr("builtins.input", lambda _: "APPROVE 3 REVIEWED RECORDS")
    outcome = batch_attest(args, candidate_root=candidate_root, queue_path=queue,
                           snapshot_root=root, backup_root=tmp_path / "backups")
    assert outcome["APPROVED"] == 3
    backups = list((tmp_path / "backups").glob("*.zip"))
    assert len(backups) == 1
    with ZipFile(backups[0]) as archive:
        assert len(archive.namelist()) == 4
        assert archive.read(packages[0][0].name) == before[packages[0][0].name]
    for path, original in packages:
        updated = json.loads(path.read_text())["records"][0]
        prior = original["records"][0]
        assert updated["review_state"] == "REVIEWED"
        assert updated["reviewer"] == "External reviewer"
        assert updated["review_mechanism"] == "EXTERNAL_HUMAN_REVIEW_BATCH"
        assert updated["content_hash"] == prior["content_hash"]
        assert updated["claim"] == prior["claim"]
        assert updated["evidence_status"] == prior["evidence_status"]


def test_batch_attestation_skips_stale_and_rejected_candidates(tmp_path):
    root, queue, packages = _fixture(tmp_path)
    rejected_path, rejected_package = packages[0]
    rejected_package["records"][0] = record_decision(
        rejected_package["records"][0], reviewer="Reviewer", decision="reject")
    rejected_path.write_text(json.dumps(rejected_package))
    changed_path, _ = packages[1]
    changed_package = json.loads(changed_path.read_text())
    changed_package["records"][0]["claim"] = "Unreviewed changed content"
    changed_path.write_text(json.dumps(changed_package))
    args = SimpleNamespace(
        attest_reviewed=True, reviewer="External reviewer", dry_run=True)
    outcome = batch_attest(args, candidate_root=tmp_path / "candidates",
                           queue_path=queue, snapshot_root=root)
    assert outcome["REJECTED_UNCHANGED"] == 1
    assert outcome["SKIPPED_INVALID"] == 1
    assert outcome["APPROVED"] == 0
