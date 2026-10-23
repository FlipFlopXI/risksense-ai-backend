"""Explicit human review workbench for Drug Assistant evidence candidates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.ml.drug_assistant.evidence_pipeline import QUEUE_PATH, WORK_ROOT
from app.ml.drug_assistant.evidence_store import canonical_hash, validate_record
from app.ml.drug_assistant.evidence_normalization import (
    verify_source, _snapshot, mother_sections, daily_med_sections,
)
from hashlib import sha256
from app.ml.drug_assistant.runtime import load_runtime

CANDIDATE_ROOT = WORK_ROOT / "candidates"
PRIORITY = {"pregnancy": 1, "lactation": 2, "reproductive_potential": 3, "drug_interactions": 4,
            "serious_adverse_effects": 5, "warnings": 5, "contraindications": 6,
            "adverse_effects": 7, "monitoring": 8, "general_information": 9}


def candidates():
    pending = []
    for path in sorted(CANDIDATE_ROOT.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for record in document.get("records", []):
            pending.append((path, document, record))
    yield from sorted(pending, key=lambda item: (PRIORITY.get(item[2].get("topic"), 99), item[2].get("drug_id", "")))


def list_queue(status: str | None) -> int:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    rows = [item for item in queue["operations"] if status is None or item["status"] == status]
    for item in rows:
        print(json.dumps(item, indent=2))
    print(f"Source operations matched: {len(rows)}")
    return 0


def draft(args) -> int:
    runtime = load_runtime()
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    operation = next((item for item in queue["operations"] if item["drug_id"] == args.drug_id
                      and item["source_family"] == args.source_family), None)
    if operation is None or operation.get("status") != "SUCCESS" or not operation.get("source_url"):
        raise SystemExit("A uniquely selected SUCCESS source operation is required before drafting evidence.")
    now = datetime.now(timezone.utc).isoformat()
    evidence_id = args.evidence_id or f"{args.drug_id}-{args.topic}-{operation['source_content_hash'][:12]}"
    record = {
        "evidence_id": evidence_id, "drug_id": args.drug_id,
        "related_drug_ids": args.related_drug_id or [], "topic": args.topic, "subtopic": args.subtopic,
        "claim": args.claim, "source_organisation": args.source_family,
        "source_title": args.source_title, "source_url": operation["source_url"],
        "source_identifier": operation["source_identifier"], "source_section": args.source_section,
        "source_revision_date": operation.get("source_revision_date") or args.source_revision_date,
        "retrieved_at": operation["retrieved_at"], "reviewed_at": None,
        "review_state": "REVIEW_REQUIRED", "reviewer": None, "review_mechanism": "explicit_cli_review",
        "revision": "1", "content_hash": "", "evidence_status": args.evidence_status,
        "applicable_population": args.applicable_population, "pregnancy_timing": args.pregnancy_timing,
        "lactation_relevance": args.lactation_relevance, "notes": args.notes,
    }
    record["content_hash"] = canonical_hash(record)
    validate_record(record, load_runtime())
    source_path = _snapshot(operation, WORK_ROOT / "snapshots")
    if sha256(source_path.read_bytes()).hexdigest() != operation["source_content_hash"]:
        raise SystemExit("Retrieved source content changed; retrieve and review again.")
    if operation["source_family"] == "MOTHERTOBABY":
        actual_title, sections = mother_sections(source_path.read_bytes(), operation["canonical_name"])
    else:
        actual_title, _, sections = daily_med_sections(source_path.read_bytes())
    matching_section = next((excerpt for _, _, section, excerpt in sections
                             if section == args.source_section), None)
    if actual_title != args.source_title or matching_section is None:
        raise SystemExit("Source title or section does not match the retrieved snapshot.")
    document = {"schema_version": "1.0.0", "records": [record],
                "provenance": {"operation": operation,
                               "source_content_hash": operation["source_content_hash"],
                               "source_product_identifier": operation["source_identifier"],
                               "source_version": operation.get("source_revision_date"),
                               "canonical_name": operation["canonical_name"],
                               "therapeutic_group": runtime.drugs[args.drug_id]["therapeutic_group"],
                               "source_excerpt": matching_section[:5000]}}
    CANDIDATE_ROOT.mkdir(parents=True, exist_ok=True)
    path = CANDIDATE_ROOT / f"{evidence_id}.json"
    if path.exists():
        raise SystemExit("Candidate already exists; choose a new evidence ID or review the existing candidate.")
    path.write_text(json.dumps(document, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"REVIEW_REQUIRED: {evidence_id}")
    return 0


def list_candidates(drug_id: str | None, topic: str | None) -> int:
    count = 0
    for path, _, record in candidates():
        if drug_id and record.get("drug_id") != drug_id:
            continue
        if topic and record.get("topic") != topic:
            continue
        count += 1
        print(json.dumps({key: record.get(key) for key in (
            "evidence_id", "drug_id", "topic", "subtopic", "claim", "source_organisation",
            "source_title", "source_url", "source_identifier", "source_section", "content_hash",
            "retrieved_at", "review_state", "evidence_status", "notes")}, indent=2))
        print(f"candidate_file: {path}")
    print(f"Candidates matched: {count}")
    return 0


def decide(evidence_id: str, decision: str, reviewer: str, notes: str | None) -> int:
    runtime = load_runtime()
    for path, document, record in candidates():
        if record.get("evidence_id") != evidence_id:
            continue
        verify_source(document)
        now = datetime.now(timezone.utc).isoformat()
        record["reviewer"] = reviewer.strip()
        record["review_mechanism"] = "explicit_cli_review"
        record["reviewed_at"] = now
        record["notes"] = notes
        if decision == "reject":
            record["review_state"] = "REJECTED"
        else:
            record["review_state"] = "REVIEWED"
            record["evidence_status"] = "LIMITED_EVIDENCE" if decision == "partial" else record.get("evidence_status", "SOURCE_SUPPORTED")
        record["content_hash"] = canonical_hash(record)
        validate_record(record, runtime, require_reviewed=decision != "reject")
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{decision.upper()}: {evidence_id}")
        return 0
    raise SystemExit("Evidence candidate not found.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--drug-id")
    listing.add_argument("--topic")
    queue_parser = sub.add_parser("queue")
    queue_parser.add_argument("--status", choices=["SUCCESS", "PARTIAL", "NO_SOURCE", "FAILED", "REQUIRES_REVIEW"])
    draft_parser = sub.add_parser("draft")
    draft_parser.add_argument("--drug-id", required=True)
    draft_parser.add_argument("--source-family", required=True, choices=["DAILYMED", "MOTHERTOBABY"])
    draft_parser.add_argument("--topic", required=True)
    draft_parser.add_argument("--subtopic", required=True)
    draft_parser.add_argument("--claim", required=True)
    draft_parser.add_argument("--source-title", required=True)
    draft_parser.add_argument("--source-section", required=True)
    draft_parser.add_argument("--source-revision-date", default="unknown")
    draft_parser.add_argument("--evidence-id")
    draft_parser.add_argument("--related-drug-id", action="append")
    draft_parser.add_argument("--evidence-status", default="SOURCE_SUPPORTED", choices=["SOURCE_SUPPORTED", "LIMITED_EVIDENCE", "CONFLICTING_EVIDENCE"])
    draft_parser.add_argument("--applicable-population")
    draft_parser.add_argument("--pregnancy-timing")
    draft_parser.add_argument("--lactation-relevance")
    draft_parser.add_argument("--notes")
    for name in ("approve", "partial", "reject"):
        command = sub.add_parser(name)
        command.add_argument("evidence_id")
        command.add_argument("--reviewer", required=True)
        command.add_argument("--notes")
    args = parser.parse_args()
    if args.command == "list":
        return list_candidates(args.drug_id, args.topic)
    if args.command == "queue":
        return list_queue(args.status)
    if args.command == "draft":
        return draft(args)
    return decide(args.evidence_id, args.command, args.reviewer, args.notes)


if __name__ == "__main__":
    raise SystemExit(main())
