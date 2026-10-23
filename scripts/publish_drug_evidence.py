"""Publish explicitly reviewed candidates, then regenerate runtime coverage."""
from __future__ import annotations

import argparse
import json

from app.ml.drug_assistant.evidence_normalization import CANDIDATES
from app.ml.drug_assistant.evidence_pipeline import generate_coverage, publish, validate_review_package
from app.ml.drug_assistant.evidence_store import validate_record
from app.ml.drug_assistant.runtime import load_runtime


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--drug", help="Publish reviewed candidates for one medication")
    scope.add_argument("--all-reviewed", action="store_true", help="Publish every eligible reviewed candidate")
    args = parser.parse_args()
    approved = []
    rejected = []
    runtime = load_runtime()
    for path in sorted(CANDIDATES.glob("*.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        records = package.get("records", [])
        if len(records) != 1:
            raise SystemExit(f"Invalid candidate package: {path}")
        record = records[0]
        if args.drug and record["drug_id"] != args.drug:
            continue
        if record["review_state"] == "REVIEWED":
            try:
                validated = validate_review_package(path)
                for item in validated["records"]:
                    validate_record(item, runtime, require_reviewed=True)
            except (ValueError, KeyError, TypeError) as exc:
                rejected.append((path.name, str(exc)))
            else:
                approved.append(path)
    for name, reason in rejected:
        print(f"Rejected at publication: {name}: {reason}")
    print(f"Eligible reviewed candidates: {len(approved)}; rejected at publication: {len(rejected)}")
    if not approved:
        print("No explicitly reviewed candidates matched; nothing published.")
        return
    store = publish(approved)
    coverage = generate_coverage()
    print(f"Published reviewed records: {len(store['records'])}")
    print(f"Medications in coverage matrix: {len(coverage['records'])}")


if __name__ == "__main__":
    main()
