"""Extractive review candidates from already retrieved authoritative snapshots.

These candidates are proposals, never runtime evidence. No clinical inference,
product selection, or review decision is made by this module.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from app.ml.drug_assistant.evidence_pipeline import QUEUE_PATH, WORK_ROOT
from app.ml.drug_assistant.evidence_store import canonical_hash, validate_record, load_published_store
from app.ml.drug_assistant.runtime import load_runtime

CANDIDATES = WORK_ROOT / "candidates"
SNAPSHOTS = WORK_ROOT / "snapshots"
NORMALIZATION_REPORT = WORK_ROOT / "normalization_report_v1.json"

SPL_TOPICS = {
    "34089-3": ("general_information", "description"),
    "43679-0": ("general_information", "mechanism_of_action"),
    "34067-9": ("indications", "indications_and_usage"),
    "34068-7": ("administration", "dosage_and_administration"),
    "43678-2": ("administration", "dosage_forms_and_strengths"),
    "34070-3": ("contraindications", "contraindications"),
    "43685-7": ("warnings", "warnings_and_precautions"),
    "34071-1": ("warnings", "warnings"),
    "34084-4": ("adverse_effects", "adverse_reactions"),
    "34073-7": ("drug_interactions", "drug_interactions"),
    "34076-0": ("clinician_discussion", "patient_counseling_information"),
    "42228-7": ("pregnancy", "pllr_8_1"),
    "77290-5": ("lactation", "pllr_8_2"),
    "77291-3": ("reproductive_potential", "pllr_8_3"),
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


class _FactSheet(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.capture: str | None = None
        self.text: list[str] = []
        self.heading = ""
        self.sections: list[tuple[str, str]] = []
        self.title = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div" and "entry-content" in attributes.get("class", "").split():
            self.depth = 1
            return
        if self.depth:
            if tag == "div":
                self.depth += 1
            if tag in {"h2", "p"} and self.capture is None:
                self.capture, self.text = tag, []
        if tag == "h1" and "entry-title" in attributes.get("class", "").split():
            self.capture, self.text = "title", []

    def handle_data(self, data):
        if self.capture:
            self.text.append(data)

    def handle_endtag(self, tag):
        if self.capture == tag or (self.capture == "title" and tag == "h1"):
            value = _clean("".join(self.text))
            if self.capture == "title":
                self.title = value
            elif tag == "h2":
                self.heading = value
            elif self.heading and value:
                self.sections.append((self.heading, value))
            self.capture, self.text = None, []
        if self.depth and tag == "div":
            self.depth -= 1


def _mother_topic(question: str) -> tuple[str, str] | None:
    q = question.casefold()
    if "what is " in q:
        return "general_information", "identity_and_uses"
    if "breastfeed" in q or "breast milk" in q:
        return "lactation", "breastfeeding"
    if "fertility" in q or "harder for me to get pregnant" in q:
        return "fertility", "fertility"
    if "miscarriage" in q:
        return "pregnancy", "miscarriage"
    if "birth defects" in q:
        return "pregnancy", "birth_defects"
    if "pregnancy" in q or "pregnant" in q:
        return "pregnancy", "pregnancy_outcomes"
    return None


def mother_sections(content: bytes, canonical_name: str) -> tuple[str, list[tuple[str, str, str, str]]]:
    parser = _FactSheet()
    parser.feed(content.decode("utf-8", errors="replace"))
    if canonical_name.casefold() not in parser.title.casefold():
        raise ValueError("Fact-sheet title does not match catalogue medication")
    result = []
    for question, excerpt in parser.sections:
        mapped = _mother_topic(question)
        if mapped and excerpt and canonical_name.casefold() in excerpt.casefold():
            result.append((*mapped, question, excerpt))
    return parser.title, result


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def daily_med_sections(content: bytes) -> tuple[str, str, list[tuple[str, str, str, str]]]:
    root = ET.fromstring(content)
    title = next((_clean(" ".join(e.itertext())) for e in root if _tag(e) == "title"), "")
    version = next((e.get("value", "") for e in root if _tag(e) == "versionNumber"), "")
    result = []
    for section in root.iter():
        if _tag(section) != "section":
            continue
        code = next((e.get("code") for e in section if _tag(e) == "code"), None)
        mapped = SPL_TOPICS.get(code)
        if not mapped:
            continue
        label = next((_clean(" ".join(e.itertext())) for e in section if _tag(e) == "title"), "")
        # SPL top-level sections often hold the clinical text in nested
        # subsections. Preserve the top-level source section as the citation.
        text = " ".join(_clean(" ".join(e.itertext()))
                        for e in section.iter() if _tag(e) == "text")
        text = _clean(text)
        if text:
            result.append((*mapped, label or code, text))
        # Propose monitoring candidates only when the source explicitly uses
        # monitoring language. These remain unreviewed and cannot reach runtime.
        if code in {"43685-7", "34071-1", "34073-7", "34068-7"}:
            for node in section.iter():
                if _tag(node) != "text":
                    continue
                for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", _clean(" ".join(node.itertext()))):
                    if re.search(r"\bmonitor(?:ing)?\b", sentence, re.I) and 30 <= len(sentence) <= 5000:
                        result.append(("monitoring", "explicit_monitoring", label or code, sentence))
    return title, version, result


def _snapshot(operation: dict, snapshot_root: Path) -> Path:
    if operation["source_family"] == "MOTHERTOBABY":
        return snapshot_root / operation["drug_id"] / "mothertobaby.html"
    set_id = operation.get("source_identifier")
    if not set_id or not re.fullmatch(r"[a-fA-F0-9-]+", set_id):
        raise ValueError("Missing or invalid DailyMed SET ID")
    return snapshot_root / operation["drug_id"] / f"{set_id}.xml"


def verify_source(package: dict, snapshot_root: Path = SNAPSHOTS) -> None:
    provenance = package.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Candidate provenance is missing")
    operation = provenance.get("operation")
    if not isinstance(operation, dict) or operation.get("status") != "SUCCESS":
        raise ValueError("Source operation is not successful")
    if (operation.get("drug_id") not in load_runtime().drugs or
            operation.get("source_family") not in {"DAILYMED", "MOTHERTOBABY"}):
        raise ValueError("Source operation identity is invalid")
    expected_prefix = (
        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/"
        if operation["source_family"] == "DAILYMED"
        else "https://mothertobaby.org/fact-sheets/"
    )
    if not str(operation.get("source_url", "")).startswith(expected_prefix):
        raise ValueError("Source URL does not match source organisation")
    snapshot = _snapshot(operation, snapshot_root)
    digest = sha256(snapshot.read_bytes()).hexdigest()
    if digest != provenance.get("source_content_hash") or digest != operation.get("source_content_hash"):
        raise ValueError("Retrieved source content changed")
    for record in package.get("records", []):
        if (record["drug_id"] != operation["drug_id"] or
                record["source_identifier"] != operation["source_identifier"] or
                record["source_url"] != operation["source_url"]):
            raise ValueError("Evidence source does not match the snapshot")
        if record["source_organisation"].upper() != operation["source_family"]:
            raise ValueError("Evidence source organisation does not match")
    if operation["source_family"] == "MOTHERTOBABY":
        title, sections = mother_sections(snapshot.read_bytes(), operation["canonical_name"])
    else:
        title, _, sections = daily_med_sections(snapshot.read_bytes())
    if any(record["source_title"] != title for record in package.get("records", [])):
        raise ValueError("Evidence source title does not match")
    if not any(section == package["records"][0]["source_section"] and
               excerpt[:5000] == provenance.get("source_excerpt")
               for _, _, section, excerpt in sections):
        raise ValueError("Evidence source excerpt or section changed")


def normalize_operation(operation: dict, candidate_root: Path = CANDIDATES,
                        snapshot_root: Path = SNAPSHOTS) -> int:
    if operation["status"] != "SUCCESS":
        return 0
    snapshot = _snapshot(operation, snapshot_root)
    content = snapshot.read_bytes()
    digest = sha256(content).hexdigest()
    if digest != operation.get("source_content_hash"):
        raise ValueError("Snapshot hash does not match ingestion operation")
    runtime = load_runtime()
    drug_id = operation["drug_id"]
    catalogue = runtime.drugs[drug_id]
    if operation["source_family"] == "MOTHERTOBABY":
        title, sections = mother_sections(content, operation["canonical_name"])
        version = operation.get("source_revision_date") or "undated fact sheet"
        organisation = "MotherToBaby"
    else:
        title, version, sections = daily_med_sections(content)
        organisation = "DailyMed"
        version = version or operation.get("source_revision_date") or "undated SPL"
    records = []
    seen_sections = set()
    for index, (topic, subtopic, section, excerpt) in enumerate(sections, 1):
        # Exact extractive draft. A reviewer must verify and may paraphrase it.
        claim = excerpt[:1600].rstrip()
        if not claim:
            continue
        duplicate_key = (topic, section, claim)
        if duplicate_key in seen_sections:
            continue
        seen_sections.add(duplicate_key)
        evidence_id = f"{drug_id}-{operation['source_family'].lower()}-{digest[:12]}-{index:03}"
        existing_path = candidate_root / f"{evidence_id}.json"
        if existing_path.exists():
            existing = json.loads(existing_path.read_text(encoding="utf-8"))["records"][0]
            if (existing["topic"], existing["source_section"], existing["claim"]) != duplicate_key:
                evidence_id += f"-{topic}"
        record = {
            "evidence_id": evidence_id,
            "drug_id": drug_id, "related_drug_ids": [], "topic": topic,
            "subtopic": subtopic, "claim": claim,
            "source_organisation": organisation, "source_title": title,
            "source_url": operation["source_url"],
            "source_identifier": operation["source_identifier"],
            "source_section": section,
            "source_revision_date": operation.get("source_revision_date") or version,
            "retrieved_at": operation["retrieved_at"], "reviewed_at": None,
            "review_state": "REVIEW_REQUIRED", "reviewer": None,
            "review_mechanism": "explicit_cli_review", "revision": str(version),
            "content_hash": "", "evidence_status": "LIMITED_EVIDENCE",
            "applicable_population": None, "pregnancy_timing": None,
            "lactation_relevance": None, "notes": None,
        }
        record["content_hash"] = canonical_hash(record)
        validate_record(record, runtime)
        records.append({"record": record, "source_excerpt": excerpt[:5000],
                        "canonical_name": catalogue["generic_name"],
                        "therapeutic_group": catalogue["therapeutic_group"]})
    for item in records:
        record = item["record"]
        path = candidate_root / f"{record['evidence_id']}.json"
        if path.exists():
            continue  # Preserve prior human review decisions.
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": "1.0.0", "records": [record],
            "provenance": {
                "operation": operation, "source_content_hash": digest,
                "source_product_identifier": operation["source_identifier"],
                "source_version": version, "canonical_name": item["canonical_name"],
                "therapeutic_group": item["therapeutic_group"],
                "source_excerpt": item["source_excerpt"],
            },
        }
        verify_source(document, snapshot_root)
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(records)


def normalize_all(queue_path: Path = QUEUE_PATH, candidate_root: Path = CANDIDATES,
                  snapshot_root: Path = SNAPSHOTS, report_path: Path = NORMALIZATION_REPORT) -> dict:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    runtime = load_runtime()
    operation_statuses = Counter(row["status"] for row in queue["operations"])
    failures = []
    for operation in queue["operations"]:
        if operation["status"] != "SUCCESS":
            continue
        try:
            normalize_operation(operation, candidate_root, snapshot_root)
        except (ValueError, OSError, ET.ParseError) as exc:
            failures.append({"drug_id": operation["drug_id"],
                             "source_family": operation["source_family"],
                             "reason": type(exc).__name__})
    records = []
    for path in sorted(candidate_root.glob("*.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        records.extend(package.get("records", []))
    counts = Counter(row["review_state"] for row in records)
    by_drug = Counter(row["drug_id"] for row in records)
    by_topic = Counter(row["topic"] for row in records)
    by_source = Counter(row["source_organisation"] for row in records)
    published = load_published_store()
    published_drugs = {row["drug_id"] for row in published.records}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalogue_medications": len(runtime.drugs),
        "processed_medications": len({row["drug_id"] for row in queue["operations"]}),
        "retrieval": dict(operation_statuses),
        "normalization": {
            "total_candidates": len(records), "medications_with_candidates": len(by_drug),
            "by_source": dict(by_source), "by_topic": dict(by_topic),
            "by_review_state": dict(counts), "medications_with_ambiguous_product":
                len({row["drug_id"] for row in queue["operations"]
                     if row["source_family"] == "DAILYMED" and row["status"] == "PARTIAL"}),
            "failures": failures,
        },
        "review": {
            "REVIEW_REQUIRED": counts["REVIEW_REQUIRED"],
            "REVIEWED": counts["REVIEWED"],
            "REJECTED": counts["REJECTED"],
            "PARTIAL": sum(row["review_state"] == "REVIEWED" and
                           row["evidence_status"] == "LIMITED_EVIDENCE" for row in records),
        },
        "domains": {domain: by_topic[domain] for domain in (
            "general_information", "pregnancy", "lactation", "adverse_effects",
            "warnings", "contraindications", "drug_interactions", "monitoring",
            "reproductive_potential")},
        "publication": {
            "runtime_eligible_records": len(published.records),
            "medications_with_published_evidence": len(published_drugs),
            "medications_entirely_insufficient": len(runtime.drugs) - len(published_drugs),
        },
        "best_candidate_coverage": by_drug.most_common(10),
        "largest_source_gaps": [drug_id for drug_id in sorted(runtime.drugs)
                                if by_drug[drug_id] == 0],
        "medication_gaps": [
            {"drug_id": drug_id,
             "candidate_count": by_drug[drug_id],
             "source_statuses": {row["source_family"]: row["status"]
                                 for row in queue["operations"] if row["drug_id"] == drug_id}}
            for drug_id in sorted(runtime.drugs)
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    report = normalize_all()
    print(json.dumps({
        "processed_medications": report["processed_medications"],
        "retrieval": report["retrieval"],
        "normalization": {key: value for key, value in report["normalization"].items()
                          if key != "failures"},
        "review": report["review"],
        "publication": report["publication"],
        "failures": report["normalization"]["failures"],
    }, indent=2))


if __name__ == "__main__":
    main()
