"""Conservative deterministic routing; urgent phrases precede ordinary intent rules."""
import re
from dataclasses import dataclass
from app.ml.drug_assistant.runtime import normalize


@dataclass(frozen=True)
class Intent:
    name: str
    urgent_category: str | None = None


URGENT_RULES = (
    ("suspected_overdose", r"\b(overdos\w*|too many (?:pills|tablets)|took too much|swallowed too much)\b|\b(?:took|swallowed|taken)\s+(?:\d{2,}|forty|twenty|thirty|fifty|hundred)\s+(?:pills|tablets|capsules)\b"),
    ("difficulty_breathing", r"\b(can t breathe|cannot breathe|can not breathe|difficulty breathing|trouble breathing|struggling to breathe|stopped breathing|gasping|choking)\b"),
    ("severe_allergic_reaction", r"\b(anaphyl\w*|severe allergic reaction)\b|\b(face|throat|tongue|lips)\b.{0,20}\b(swell\w*)\b|\b(swell\w*)\b.{0,20}\b(face|throat|tongue|lips)\b"),
    ("loss_of_consciousness", r"\b(unconscious|passed out|lost consciousness|not waking|won t wake|unresponsive)\b"),
    ("severe_bleeding", r"\b(bleeding heavily|heavy bleeding|severe bleeding|vomiting blood|bleeding won t stop)\b"),
    ("severe_medication_reaction", r"\b(seizure|severe (?:medication |drug )?reaction|blistering rash|skin peeling)\b"),
    ("immediate_danger", r"\b(kill myself|end my life|suicid\w*|immediate danger|severe chest pain)\b"),
    ("severe_pregnancy_related_symptoms", r"\b(pregnan\w*|baby)\b.{0,100}\b(severe (?:pain|headache)|blurred vision|not moving|stopped moving)\b|\bsevere (?:abdominal|stomach) pain\b.{0,100}\bpregnan\w*\b"),
)

RULES = (
    ("DRUG_PREGNANCY_REGISTRY", r"pregnancy.*registry|exposure registry"),
    ("DRUG_PREGNANCY_TESTING", r"pregnancy test"),
    ("DRUG_PREGNANCY_EXPOSURE", r"before i knew|before knowing.*pregnan|found out.*pregnant|accidental.*exposure|already took.*pregnan|pregnant.*(?:been taking|took|taking)|took.*pregnant|taking.*(?:and|while).*pregnan"),
    ("DRUG_PREGNANCY_TIMING", r"trimester|weeks? pregnant|early pregnancy|pregnancy timing"),
    ("DRUG_PREGNANCY_EVIDENCE", r"(?:human|animal).*evidence|(?:human|animal).*data|pregnancy evidence"),
    ("DRUG_LACTATION", r"breastfeed|breast feed|breastfed|breast milk|lactation|milk (?:production|supply)|nursing"),
    ("DRUG_CONTRACEPTION", r"contracepti|birth control"),
    ("DRUG_FERTILITY", r"fertility|infertility"),
    ("DRUG_REPRODUCTIVE_POTENTIAL", r"trying to (?:conceive|become pregnant)|reproductive|planning.*pregnan"),
    ("DRUG_CLINICIAN_DISCUSSION", r"(?:ask|discuss|discussion|questions).*(?:doctor|clinician|pharmacist|obstetrician)"),
    ("DRUG_PREGNANCY", r"pregnan|fetus|foetus|unborn"),
    ("DRUG_MISSED_DOSE_INFORMATION", r"missed.*dose|forgot.*(?:dose|take)|double.*dose|skip.*dose"),
    ("DRUG_ALCOHOL_INTERACTION", r"alcohol|beer|wine"),
    ("DRUG_FOOD_INTERACTION", r"food|grapefruit|meal"),
    ("DRUG_INTERACTION", r"interact|together|combine|other medic|clash|with (?:my )?(?:other )?(?:medicines|medications|drugs)"),
    ("DRUG_CONTRAINDICATION", r"contraindicat|who should not|should.*avoid"),
    ("DRUG_SERIOUS_WARNING", r"warning|serious.*(?:effect|reaction)|danger"),
    ("DRUG_SIDE_EFFECT", r"side effects?|adverse|reactions? (?:can|could|does|might)|(?:can|could|does|might).*(?:cause|give).*(?:reaction|problem)"),
    ("DRUG_MONITORING", r"monitor|check.*(?:blood|kidney|liver)|tests needed"),
    ("DRUG_STORAGE", r"stor(?:e|age)|refrigerat|keep.*medicine"),
    ("DRUG_FORMULATION", r"formulation|strength|liquid|injection|tablet form|how (?:is|do i|should i).*\b(?:take|taken|administer|administered|use|used)\b|administered"),
    ("DRUG_COMPARISON", r"difference|compare|versus|\bvs\b"),
    ("DRUG_HEART_CONTEXT", r"heart|cardiovascular|blood pressure"),
    ("DRUG_DIABETES_CONTEXT", r"diabet|blood sugar|glucose"),
    ("DRUG_PATIENT_CONTEXT", r"my (?:profile|conditions|medications)|recorded medicines|my health"),
    ("DRUG_EVIDENCE_STRENGTH", r"evidence|how recent|reliable|certain"),
    ("DRUG_SOURCE_REQUEST", r"source|citation|where did.*information"),
    ("DRUG_ALIAS", r"another name|other name|alias|same as"),
    ("DRUG_CLASS", r"drug class|class of|what class"),
    ("DRUG_INDICATION", r"used for|use(?:s)? (?:of|for)|why.*(?:take|prescrib)|prescribed for|what.*treat|treats|indication"),
    ("DRUG_IDENTIFICATION", r"identify|which medicine|what pill|what tablet"),
    ("DRUG_GENERAL", r"what is|what s|what does .* do|tell me|information|what should i know|can i (?:take|use)|medicine|medication|drug"),
)


def classify(message: str) -> Intent:
    value = normalize(message)
    for category, pattern in URGENT_RULES:
        if re.search(pattern, value):
            return Intent("EMERGENCY_OR_URGENT", category)
    for name, pattern in RULES:
        if re.search(pattern, value):
            return Intent(name)
    return Intent("OUT_OF_SCOPE")
