# Drug Assistant question coverage

The immutable v1 taxonomy defines 36 intent/status names. The routing regression suite contains 71 direct paraphrases plus conversational and resolver checks.

Routing support is separate from reviewed clinical evidence. A correctly routed question can still return INSUFFICIENT_EVIDENCE.

| Intent | Example questions | Required reviewed topic(s) | Routed? | Published / pending records | Remaining gap |
| --- | --- | --- | --- | --- | --- |
| DRUG_GENERAL | What is metformin?<br>WHAT DOES METFORMIN DO? | general_information | Yes | 137 / 0 | Coverage varies by medication and source section |
| DRUG_INDICATION | What is metformin used for?<br>Why would someone take metformin? | indications | Yes | 8 / 0 | Coverage varies by medication and source section |
| DRUG_CLASS | What class of drug is metformin?<br>What is the drug class of atorvastatin? | class | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_IDENTIFICATION | Can you identify this metformin tablet?<br>Which medicine is metformin? | identity | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_ALIAS | Is there another name for metformin?<br>What is the other name of atorvastatin? | identity | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_PREGNANCY | Can I take metformin while pregnant?<br>Is metformin okay during pregnancy? | pregnancy | Yes | 493 / 0 | Coverage varies by medication and source section |
| DRUG_PREGNANCY_EXPOSURE | What happens if I'm pregnant and taking metformin?<br>I took metformin before knowing I was pregnant | pregnancy_exposure, pregnancy | Yes | 493 / 0 | Coverage varies by medication and source section |
| DRUG_PREGNANCY_TIMING | What about metformin in the first trimester?<br>Does metformin matter at 12 weeks pregnant? | pregnancy_timing | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_PREGNANCY_EVIDENCE | What human evidence exists for metformin in pregnancy?<br>Show pregnancy evidence for metformin | pregnancy | Yes | 493 / 0 | Coverage varies by medication and source section |
| DRUG_PREGNANCY_REGISTRY | Is there a pregnancy registry for metformin? | pregnancy_registry | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_LACTATION | Can I breastfeed while taking metformin?<br>Does metformin pass into breast milk? | lactation | Yes | 133 / 0 | Coverage varies by medication and source section |
| DRUG_REPRODUCTIVE_POTENTIAL | I am trying to conceive while using metformin<br>Any reproductive considerations for metformin? | reproductive_potential | Yes | 2 / 0 | Coverage varies by medication and source section |
| DRUG_FERTILITY | Can metformin affect fertility?<br>Could metformin cause infertility? | fertility | Yes | 172 / 0 | Coverage varies by medication and source section |
| DRUG_CONTRACEPTION | Does metformin affect contraception?<br>Does metformin interfere with birth control? | contraception | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_PREGNANCY_TESTING | Do I need a pregnancy test before metformin? | pregnancy_testing | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_SIDE_EFFECT | What are metformin's side effects?<br>Can metformin cause any problems? | adverse_effects | Yes | 15 / 0 | Coverage varies by medication and source section |
| DRUG_SERIOUS_WARNING | What serious reactions or warnings apply to metformin?<br>What warnings apply to metformin? | serious_adverse_effects, warnings | Yes | 15 / 0 | Coverage varies by medication and source section |
| DRUG_CONTRAINDICATION | Who should not take metformin?<br>What are metformin's contraindications? | contraindications | Yes | 15 / 0 | Coverage varies by medication and source section |
| DRUG_INTERACTION | Does metformin interact with atorvastatin?<br>Does metformin clash with atorvastatin? | drug_interactions | Yes | 11 / 0 | Coverage varies by medication and source section; named pairs require explicit pair-linked evidence |
| DRUG_FOOD_INTERACTION | Does food affect metformin?<br>Can grapefruit interact with metformin? | food_alcohol_interactions | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_ALCOHOL_INTERACTION | Can I drink alcohol with metformin?<br>Does wine interact with metformin? | food_alcohol_interactions | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_MONITORING | What monitoring is needed with metformin?<br>Should I check my kidneys on metformin? | monitoring | Yes | 54 / 0 | Coverage varies by medication and source section |
| DRUG_STORAGE | How should I store metformin?<br>Should metformin be refrigerated? | storage | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_FORMULATION | How is metformin taken?<br>How do I administer metformin? | administration | Yes | 15 / 0 | Coverage varies by medication and source section |
| DRUG_HEART_CONTEXT | Can metformin affect blood pressure?<br>Is metformin relevant to cardiovascular disease? | drug_condition_interactions | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_DIABETES_CONTEXT | Can metformin affect glucose?<br>Is metformin relevant to diabetes? | drug_condition_interactions | Yes | 0 / 0 | No eligible published evidence for this domain |
| DRUG_PATIENT_CONTEXT | Is metformin suitable with my conditions? | drug_condition_interactions, drug_interactions | Yes | 11 / 0 | Coverage varies by medication and source section |
| DRUG_COMPARISON | Compare metformin versus atorvastatin<br>What is the difference between metformin and atorvastatin? | general_information, warnings | Yes | 152 / 0 | Coverage varies by medication and source section |
| DRUG_SOURCE_REQUEST | Show the source for metformin<br>Where did the information about metformin come from? | general_information | Yes | 137 / 0 | Coverage varies by medication and source section |
| DRUG_EVIDENCE_STRENGTH | How reliable is the evidence for metformin?<br>How recent is the evidence for metformin? | general_information | Yes | 137 / 0 | Coverage varies by medication and source section |
| DRUG_CLINICIAN_DISCUSSION | What should I discuss with my clinician about metformin?<br>What should I ask my pharmacist about metformin? | clinician_discussion | Yes | 8 / 0 | Coverage varies by medication and source section |
| DRUG_MISSED_DOSE_INFORMATION | I missed a metformin dose<br>What if I forgot to take metformin? | missed_dose | Yes | 0 / 0 | No eligible published evidence for this domain |
| UNSUPPORTED_DRUG | See immutable taxonomy; no separate direct paraphrase | Routing/safety state; no drug-specific evidence | Yes | 0 / 0 | Not a clinical evidence answer |
| AMBIGUOUS_DRUG | See immutable taxonomy; no separate direct paraphrase | Routing/safety state; no drug-specific evidence | Yes | 0 / 0 | Not a clinical evidence answer |
| EMERGENCY_OR_URGENT | See immutable taxonomy; no separate direct paraphrase | Routing/safety state; no drug-specific evidence | Yes | 0 / 0 | Not a clinical evidence answer |
| OUT_OF_SCOPE | See immutable taxonomy; no separate direct paraphrase | Routing/safety state; no drug-specific evidence | Yes | 0 / 0 | Not a clinical evidence answer |

## Conversational and name resolution

- Explicit generic and recognized brand aliases resolve to catalogue IDs. Unknown names fail closed.
- A single prior medication can carry through topic-only follow-ups; a newly named medication replaces it.
- Multi-medication interaction claims require reviewed evidence linking the requested pair. General label text is not proof of a pair interaction.
- Authorized active patient medications may select pair evidence for questions about 'my medications'; unstructured legacy medication text is not used as an authoritative active list.
- Missing evidence never means a medicine or combination is safe.
