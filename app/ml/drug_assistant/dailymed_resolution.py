"""Conservative, restartable DailyMed product resolution for review preparation.

Search titles are not product identity evidence. A unique selection additionally
requires a complete search result and a verified human-prescription SPL with one
matching active ingredient. Ambiguous products remain for human selection.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from app.ml.drug_assistant.evidence_pipeline import QUEUE_PATH, WORK_ROOT, _write
from app.ml.drug_assistant.source_adapters import DailyMedAdapter, SourceRetrievalError

REPORT_PATH = Path("DAILYMED_PRODUCT_RESOLUTION_REPORT.md")
RUN_PATH = WORK_ROOT / "dailymed_resolution_run_v1.json"
VERSION = "1.0.0"


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def product_metadata(content: bytes) -> dict:
    root = ET.fromstring(content)
    document_code = next((node.get("code") for node in root if _tag(node) == "code"), None)
    ingredients = []
    for node in root.iter():
        if _tag(node) == "ingredient" and node.get("classCode") in {"ACTIB", "ACTIM", "ACTIR"}:
            names = [" ".join(child.itertext()).strip() for child in node.iter() if _tag(child) == "name"]
            if names:
                ingredients.append(names[0])
    forms = sorted({node.get("displayName") for node in root.iter()
                    if _tag(node) == "formCode" and node.get("displayName")})
    routes = sorted({node.get("displayName") for node in root.iter()
                     if _tag(node) == "routeCode" and node.get("displayName")})
    revision = next((node.get("value") for node in root if _tag(node) == "versionNumber"), None)
    return {"document_code": document_code, "ingredients": sorted(set(ingredients)),
            "routes": routes, "dosage_forms": forms, "revision": revision}


def title_exclusion(title: str, canonical: str) -> str | None:
    product = title.split("[", 1)[0].casefold()
    name = canonical.casefold()
    if re.search(r"\b(?:veterinary|animal use|for dogs|for cats)\b", product):
        return "NON_HUMAN_TITLE"
    if not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", product):
        return None  # An unknown brand could still contain this ingredient.
    if re.search(r"\b(?:and|with)\b|\s/\s", product):
        return "COMBINATION_TITLE"
    return None


def select_unique(candidates: tuple[dict, ...], canonical: str) -> tuple[dict | None, list[dict]]:
    """Only explicit non-human/combination titles can be excluded pre-SPL."""
    assessed = [{**item, "exclusion": title_exclusion(item["title"], canonical)}
                for item in candidates]
    compatible = [item for item in assessed if item["exclusion"] is None]
    if len(compatible) != 1:
        return None, assessed
    return compatible[0], assessed


def _search(adapter: DailyMedAdapter, operation: dict) -> tuple[str, tuple[dict, ...] | None]:
    try:
        return operation["drug_id"], adapter.locate_all(operation["canonical_name"])
    except SourceRetrievalError:
        return operation["drug_id"], None


def run(*, limit: int | None = None, workers: int = 4,
        adapter: DailyMedAdapter | None = None, queue_path: Path = QUEUE_PATH,
        snapshot_root: Path | None = None, report_path: Path = REPORT_PATH,
        run_path: Path = RUN_PATH) -> dict:
    adapter = adapter or DailyMedAdapter()
    snapshot_root = snapshot_root or WORK_ROOT / "snapshots"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    pending = [row for row in queue["operations"]
               if row["source_family"] == "DAILYMED" and row["status"] == "PARTIAL"]
    if limit is not None:
        pending = pending[:limit]
    started = datetime.now(timezone.utc).isoformat()
    searches = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_search, adapter, row) for row in pending]
        for future in as_completed(futures):
            drug_id, result = future.result()
            searches[drug_id] = result
    rows = []
    for operation in pending:
        drug_id = operation["drug_id"]
        candidates = searches[drug_id]
        if candidates is None:
            rows.append({"drug_id": drug_id, "status": "FAILED_SEARCH",
                         "reason": "DailyMed paginated search failed", "candidates": operation.get("candidates", [])})
            continue
        operation["candidates"] = list(candidates)
        operation["candidate_list_complete"] = True
        operation["candidate_list_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        if not candidates:
            operation.update(status="NO_SOURCE", error_code=None)
            rows.append({"drug_id": drug_id, "status": "NO_SOURCE", "reason": "No current DailyMed labels", "candidates": []})
            _write(queue_path, queue)
            continue
        selected, assessed = select_unique(candidates, operation["canonical_name"])
        if selected is None:
            rows.append({"drug_id": drug_id, "status": "AMBIGUOUS",
                         "reason": "Multiple plausible labels or no uniquely compatible title",
                         "candidates": assessed})
            _write(queue_path, queue)
            continue
        try:
            snapshot = adapter.retrieve(selected["set_id"])
            metadata = product_metadata(snapshot.content)
            if (metadata["document_code"] != "34391-3" or
                    [part.casefold() for part in metadata["ingredients"]] !=
                    [operation["canonical_name"].casefold()] or
                    not metadata["dosage_forms"] or not metadata["revision"]):
                raise ValueError("SPL product metadata is not a unique human prescription ingredient match")
            target = snapshot_root / drug_id / f"{snapshot.source_identifier}.xml"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if sha256(target.read_bytes()).hexdigest() != snapshot.content_hash:
                    raise ValueError("Existing snapshot differs from current SPL")
            else:
                target.write_bytes(snapshot.content)
            operation.update(
                status="SUCCESS", source_identifier=snapshot.source_identifier,
                source_url=snapshot.source_url, source_revision_date=snapshot.source_revision_date,
                source_content_hash=snapshot.content_hash,
                retrieved_at=datetime.now(timezone.utc).isoformat(), error_code=None,
                product_selection_reason="HIGH_CONFIDENCE_UNIQUE_MATCH",
                product_resolution_version=VERSION,
                product_resolution_at=datetime.now(timezone.utc).isoformat(),
                product_resolution_criteria={"complete_search": True, "human_prescription": True,
                                             "single_exact_active_ingredient": True,
                                             "unique_compatible_candidate": True,
                                             "routes": metadata["routes"],
                                             "dosage_forms": metadata["dosage_forms"]},
                selected_product_title=selected["title"],
            )
            rows.append({"drug_id": drug_id, "status": "HIGH_CONFIDENCE_UNIQUE_MATCH",
                         "reason": "Only one compatible current label; verified human prescription SPL and exact ingredient",
                         "selected_set_id": selected["set_id"], "metadata": metadata,
                         "candidates": assessed})
        except (SourceRetrievalError, ET.ParseError, ValueError, OSError) as exc:
            rows.append({"drug_id": drug_id, "status": "FAILED_VERIFICATION",
                         "reason": type(exc).__name__, "candidates": assessed})
        _write(queue_path, queue)
    result = {"resolver_version": VERSION, "started_at": started,
              "finished_at": datetime.now(timezone.utc).isoformat(), "rows": rows}
    _write(run_path, result)
    report_path.write_text(render_report(result), encoding="utf-8")
    return result


def render_report(result: dict) -> str:
    from collections import Counter
    counts = Counter(row["status"] for row in result["rows"])
    lines = ["# DailyMed product resolution", "",
             f"Run: {result['started_at']} · Resolver {result['resolver_version']}", "",
             "Only a unique compatible human-prescription SPL with one exact active ingredient is selected.",
             "Unknown brand identity, missing route/form verification, and equally valid labels remain for human review.",
             "Ingredient, route, dosage form and human-prescription status are shown only where the SPL was verified; unknown values are not inferred from a title.",
             "The first 12 candidate labels per medicine are shown below. The complete candidate list is in `evidence_work/dailymed_resolution_run_v1.json` and the ingestion queue.",
             "", "## Results", "",
             "| Classification | Count |", "| --- | ---: |",
             *[f"| {key} | {value} |" for key, value in sorted(counts.items())], ""]
    for row in result["rows"]:
        lines.extend([f"## {row['drug_id']} — {row['status']}", "", row["reason"], "",
                      "| SET ID | Product | Ingredients | Route | Dosage form | Human Rx | Revision | Decision |",
                      "| --- | --- | --- | --- | --- | --- | --- | --- |"])
        candidates = row.get("candidates", [])
        for item in candidates[:12]:
            selected = item["set_id"] == row.get("selected_set_id")
            metadata = row.get("metadata", {}) if selected else {}
            cell = lambda value: str(value or "Not verified").replace("|", "/")
            lines.append("| " + " | ".join([
                cell(item.get("set_id")), cell(item.get("title")),
                cell(", ".join(metadata.get("ingredients", []))),
                cell(", ".join(metadata.get("routes", []))),
                cell(", ".join(metadata.get("dosage_forms", []))),
                "Yes" if selected else "Not verified",
                cell(metadata.get("revision") or item.get("spl_version")),
                cell("SELECTED" if selected else item.get("exclusion") or "Ambiguous"),
            ]) + " |")
        if len(candidates) > 12:
            lines.append(f"| … | {len(candidates) - 12} more candidates in the machine-readable run file | | | | | | |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = run(limit=args.limit, workers=args.workers)
    from collections import Counter
    print(dict(Counter(row["status"] for row in result["rows"])))
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
