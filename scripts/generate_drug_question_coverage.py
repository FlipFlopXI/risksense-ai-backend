"""Generate a truthful intent-to-evidence coverage matrix from the current code."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import runpy

from app.ml.drug_assistant.evidence_normalization import CANDIDATES
from app.ml.drug_assistant.provider import TOPICS
from app.ml.drug_assistant.runtime import load_runtime

OUTPUT = Path("DRUG_ASSISTANT_QUESTION_COVERAGE.md")
PUBLISHED = Path("app/ml/drug_assistant/published_evidence_v1.json")


def generate() -> dict:
    runtime = load_runtime()
    published = json.loads(PUBLISHED.read_text(encoding="utf-8"))["records"]
    pending = [json.loads(path.read_text(encoding="utf-8"))["records"][0]
               for path in CANDIDATES.glob("*.json")]
    pending = [item for item in pending if item["review_state"] == "REVIEW_REQUIRED"]
    examples = defaultdict(list)
    cases = runpy.run_path("tests/unit/test_drug_question_coverage.py")["QUESTIONS"]
    for question, intent in cases:
        if len(examples[intent]) < 2:
            examples[intent].append(question)
    lines = ["# Drug Assistant question coverage", "",
             f"The immutable v1 taxonomy defines {len(runtime.model['supported_intents'])} intent/status names. "
             f"The routing regression suite contains {len(cases)} direct paraphrases plus conversational and resolver checks.",
             "", "Routing support is separate from reviewed clinical evidence. "
             "A correctly routed question can still return INSUFFICIENT_EVIDENCE.", "",
             "| Intent | Example questions | Required reviewed topic(s) | Routed? | Published / pending records | Remaining gap |",
             "| --- | --- | --- | --- | --- | --- |"]
    for intent in runtime.model["supported_intents"]:
        topics = TOPICS.get(intent, ())
        count_p = sum(row["topic"] in topics for row in published)
        count_r = sum(row["topic"] in topics for row in pending)
        if intent in {"UNSUPPORTED_DRUG", "AMBIGUOUS_DRUG", "EMERGENCY_OR_URGENT", "OUT_OF_SCOPE"}:
            topic = "Routing/safety state; no drug-specific evidence"
            gap = "Not a clinical evidence answer"
        else:
            topic = ", ".join(topics) or "No mapped reviewed topic"
            gap = ("Pending records need external review and publication" if count_r else
                   "No eligible published evidence for this domain" if not count_p else
                   "Coverage varies by medication and source section")
        if intent == "DRUG_INTERACTION":
            gap += "; named pairs require explicit pair-linked evidence"
        sample = "<br>".join(examples[intent]) if examples[intent] else "See immutable taxonomy; no separate direct paraphrase"
        lines.append("| " + " | ".join([intent, sample.replace("|", "/"), topic,
                                         "Yes" if intent in examples else "Policy-defined",
                                         f"{count_p} / {count_r}", gap]) + " |")
    lines.extend(["", "## Conversational and name resolution", "",
                  "- Explicit generic and recognized brand aliases resolve to catalogue IDs. Unknown names fail closed.",
                  "- A single prior medication can carry through topic-only follow-ups; a newly named medication replaces it.",
                  "- Multi-medication interaction claims require reviewed evidence linking the requested pair. General label text is not proof of a pair interaction.",
                  "- Authorized active patient medications may select pair evidence for questions about 'my medications'; unstructured legacy medication text is not used as an authoritative active list.",
                  "- Missing evidence never means a medicine or combination is safe.", ""])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    return {"intents": len(runtime.model["supported_intents"]), "paraphrases": len(cases),
            "published_by_topic": dict(Counter(row["topic"] for row in published)),
            "pending_by_topic": dict(Counter(row["topic"] for row in pending))}


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
