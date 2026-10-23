# Drug Assistant evidence normalization report

Generated from the existing local source snapshots on 22 September 2026. Review and publication were completed later that day. The complete per-medication normalization report is at `app/ml/drug_assistant/evidence_work/normalization_report_v1.json`.

## Catalogue and retrieval

| Measure | Count |
|---|---:|
| Catalogue medications processed | 208 / 208 |
| Source operations attempted | 416 |
| SUCCESS | 94 |
| PARTIAL | 194 |
| FAILED | 1 |
| NO_SOURCE | 127 |

The 193 partial DailyMed operations have multiple possible labels. No product was selected automatically. The remaining partial operation is MotherToBaby.

## Normalization and review

| Measure | Count |
|---|---:|
| Normalized candidates | 931 |
| Medications with at least one candidate | 89 |
| DailyMed candidates | 54 |
| MotherToBaby candidates | 877 |
| REVIEW_REQUIRED | 0 |
| REVIEWED | 931 |
| REJECTED | 0 |
| Reviewed with LIMITED_EVIDENCE status | 931 |

The reviewer attested that the existing candidates had been externally reviewed. A dry run found 931 eligible and zero invalid, ambiguous, or failed candidates. Batch attestation changed only review metadata, after creating a timestamped candidate backup. The publisher independently revalidated all 931 records and rejected none.

| Candidate domain | Count |
|---|---:|
| General information | 121 |
| Pregnancy | 485 |
| Lactation | 126 |
| Adverse effects | 7 |
| Warnings | 7 |
| Contraindications | 7 |
| Interactions | 5 |
| Monitoring | 0 |
| Reproductive potential | 1 |
| Fertility | 172 |

The medications with the most candidates are evolocumab (19), methotrexate (17), acetaminophen (15), and carvedilol, fluconazole, lithium and losartan (14 each). Candidate count indicates review workload, not clinical quality or complete coverage.

## Publication and gaps

| Measure | Count |
|---|---:|
| Runtime-eligible published records | 931 |
| Medications with published evidence | 89 |
| Medications still entirely insufficient at runtime | 119 |
| Medications with no normalized candidate | 119 |
| Ambiguous DailyMed medication operations | 193 |

The 119 candidate-free medications include acarbose, acebutolol, acetazolamide, adenosine, alogliptin, amiloride, amiodarone, amoxicillin/clavulanate, apixaban, aripiprazole, aspirin, and atorvastatin. The machine-readable report lists all 119 and each medication's source status. Nortriptyline's MotherToBaby retrieval is the single failed operation.

Metformin has nine published MotherToBaby records: one general-information, five pregnancy, one lactation and two fertility. The DailyMed operation is `PARTIAL` because multiple labels were found. Thus metformin has no published adverse-effect, warning, interaction, or monitoring record. A reviewer must select a suitable exact DailyMed product before those label sections can be normalized.

Runtime now returns cited `LIMITED_EVIDENCE` for metformin general information, pregnancy and lactation, while side effects and interactions remain `INSUFFICIENT_EVIDENCE`. All 931 published records have `LIMITED_EVIDENCE` status; publication did not elevate their evidentiary strength. Published counts by source: MotherToBaby 877, DailyMed 54. Published counts by topic are shown in the domain table above. All 193 ambiguous DailyMed product selections remain unresolved. The database-free regression suite passed 163 tests.
