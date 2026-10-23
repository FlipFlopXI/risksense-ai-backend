"""Summarize approved-source operation results for medicines lacking published evidence."""
from collections import Counter
import json
from pathlib import Path

from app.ml.drug_assistant.runtime import load_runtime

ROOT = Path("app/ml/drug_assistant")
OUTPUT = Path("DRUG_ASSISTANT_UNCOVERED_MEDICATIONS.md")


def main() -> None:
    runtime = load_runtime()
    published = json.loads((ROOT / "published_evidence_v1.json").read_text(encoding="utf-8"))["records"]
    queue = json.loads((ROOT / "evidence_work/ingestion_queue_v1.json").read_text(encoding="utf-8"))["operations"]
    covered = {item["drug_id"] for item in published}
    operations = {(item["drug_id"], item["source_family"]): item for item in queue}
    uncovered = sorted(set(runtime.drugs) - covered)
    lines = ["# Medicines without runtime-published evidence", "",
             f"{len(uncovered)} of {len(runtime.drugs)} catalogue medicines have no eligible published record.",
             "These operation statuses describe retrieval, not clinical review. `PARTIAL` DailyMed cases need product identity selection; `NO_SOURCE` means the approved adapter found no source. No third-party source has been substituted.",
             "", "| Medicine | DailyMed | MotherToBaby | Next gate |",
             "| --- | --- | --- | --- |"]
    counts = Counter()
    for drug_id in uncovered:
        daily = operations[(drug_id, "DAILYMED")]["status"]
        mtb = operations[(drug_id, "MOTHERTOBABY")]["status"]
        counts[(daily, mtb)] += 1
        gate = ("External review and publication" if daily == "SUCCESS" or mtb == "SUCCESS" else
                "Resolve exact product identity" if daily == "PARTIAL" else
                "Retry failed approved-source retrieval" if "FAILED" in (daily, mtb) else
                "No approved source located")
        lines.append(f"| {drug_id} | {daily} | {mtb} | {gate} |")
    lines += ["", "Operation combinations: " + ", ".join(
        f"{daily}/{mtb}: {count}" for (daily, mtb), count in sorted(counts.items())), ""]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(uncovered)} uncovered medicines; {dict(counts)}")


if __name__ == "__main__":
    main()
