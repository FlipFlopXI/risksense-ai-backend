"""Read-only queue inspection and explicit one-record-at-a-time clinical review."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

from app.ml.drug_assistant.evidence_normalization import (
    CANDIDATES, SNAPSHOTS, normalize_operation, verify_source,
)
from app.ml.drug_assistant.evidence_pipeline import QUEUE_PATH
from app.ml.drug_assistant.evidence_pipeline import WORK_ROOT, validate_review_package
from app.ml.drug_assistant.evidence_store import canonical_hash, validate_record
from app.ml.drug_assistant.runtime import load_runtime
from app.ml.drug_assistant.source_adapters import DailyMedAdapter


def packages():
    for path in sorted(CANDIDATES.glob("*.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        if len(package.get("records", [])) == 1:
            yield path, package, package["records"][0]


def _manifest_ids(path: str | None) -> set[str] | None:
    if not path:
        return None
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = document.get("candidate_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids):
        raise SystemExit("Review manifest must contain a non-empty candidate_ids list.")
    if len(ids) != len(set(ids)):
        raise SystemExit("Review manifest contains duplicate candidate IDs.")
    return set(ids)


def _matches(record: dict, package: dict, args) -> bool:
    if getattr(args, "candidate_ids", None) is not None and record["evidence_id"] not in args.candidate_ids:
        return False
    if args.drug and record["drug_id"] != args.drug:
        return False
    if args.topic and record["topic"] != args.topic:
        return False
    if args.source and record["source_organisation"].casefold() != args.source.casefold():
        return False
    if args.group and package["provenance"]["therapeutic_group"] != args.group:
        return False
    if args.pending and record["review_state"] != "REVIEW_REQUIRED":
        return False
    if args.reviewed and record["review_state"] != "REVIEWED":
        return False
    if args.conflicts and record["evidence_status"] != "CONFLICTING_EVIDENCE":
        return False
    return True


def summary() -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))["operations"]
    rows = [record for _, _, record in packages()]
    print(f"Catalogue: {len(load_runtime().drugs)}")
    print(f"Retrieval: {dict(Counter(item['status'] for item in queue))}")
    print(f"Candidates: {len(rows)} across {len({r['drug_id'] for r in rows})} medications")
    print(f"Review: {dict(Counter(r['review_state'] for r in rows))}")
    print(f"Topics: {dict(Counter(r['topic'] for r in rows))}")
    print(f"Sources: {dict(Counter(r['source_organisation'] for r in rows))}")
    print(f"Ambiguous DailyMed products: {sum(r['source_family'] == 'DAILYMED' and r['status'] == 'PARTIAL' for r in queue)}")


def _show(record: dict, package: dict, *, full: bool = True) -> None:
    provenance = package["provenance"]
    print(f"\nMedication: {provenance['canonical_name']} ({record['drug_id']})")
    print(f"Group: {provenance['therapeutic_group']} | Topic: {record['topic']} / {record['subtopic']}")
    print(f"Source: {record['source_organisation']} — {record['source_title']}")
    print(f"Section: {record['source_section']}")
    print(f"URL: {record['source_url']}")
    print(f"Product/source ID: {record['source_identifier']}")
    print(f"Retrieved: {record['retrieved_at']} | Version: {provenance['source_version']}")
    print(f"Evidence ID: {record['evidence_id']} | State: {record['review_state']}")
    try:
        verify_source(package)
        print(f"Snapshot SHA-256: VERIFIED {provenance['source_content_hash']}")
    except (ValueError, OSError):
        print("Snapshot SHA-256: INVALID OR MISSING")
    if full:
        print("\nSOURCE CONTEXT:\n" + provenance["source_excerpt"])
        print("\nPROPOSED EXTRACTIVE CLAIM:\n" + record["claim"])


def record_decision(record: dict, *, reviewer: str, decision: str,
                    claim: str | None = None, notes: str | None = None) -> dict:
    if record["review_state"] != "REVIEW_REQUIRED":
        raise ValueError("Only pending records can be decided")
    if not reviewer.strip() or decision not in {"approve", "partial", "reject"}:
        raise ValueError("Named reviewer and explicit decision required")
    updated = dict(record)
    if claim is not None:
        updated["claim"] = claim.strip()
    updated["reviewer"] = reviewer.strip()
    updated["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    updated["notes"] = notes
    updated["review_state"] = "REJECTED" if decision == "reject" else "REVIEWED"
    updated["evidence_status"] = (
        "SOURCE_SUPPORTED" if decision == "approve" else
        "LIMITED_EVIDENCE" if decision == "partial" else updated["evidence_status"])
    updated["content_hash"] = canonical_hash(updated)
    validate_record(updated, load_runtime(), require_reviewed=decision != "reject")
    return updated


def review(args) -> None:
    reviewer = (args.reviewer or "").strip()
    if not reviewer:
        raise SystemExit("A named reviewer is required for review decisions.")
    selected = [(path, package, record) for path, package, record in packages()
                if _matches(record, package, args)]
    if not selected:
        print("No matching candidates.")
        return
    for path, package, record in selected:
        _show(record, package)
        while True:
            choice = input("\n[A]pprove [P]artial [R]eject [S]kip [V]iew provenance [N]ext: ").strip().lower()
            if choice in {"s", "n"}:
                break
            if choice == "v":
                _show(record, package)
                continue
            if choice not in {"a", "p", "r"}:
                print("Choose A, P, R, S, V or N.")
                continue
            verify_source(package)
            if record["review_state"] != "REVIEW_REQUIRED":
                print("Only pending records can be newly decided here.")
                break
            if choice != "r":
                edited = input("Verified claim (Enter retains the displayed extract): ").strip()
                if edited:
                    record["claim"] = edited
                if len(record["claim"]) > 1600:
                    print("Claim exceeds 1600 characters; revise it.")
                    continue
            notes = input("Review notes (optional): ").strip() or None
            decision = {"a": "APPROVE", "p": "PARTIAL", "r": "REJECT"}[choice]
            confirm = input(f"Type {decision} for evidence ID {record['evidence_id']}: ").strip()
            if confirm != decision:
                print("Decision not recorded.")
                break
            record = record_decision(
                record, reviewer=reviewer,
                decision={"a": "approve", "p": "partial", "r": "reject"}[choice],
                claim=record["claim"], notes=notes)
            package["records"][0] = record
            verify_source(package)
            path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Recorded {decision}; publication remains a separate command.")
            break


def select_product(args) -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    operation = next((item for item in queue["operations"]
                      if item["drug_id"] == args.drug and item["source_family"] == "DAILYMED"), None)
    if operation is None or operation["status"] != "PARTIAL":
        raise SystemExit("This medication has no ambiguous DailyMed selection.")
    candidates = operation.get("candidates", [])
    canonical = operation["canonical_name"].casefold()

    def label_hint(item):
        title = item["title"].casefold()
        if not re.search(r"(?<!\w)" + re.escape(canonical) + r"(?!\w)", title):
            return "NAME MISMATCH — exclude until identity is resolved"
        if any(word in title for word in ("veterinary", "animal use", "for dogs", "for cats")):
            return "NON-HUMAN LABEL — exclude"
        if (" and " in title or " / " in title) and not (
                " and " in canonical or "/" in canonical):
            return "COMBINATION MISMATCH — exclude"
        return "NAME MATCH — verify route, formulation and current human prescription status"

    print(f"{args.drug}: {len(candidates)} DailyMed labels. The catalogue has no route/form for automatic selection.")
    for item in sorted(candidates, key=lambda item: (label_hint(item), item["title"], item["set_id"])):
        print(f"  {item['set_id']}  {item['title']} [{label_hint(item)}]")
    if not args.set_id:
        return
    selected = next((item for item in candidates if item["set_id"] == args.set_id), None)
    if selected is None:
        raise SystemExit("SET ID is not one of the recorded candidate products.")
    if label_hint(selected).startswith(("NAME MISMATCH", "NON-HUMAN LABEL",
                                       "COMBINATION MISMATCH")):
        raise SystemExit("The selected product is not a supported human catalogue match.")
    if not args.reason or not args.reason.strip():
        raise SystemExit("A product-selection reason is required.")
    if input(f"Type SELECT {args.set_id} to retrieve this exact label: ").strip() != f"SELECT {args.set_id}":
        raise SystemExit("Selection not confirmed.")
    snapshot = DailyMedAdapter().retrieve(args.set_id)
    target = SNAPSHOTS / args.drug / f"{args.set_id}.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(snapshot.content)
    if sha256(target.read_bytes()).hexdigest() != snapshot.content_hash:
        raise SystemExit("Downloaded snapshot hash mismatch.")
    operation.update(
        status="SUCCESS", source_identifier=snapshot.source_identifier,
        source_url=snapshot.source_url, source_revision_date=snapshot.source_revision_date,
        source_content_hash=snapshot.content_hash,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        error_code=None, product_selection_reason=args.reason.strip(),
        product_selection_reviewer=args.reviewer.strip(),
        selected_product_title=selected["title"],
    )
    QUEUE_PATH.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    count = normalize_operation(operation)
    print(f"Selected {args.set_id}; {count} source sections mapped to review candidates.")


def batch_plan(candidate_root: Path = CANDIDATES, queue_path: Path = QUEUE_PATH,
               snapshot_root: Path = SNAPSHOTS, candidate_ids: set[str] | None = None) -> dict:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    operations = {(item["drug_id"], item["source_family"]): item
                  for item in queue["operations"]}
    report = {
        "total_candidate_records": 0, "pending_records": 0,
        "already_reviewed": 0, "rejected_unchanged": 0,
        "partial_reviewed": 0, "eligible": [], "skipped_invalid": [],
        "skipped_ambiguous": [], "failed": [],
        "medications": set(), "sources": Counter(), "topics": Counter(),
    }
    found_ids = set()
    for path in sorted(candidate_root.glob("*.json")):
        try:
            package = json.loads(path.read_text(encoding="utf-8"))
            records = package.get("records")
            if not isinstance(records, list) or len(records) != 1:
                raise ValueError("Candidate package must contain exactly one record")
            record = records[0]
            if candidate_ids is not None and record["evidence_id"] not in candidate_ids:
                continue
            found_ids.add(record["evidence_id"])
            report["total_candidate_records"] += 1
            report["medications"].add(record["drug_id"])
            report["sources"][record["source_organisation"]] += 1
            report["topics"][record["topic"]] += 1
            state = record["review_state"]
            if state == "REVIEWED":
                report["already_reviewed"] += 1
                if record["evidence_status"] == "LIMITED_EVIDENCE":
                    report["partial_reviewed"] += 1
                continue
            if state == "REJECTED":
                report["rejected_unchanged"] += 1
                continue
            if state != "REVIEW_REQUIRED":
                report["skipped_invalid"].append((path, "Unexpected review state"))
                continue
            report["pending_records"] += 1
            try:
                validate_review_package(
                    path, queue_path=queue_path, snapshot_root=snapshot_root)
                operation = package["provenance"]["operation"]
                current = operations.get(
                    (operation["drug_id"], operation["source_family"]))
                if current is None or current["status"] != "SUCCESS":
                    raise ValueError("Source product or retrieval is unresolved")
                report["eligible"].append(path)
            except (ValueError, OSError, KeyError) as exc:
                operation = package.get("provenance", {}).get("operation", {})
                current = operations.get(
                    (operation.get("drug_id"), operation.get("source_family")))
                destination = (
                    report["skipped_ambiguous"]
                    if operation.get("source_family") == "DAILYMED"
                    and current is not None and current.get("status") == "PARTIAL"
                    else report["skipped_invalid"]
                )
                destination.append((path, str(exc)))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report["failed"].append((path, type(exc).__name__))
    if candidate_ids is not None and found_ids != candidate_ids:
        raise ValueError(f"Review manifest contains {len(candidate_ids - found_ids)} missing candidate IDs")
    return report


def _print_batch_plan(plan: dict, *, dry_run: bool) -> None:
    print("EXTERNALLY REVIEWED BATCH ATTESTATION" + (" — DRY RUN" if dry_run else ""))
    print(f"Total candidate records: {plan['total_candidate_records']}")
    print(f"Pending records: {plan['pending_records']}")
    print(f"Already reviewed: {plan['already_reviewed']}")
    print(f"Rejected: {plan['rejected_unchanged']}")
    print(f"Partial reviewed: {plan['partial_reviewed']}")
    print(f"Medications affected: {len(plan['medications'])}")
    print(f"Sources affected: {len(plan['sources'])}")
    print(f"Topics affected: {len(plan['topics'])}")
    print("By source organisation: " + json.dumps(dict(sorted(plan["sources"].items()))))
    print("By evidence topic: " + json.dumps(dict(sorted(plan["topics"].items()))))
    print(f"Eligible for approval: {len(plan['eligible'])}")
    print(f"SKIPPED_INVALID: {len(plan['skipped_invalid'])}")
    print(f"SKIPPED_AMBIGUOUS: {len(plan['skipped_ambiguous'])}")
    print(f"ALREADY_REVIEWED: {plan['already_reviewed']}")
    print(f"REJECTED_UNCHANGED: {plan['rejected_unchanged']}")
    print(f"FAILED: {len(plan['failed'])}")
    for category in ("skipped_invalid", "skipped_ambiguous", "failed"):
        for path, reason in plan[category]:
            print(f"{category.upper()}: {path.name}: {reason}")
    print("This action records an external human review decision for all eligible pending evidence records in the displayed scope.")


def _backup_candidates(candidate_root: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_root / f"candidate-review-state-{timestamp}.zip"
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }
    with ZipFile(backup_path, "x", compression=ZIP_DEFLATED) as archive:
        for path in sorted(candidate_root.glob("*.json")):
            content = path.read_bytes()
            archive.writestr(path.name, content)
            manifest["files"][path.name] = sha256(content).hexdigest()
        archive.writestr("review-backup-manifest.json", json.dumps(manifest, indent=2))
    return backup_path


def batch_attest(args, *, candidate_root: Path = CANDIDATES,
                 queue_path: Path = QUEUE_PATH, snapshot_root: Path = SNAPSHOTS,
                 backup_root: Path | None = None) -> dict:
    if not args.attest_reviewed:
        raise SystemExit("--attest-reviewed is required; no candidate changed.")
    reviewer = (args.reviewer or "").strip()
    if not reviewer:
        raise SystemExit("--reviewer with a human name is required.")
    plan = batch_plan(candidate_root, queue_path, snapshot_root,
                      getattr(args, "candidate_ids", None))
    _print_batch_plan(plan, dry_run=args.dry_run)
    outcome = {
        "APPROVED": 0,
        "SKIPPED_INVALID": len(plan["skipped_invalid"]),
        "SKIPPED_AMBIGUOUS": len(plan["skipped_ambiguous"]),
        "ALREADY_REVIEWED": plan["already_reviewed"],
        "REJECTED_UNCHANGED": plan["rejected_unchanged"],
        "FAILED": len(plan["failed"]),
    }
    if args.dry_run:
        print("Dry run: no backup or candidate file was changed.")
        return outcome
    expected = f"APPROVE {plan['pending_records']} REVIEWED RECORDS"
    confirmation = input(f"Type {expected} to record this external review decision: ").strip()
    if confirmation != expected:
        raise SystemExit("Confirmation did not match the current pending count; no candidate changed.")
    if not plan["eligible"]:
        print("No eligible pending candidates.")
        return outcome
    backup = _backup_candidates(
        candidate_root, backup_root or (WORK_ROOT / "backups"))
    print(f"Candidate review-state backup: {backup}")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    for path in plan["eligible"]:
        try:
            package = validate_review_package(
                path, queue_path=queue_path, snapshot_root=snapshot_root)
            record = package["records"][0]
            if record["review_state"] != "REVIEW_REQUIRED":
                outcome["SKIPPED_INVALID"] += 1
                continue
            old_hash = record["content_hash"]
            record.update(
                review_state="REVIEWED", reviewer=reviewer,
                reviewed_at=reviewed_at,
                review_mechanism="EXTERNAL_HUMAN_REVIEW_BATCH",
            )
            if record["content_hash"] != old_hash or canonical_hash(record) != old_hash:
                raise ValueError("Clinical content hash changed")
            validate_record(record, load_runtime(), require_reviewed=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(package, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
            os.replace(temporary, path)
            outcome["APPROVED"] += 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            outcome["FAILED"] += 1
            print(f"FAILED: {path.name}: {type(exc).__name__}")
    print("Batch outcome: " + json.dumps(outcome, sort_keys=True))
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--drug")
    parser.add_argument("--topic")
    parser.add_argument("--source")
    parser.add_argument("--group")
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--conflicts", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--select-product", action="store_true")
    parser.add_argument("--set-id")
    parser.add_argument("--reason")
    parser.add_argument("--approve-all-pending", action="store_true")
    parser.add_argument("--attest-reviewed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", help="Scope review or attestation to exact candidate_ids in a JSON manifest")
    args = parser.parse_args()
    args.candidate_ids = _manifest_ids(args.manifest)
    if args.approve_all_pending:
        batch_attest(args)
    elif args.select_product:
        if not args.drug or not args.reviewer:
            parser.error("--select-product requires --drug and --reviewer")
        select_product(args)
    elif args.summary:
        summary()
    elif args.interactive:
        review(args)
    else:
        selected = [(package, record) for _, package, record in packages()
                    if _matches(record, package, args)]
        for package, record in selected:
            _show(record, package, full=False)
        print(f"Candidates matched: {len(selected)}")


if __name__ == "__main__":
    main()
