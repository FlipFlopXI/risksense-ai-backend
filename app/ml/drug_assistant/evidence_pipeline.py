"""Restartable review workflow and coverage reporting for medication evidence.

This command never marks extracted content REVIEWED.  Reviewers publish an
explicitly reviewed package after checking the source, paraphrase and mapping.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Iterable

from app.ml.drug_assistant.evidence_store import canonical_hash, load_store, validate_record
from app.ml.drug_assistant.runtime import load_runtime
from app.ml.drug_assistant.source_adapters import DailyMedAdapter, MotherToBabyAdapter, SourceRetrievalError

ROOT = Path(__file__).resolve().parent
WORK_ROOT = ROOT / "evidence_work"
QUEUE_PATH = WORK_ROOT / "ingestion_queue_v1.json"
PUBLISHED_PATH = ROOT / "published_evidence_v1.json"
COVERAGE_PATH = ROOT / "evidence_coverage_v1.json"

DOMAIN_TOPICS = {
    "general_information_status": {"identity", "general_information", "indications", "administration", "class"},
    "adverse_effect_status": {"adverse_effects", "serious_adverse_effects"},
    "warnings_status": {"warnings", "precautions", "drug_condition_interactions", "food_alcohol_interactions"},
    "contraindications_status": {"contraindications"},
    "interaction_status": {"drug_interactions"},
    "monitoring_status": {"monitoring"},
    "pregnancy_status": {"pregnancy", "pregnancy_exposure", "pregnancy_timing"},
    "lactation_status": {"lactation"},
    "reproductive_potential_status": {"reproductive_potential", "fertility", "contraception", "pregnancy_testing"},
}


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1 * (attempt + 1))


def bootstrap_queue(path: Path = QUEUE_PATH) -> dict:
    """Create missing operations while retaining prior per-source progress."""
    runtime = load_runtime()
    current = _read(path, {"schema_version": "1.0.0", "operations": []})
    indexed = {(item["drug_id"], item["source_family"]): item for item in current.get("operations", [])}
    operations = []
    for drug_id, record in sorted(runtime.drugs.items()):
        for family in ("DAILYMED", "MOTHERTOBABY"):
            key = (drug_id, family)
            operations.append(indexed.get(key, {
                "drug_id": drug_id,
                "canonical_name": record["generic_name"],
                "source_family": family,
                "status": "REQUIRES_REVIEW",
                "source_identifier": None,
                "source_url": None,
                "retrieved_at": None,
                "source_revision_date": None,
                "source_content_hash": None,
                "error_code": None,
            }))
    document = {"schema_version": "1.0.0", "catalogue_version": "1.0.0", "operations": operations}
    _write(path, document)
    return document


def validate_review_package(input_path: Path, *, queue_path: Path = QUEUE_PATH,
                            snapshot_root: Path | None = None) -> dict:
    from app.ml.drug_assistant.evidence_normalization import verify_source
    runtime = load_runtime()
    package = _read(input_path, None)
    if not isinstance(package, dict) or package.get("schema_version") != "1.0.0" or not isinstance(package.get("records"), list):
        raise ValueError("Invalid review package")
    verify_source(package, snapshot_root or (WORK_ROOT / "snapshots"))
    operation = package["provenance"]["operation"]
    current = _read(queue_path, {"operations": []})
    matching = next((item for item in current["operations"]
                     if item["drug_id"] == operation["drug_id"]
                     and item["source_family"] == operation["source_family"]), None)
    if (matching is None or matching.get("source_identifier") != operation["source_identifier"]
            or matching.get("source_content_hash") != operation["source_content_hash"]
            or matching.get("source_url") != operation["source_url"]):
        raise ValueError("Source operation has changed since review")
    for item in package["records"]:
        validate_record(item, runtime)
        if item["content_hash"].lower() != canonical_hash(item):
            raise ValueError(f"Content hash mismatch for {item.get('evidence_id', 'unknown')}")
    return package


def retrieve_dailymed(limit: int, queue_path: Path = QUEUE_PATH, snapshot_root: Path | None = None,
                      adapter: DailyMedAdapter | None = None) -> dict:
    """Retrieve unresolved DailyMed SPLs into review storage; never approve them."""
    queue = bootstrap_queue(queue_path)
    snapshot_root = snapshot_root or (WORK_ROOT / "snapshots")
    adapter = adapter or DailyMedAdapter()
    processed = 0
    for operation in queue["operations"]:
        if processed >= limit:
            break
        if operation["source_family"] != "DAILYMED" or operation["status"] in {"SUCCESS", "PARTIAL", "NO_SOURCE"}:
            continue
        processed += 1
        try:
            candidates = adapter.locate(operation["canonical_name"])
            if not candidates:
                operation.update(status="NO_SOURCE", error_code=None)
                continue
            # Multiple labels require human product selection. Preserve the list
            # rather than guessing which formulation applies.
            if len(candidates) != 1:
                operation.update(status="PARTIAL", error_code="MULTIPLE_LABELS_REQUIRE_REVIEW")
                operation["candidates"] = list(candidates)
                continue
            snapshot = adapter.retrieve(candidates[0]["set_id"])
            target = snapshot_root / operation["drug_id"] / f"{snapshot.source_identifier}.xml"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(snapshot.content)
            operation.update(
                status="SUCCESS", source_identifier=snapshot.source_identifier,
                source_url=snapshot.source_url, source_revision_date=snapshot.source_revision_date,
                source_content_hash=snapshot.content_hash,
                retrieved_at=datetime.now(timezone.utc).isoformat(), error_code=None,
            )
        except SourceRetrievalError:
            operation.update(status="FAILED", error_code="SOURCE_RETRIEVAL_FAILED")
        finally:
            _write(queue_path, queue)
    return queue


def retrieve_mothertobaby(limit: int, queue_path: Path = QUEUE_PATH, snapshot_root: Path | None = None,
                          adapter: MotherToBabyAdapter | None = None) -> dict:
    queue = bootstrap_queue(queue_path)
    snapshot_root = snapshot_root or (WORK_ROOT / "snapshots")
    adapter = adapter or MotherToBabyAdapter()
    processed = 0
    for operation in queue["operations"]:
        if processed >= limit:
            break
        if operation["source_family"] != "MOTHERTOBABY" or operation["status"] in {"SUCCESS", "PARTIAL", "NO_SOURCE"}:
            continue
        processed += 1
        try:
            candidates = adapter.locate(operation["canonical_name"])
            if not candidates:
                operation.update(status="NO_SOURCE", error_code=None)
                continue
            if len(candidates) != 1:
                operation.update(status="PARTIAL", error_code="MULTIPLE_FACT_SHEETS_REQUIRE_REVIEW", candidates=list(candidates))
                continue
            snapshot = adapter.retrieve(candidates[0]["url"])
            target = snapshot_root / operation["drug_id"] / "mothertobaby.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(snapshot.content)
            operation.update(status="SUCCESS", source_identifier=snapshot.source_identifier,
                             source_url=snapshot.source_url, source_revision_date=snapshot.source_revision_date,
                             source_content_hash=snapshot.content_hash,
                             retrieved_at=datetime.now(timezone.utc).isoformat(), error_code=None)
        except SourceRetrievalError:
            operation.update(status="FAILED", error_code="SOURCE_RETRIEVAL_FAILED")
        finally:
            _write(queue_path, queue)
    return queue


def publish(review_packages: Iterable[Path], output_path: Path = PUBLISHED_PATH,
            *, queue_path: Path = QUEUE_PATH, snapshot_root: Path | None = None) -> dict:
    """Publish only explicitly REVIEWED records, replacing by evidence_id."""
    runtime = load_runtime()
    existing = _read(output_path, {"records": []})
    merged = {item["evidence_id"]: item for item in existing.get("records", [])}
    for path in review_packages:
        package = validate_review_package(path, queue_path=queue_path, snapshot_root=snapshot_root)
        for item in package["records"]:
            validate_record(item, runtime, require_reviewed=True)
            merged[item["evidence_id"]] = item
    document = {
        "schema_version": "1.0.0", "catalogue_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": sorted(merged.values(), key=lambda item: (item["drug_id"], item["topic"], item["evidence_id"])),
    }
    _write(output_path, document)
    load_store(output_path, runtime)
    return document


def _domain_status(records: list[dict], topics: set[str]) -> str:
    selected = [item for item in records if item["topic"] in topics]
    if not selected:
        return "INSUFFICIENT_EVIDENCE"
    present = {item["topic"] for item in selected}
    return "REVIEWED" if topics <= present else "PARTIAL"


def generate_coverage(output_path: Path = COVERAGE_PATH, store_path: Path = PUBLISHED_PATH) -> dict:
    runtime = load_runtime()
    store = load_store(store_path, runtime)
    by_drug: dict[str, list[dict]] = {drug_id: [] for drug_id in runtime.drugs}
    for frozen in store.records:
        by_drug[frozen["drug_id"]].append(dict(frozen))
    rows = []
    for drug_id, catalogue in sorted(runtime.drugs.items()):
        records = by_drug[drug_id]
        statuses = {key: _domain_status(records, topics) for key, topics in DOMAIN_TOPICS.items()}
        reviewed_domains = sum(value == "REVIEWED" for value in statuses.values())
        available_domains = sum(value != "INSUFFICIENT_EVIDENCE" for value in statuses.values())
        overall = ("COMPLETE" if reviewed_domains == len(statuses) else
                   "SUBSTANTIAL" if available_domains >= 7 else
                   "PARTIAL" if available_domains >= 4 else
                   "MINIMAL" if available_domains else "INSUFFICIENT")
        sources = {item["source_url"] for item in records}
        updates = [item["source_revision_date"] for item in records]
        rows.append({
            "drug_id": drug_id, "canonical_name": catalogue["generic_name"],
            "therapeutic_group": catalogue["therapeutic_group"], "aliases_count": len(catalogue["aliases"]),
            **statuses, "source_count": len(sources), "reviewed_source_count": len(sources),
            "last_evidence_update": max(updates) if updates else None,
            "overall_coverage_status": overall,
        })
    document = {
        "schema_version": "1.0.0", "catalogue_medications": len(runtime.drugs),
        "processed_medications": len(rows), "generated_from_store_sha256": store.digest,
        "generated_at": datetime.now(timezone.utc).isoformat(), "records": rows,
    }
    _write(output_path, document)
    return document


def coverage_report(coverage: dict) -> str:
    rows = coverage["records"]
    lines = ["RiskSense Drug Knowledge Coverage", "=" * 33, "",
             f"Catalogue medications:       {coverage['catalogue_medications']}",
             f"Processed medications:       {coverage['processed_medications']}", ""]
    labels = {
        "general_information_status": "General information", "pregnancy_status": "Pregnancy evidence",
        "lactation_status": "Lactation evidence", "interaction_status": "Interaction evidence",
        "warnings_status": "Warnings evidence", "monitoring_status": "Monitoring evidence",
    }
    for key, label in labels.items():
        count = sum(row[key] in {"REVIEWED", "PARTIAL"} for row in rows)
        lines.append(f"{label + ':':28}{count} / {len(rows)}")
    totals = Counter(row["overall_coverage_status"] for row in rows)
    lines.extend(["", f"Fully reviewed:              {totals['COMPLETE']}",
                  f"Partially reviewed:          {sum(totals[key] for key in ('SUBSTANTIAL', 'PARTIAL', 'MINIMAL'))}",
                  f"Insufficient evidence:       {totals['INSUFFICIENT']}"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="Create/resume the 208-medication source queue")
    retrieve_parser = sub.add_parser("retrieve-dailymed", help="Retrieve DailyMed SPLs into the review workspace")
    retrieve_parser.add_argument("--limit", type=int, default=10)
    mother_parser = sub.add_parser("retrieve-mothertobaby", help="Retrieve MotherToBaby fact sheets into the review workspace")
    mother_parser.add_argument("--limit", type=int, default=208)
    publish_parser = sub.add_parser("publish", help="Validate and publish reviewed packages")
    publish_parser.add_argument("packages", nargs="+", type=Path)
    sub.add_parser("coverage", help="Regenerate matrix and print honest coverage")
    args = parser.parse_args()
    if args.command == "bootstrap":
        result = bootstrap_queue()
        print(f"Evidence operations: {len(result['operations'])}")
    elif args.command == "retrieve-dailymed":
        result = retrieve_dailymed(max(1, args.limit))
        print(f"DailyMed successful snapshots: {sum(item['status'] == 'SUCCESS' for item in result['operations'])}")
    elif args.command == "retrieve-mothertobaby":
        result = retrieve_mothertobaby(max(1, args.limit))
        print(f"MotherToBaby successful snapshots: {sum(item['status'] == 'SUCCESS' for item in result['operations'])}")
    elif args.command == "publish":
        result = publish(args.packages)
        print(f"Published reviewed records: {len(result['records'])}")
    else:
        print(coverage_report(generate_coverage()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
