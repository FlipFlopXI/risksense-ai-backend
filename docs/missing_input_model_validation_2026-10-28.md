# Missing-input model validation — 2026-10-28

The candidate study used the official UCI processed Cleveland data (303 rows)
and CDC NHANES 2017–2018 data (4,717 usable adult rows). Reproduce it with
`scripts/evaluate_missing_input_candidates.py` and the source files documented
in `docs/model_candidate_audit_2026-10-26.md`.

Rows were split by person 80/20 with stratification and random state 42. Only
the training portion was duplicated with selected measurements hidden. The
same person never crossed a cross-validation fold or the held-out boundary.
The held-out portion was evaluated with complete and missing inputs. Hidden
measurements represent absent values; no clinical value was fabricated.

| Model and scenario | Deployed accuracy | Deployed sensitivity | Candidate accuracy | Candidate sensitivity |
| --- | ---: | ---: | ---: | ---: |
| Heart, complete | 0.541 | 0.929 | 0.541 | 0.964 |
| Heart, cholesterol missing | 0.557 | 0.964 | 0.508 | 0.964 |
| Heart, glucose missing | 0.541 | 0.929 | 0.525 | 0.964 |
| Heart, both labs missing | 0.541 | 0.964 | 0.525 | 0.964 |
| Diabetes, complete | 0.677 | 0.803 | 0.628 | 0.854 |
| Diabetes, BP pair missing | 0.676 | 0.818 | 0.614 | 0.869 |

The two trained candidate pipelines and exact evaluation output are stored in
`artifacts/model_candidates/2026-10-28/`. The evaluation JSON records each
artifact's SHA-256 digest. These are offline research candidates and are not
registered, loaded, or activatable by the application.

Candidate thresholds were selected using cross-validation only, targeting
high sensitivity across each missing-input pattern. Both candidates lost
held-out accuracy in relevant scenarios. Neither candidate was promoted or
published as a model artifact. The existing immutable model artifacts and
decision thresholds remain deployed.

The Heart Disease artifact already packages a median imputer, which executed
on the held-out missing-lab cases. Its input validator now permits genuinely
absent lab values and records those absences in the prediction snapshot. The
API uses only lab values explicitly supplied for that analysis request;
historical LabResult rows are never silently reused. Results with missing labs
carry an uncertainty notice. Diabetes has no fasting-glucose or cholesterol
predictors; its deployed model and feature contract remain unchanged.

These datasets represent prevalent disease in their source populations, not
future disease onset. The heart holdout has only 61 people. Results are
development evidence and do not establish clinical validity for South African
patients or imply that a missing-lab prediction is as reliable as a complete
clinical assessment.

Sources: [UCI Heart Disease](https://archive.ics.uci.edu/dataset/45/heart+disease)
and [CDC NHANES 2017–2018](https://wwwn.cdc.gov/nchs/nhanes/search/DataPage.aspx?Cycle=2017-2018).
