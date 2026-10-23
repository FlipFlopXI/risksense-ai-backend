"""Create a scoped external-review dossier for currently pending evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from app.ml.drug_assistant.evidence_normalization import CANDIDATES
from app.ml.drug_assistant.evidence_pipeline import validate_review_package

REPORT = Path("DRUG_ASSISTANT_NEW_EVIDENCE_REVIEW.md")
MANIFEST = Path("app/ml/drug_assistant/evidence_work/expansion_review_manifest_v1.json")


def generate(candidate_root: Path = CANDIDATES,
             report_path: Path = REPORT, manifest_path: Path = MANIFEST) -> dict:
    pending = []
    for path in sorted(candidate_root.glob("*.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        if len(package.get("records", [])) != 1:
            raise ValueError(f"Invalid candidate package: {path.name}")
        record = package["records"][0]
        if record["review_state"] == "REVIEW_REQUIRED":
            validate_review_package(path)
            pending.append((record, package["provenance"]))
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {"schema_version": "1.0.0", "generated_at": generated_at,
                "candidate_ids": sorted(record["evidence_id"] for record, _ in pending)}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    by_topic = Counter(record["topic"] for record, _ in pending)
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for record, provenance in pending:
        grouped[record["drug_id"]][record["topic"]][record["source_section"]].append((record, provenance))
    lines = ["# New Drug Assistant evidence: external review dossier", "",
             f"Generated: {generated_at}", "",
             f"Pending candidates in this exact manifest: **{len(pending)}** across **{len(grouped)}** medications.",
             "All records below remain REVIEW_REQUIRED and are not runtime evidence.",
             "Review the original source, product identity, section mapping, claim accuracy, and applicability before attestation.",
             "", "## New candidates by domain", ""]
    for topic, count in sorted(by_topic.items()):
        lines.append(f"- {topic}: {count}")
    lines.extend(["", "## Review records", ""])
    for drug_id in sorted(grouped):
        lines.extend([f"### {drug_id}", ""])
        for topic in sorted(grouped[drug_id]):
            lines.extend([f"#### {topic}", ""])
            for section in sorted(grouped[drug_id][topic]):
                lines.extend([f"**Source section: {section}**", ""])
                for record, provenance in grouped[drug_id][topic][section]:
                    lines.extend([
                        f"- Evidence ID: `{record['evidence_id']}`",
                        f"- Proposed claim: {record['claim']}",
                        f"- Exact supporting excerpt: {provenance['source_excerpt']}",
                        f"- Source: {record['source_organisation']} — {record['source_title']}",
                        f"- URL: {record['source_url']}",
                        f"- Revision: {record['source_revision_date']}; SET/source ID: {record['source_identifier']}",
                        f"- Snapshot SHA-256: `{provenance['source_content_hash']}` — VERIFIED against local source and operation",
                        "",
                    ])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"pending": len(pending), "medications": len(grouped),
            "by_topic": dict(by_topic), "report": str(report_path), "manifest": str(manifest_path)}


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
