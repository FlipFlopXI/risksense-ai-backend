"""Routing coverage is independent of whether reviewed clinical evidence exists."""
import pytest

from app.ml.drug_assistant.intent import classify
from app.ml.drug_assistant.resolver import resolve
from app.ml.drug_assistant.runtime import load_runtime


QUESTIONS = [
    ("What is metformin?", "DRUG_GENERAL"),
    ("WHAT DOES METFORMIN DO?", "DRUG_GENERAL"),
    ("Tell me about metformin", "DRUG_GENERAL"),
    ("What should I know before taking metformin?", "DRUG_GENERAL"),
    ("What is metformin used for?", "DRUG_INDICATION"),
    ("Why would someone take metformin?", "DRUG_INDICATION"),
    ("What is metformin prescribed for?", "DRUG_INDICATION"),
    ("What does metformin treat?", "DRUG_INDICATION"),
    ("What class of drug is metformin?", "DRUG_CLASS"),
    ("What is the drug class of atorvastatin?", "DRUG_CLASS"),
    ("Can you identify this metformin tablet?", "DRUG_IDENTIFICATION"),
    ("Which medicine is metformin?", "DRUG_IDENTIFICATION"),
    ("Is there another name for metformin?", "DRUG_ALIAS"),
    ("What is the other name of atorvastatin?", "DRUG_ALIAS"),
    ("Can I take metformin while pregnant?", "DRUG_PREGNANCY"),
    ("Is metformin okay during pregnancy?", "DRUG_PREGNANCY"),
    ("What happens if I'm pregnant and taking metformin?", "DRUG_PREGNANCY_EXPOSURE"),
    ("I took metformin before knowing I was pregnant", "DRUG_PREGNANCY_EXPOSURE"),
    ("I already took metformin while pregnant", "DRUG_PREGNANCY_EXPOSURE"),
    ("What about metformin in the first trimester?", "DRUG_PREGNANCY_TIMING"),
    ("Does metformin matter at 12 weeks pregnant?", "DRUG_PREGNANCY_TIMING"),
    ("What human evidence exists for metformin in pregnancy?", "DRUG_PREGNANCY_EVIDENCE"),
    ("Show pregnancy evidence for metformin", "DRUG_PREGNANCY_EVIDENCE"),
    ("Is there a pregnancy registry for metformin?", "DRUG_PREGNANCY_REGISTRY"),
    ("Can I breastfeed while taking metformin?", "DRUG_LACTATION"),
    ("Does metformin pass into breast milk?", "DRUG_LACTATION"),
    ("What if I am nursing while on metformin?", "DRUG_LACTATION"),
    ("I am trying to conceive while using metformin", "DRUG_REPRODUCTIVE_POTENTIAL"),
    ("Any reproductive considerations for metformin?", "DRUG_REPRODUCTIVE_POTENTIAL"),
    ("Can metformin affect fertility?", "DRUG_FERTILITY"),
    ("Could metformin cause infertility?", "DRUG_FERTILITY"),
    ("Does metformin affect contraception?", "DRUG_CONTRACEPTION"),
    ("Does metformin interfere with birth control?", "DRUG_CONTRACEPTION"),
    ("Do I need a pregnancy test before metformin?", "DRUG_PREGNANCY_TESTING"),
    ("What are metformin's side effects?", "DRUG_SIDE_EFFECT"),
    ("Can metformin cause any problems?", "DRUG_SIDE_EFFECT"),
    ("What reactions can metformin cause?", "DRUG_SIDE_EFFECT"),
    ("What serious reactions or warnings apply to metformin?", "DRUG_SERIOUS_WARNING"),
    ("What warnings apply to metformin?", "DRUG_SERIOUS_WARNING"),
    ("Who should not take metformin?", "DRUG_CONTRAINDICATION"),
    ("What are metformin's contraindications?", "DRUG_CONTRAINDICATION"),
    ("Does metformin interact with atorvastatin?", "DRUG_INTERACTION"),
    ("Does metformin clash with atorvastatin?", "DRUG_INTERACTION"),
    ("Can I combine metformin with lisinopril?", "DRUG_INTERACTION"),
    ("Does metformin interact with my current medications?", "DRUG_INTERACTION"),
    ("Does food affect metformin?", "DRUG_FOOD_INTERACTION"),
    ("Can grapefruit interact with metformin?", "DRUG_FOOD_INTERACTION"),
    ("Can I drink alcohol with metformin?", "DRUG_ALCOHOL_INTERACTION"),
    ("Does wine interact with metformin?", "DRUG_ALCOHOL_INTERACTION"),
    ("What monitoring is needed with metformin?", "DRUG_MONITORING"),
    ("Should I check my kidneys on metformin?", "DRUG_MONITORING"),
    ("How should I store metformin?", "DRUG_STORAGE"),
    ("Should metformin be refrigerated?", "DRUG_STORAGE"),
    ("How is metformin taken?", "DRUG_FORMULATION"),
    ("How do I administer metformin?", "DRUG_FORMULATION"),
    ("Is metformin available as a liquid?", "DRUG_FORMULATION"),
    ("Can metformin affect blood pressure?", "DRUG_HEART_CONTEXT"),
    ("Is metformin relevant to cardiovascular disease?", "DRUG_HEART_CONTEXT"),
    ("Can metformin affect glucose?", "DRUG_DIABETES_CONTEXT"),
    ("Is metformin relevant to diabetes?", "DRUG_DIABETES_CONTEXT"),
    ("Is metformin suitable with my conditions?", "DRUG_PATIENT_CONTEXT"),
    ("Compare metformin versus atorvastatin", "DRUG_COMPARISON"),
    ("What is the difference between metformin and atorvastatin?", "DRUG_COMPARISON"),
    ("Show the source for metformin", "DRUG_SOURCE_REQUEST"),
    ("Where did the information about metformin come from?", "DRUG_SOURCE_REQUEST"),
    ("How reliable is the evidence for metformin?", "DRUG_EVIDENCE_STRENGTH"),
    ("How recent is the evidence for metformin?", "DRUG_EVIDENCE_STRENGTH"),
    ("What should I discuss with my clinician about metformin?", "DRUG_CLINICIAN_DISCUSSION"),
    ("What should I ask my pharmacist about metformin?", "DRUG_CLINICIAN_DISCUSSION"),
    ("I missed a metformin dose", "DRUG_MISSED_DOSE_INFORMATION"),
    ("What if I forgot to take metformin?", "DRUG_MISSED_DOSE_INFORMATION"),
]


@pytest.mark.parametrize("question,expected", QUESTIONS)
def test_paraphrase_intent(question, expected):
    assert classify(question).name == expected


def test_followups_and_medication_switch():
    runtime = load_runtime()
    previous = ("metformin",)
    for question, expected in [
        ("What about during pregnancy?", "DRUG_PREGNANCY"),
        ("And breastfeeding?", "DRUG_LACTATION"),
        ("What about side effects?", "DRUG_SIDE_EFFECT"),
    ]:
        assert classify(question).name == expected
        assert resolve(question, runtime, previous).drug_ids == previous
    assert resolve("What about atorvastatin instead?", runtime, previous).drug_ids == ("atorvastatin",)
    assert resolve("What about unknownmedicinex instead?", runtime, previous).status == "UNSUPPORTED_DRUG"


def test_generic_brand_multi_and_unsupported():
    runtime = load_runtime()
    assert resolve("What is paracetamol?", runtime).drug_ids == ("acetaminophen",)
    assert resolve("Does metformin interact with atorvastatin?", runtime).drug_ids == ("metformin", "atorvastatin")
    assert resolve("What is glipizidee?", runtime).status == "UNSUPPORTED_DRUG"
    assert resolve("I have a small blue pill", runtime).status == "AMBIGUOUS_DRUG"
