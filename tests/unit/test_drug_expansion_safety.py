"""Safety checks for conservative product selection and pair claims."""
from app.ml.drug_assistant.composer import compose
from app.ml.drug_assistant.dailymed_resolution import select_unique
from app.ml.drug_assistant.provider import Evidence
from app.ml.drug_assistant.runtime import load_runtime
from scripts.review_drug_evidence import _manifest_ids, batch_plan


def test_product_selection_rejects_two_plausible_labels():
    labels = (
        {"set_id": "a", "title": "BEMPEDOIC ACID tablet"},
        {"set_id": "b", "title": "BEMPEDOIC ACID tablet - another manufacturer"},
    )
    selected, assessed = select_unique(labels, "bempedoic acid")
    assert selected is None and len(assessed) == 2


def test_product_selection_excludes_explicit_combination_title():
    labels = (
        {"set_id": "a", "title": "BEMPEDOIC ACID and EZETIMIBE tablet"},
        {"set_id": "b", "title": "BEMPEDOIC ACID tablet"},
    )
    selected, assessed = select_unique(labels, "bempedoic acid")
    assert selected["set_id"] == "b"
    assert assessed[0]["exclusion"] == "COMBINATION_TITLE"


class GeneralInteractionProvider:
    def retrieve(self, drug_id, intent, related_drug_ids=()):
        return Evidence("LIMITED_EVIDENCE", ({
            "evidence_id": f"general-{drug_id}", "drug_id": drug_id,
            "field": "drug_interactions", "content": "A general label excerpt.",
            "evidence_status": "LIMITED_EVIDENCE", "related_drug_ids": [],
            "source_urls": ["https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/example.xml"],
        },), ({"url": "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/example.xml"},))


def test_general_interaction_label_does_not_answer_named_pair():
    result = compose("Does metformin interact with atorvastatin?", load_runtime(),
                     provider=GeneralInteractionProvider())
    assert result["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert not result["claims"] and not result["sources"]
    assert result["interactions"][0]["evidence_status"] == "INSUFFICIENT_EVIDENCE"


def test_new_review_manifest_is_exact_pending_scope():
    ids = _manifest_ids("app/ml/drug_assistant/evidence_work/expansion_review_manifest_v1.json")
    plan = batch_plan(candidate_ids=ids)
    assert len(ids) == plan["total_candidate_records"] == plan["already_reviewed"] == 147
    assert plan["pending_records"] == 0 and not plan["eligible"]
    assert not plan["skipped_invalid"] and not plan["failed"]
