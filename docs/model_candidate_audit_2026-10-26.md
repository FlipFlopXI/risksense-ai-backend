# RiskSense model candidate audit — 2026-10-26

No deployed model, threshold, registry row, or prediction record was changed.
Official public source files were downloaded to a temporary local directory for
offline comparison. Reproduce with `scripts/evaluate_heart_candidates.py` and
`scripts/evaluate_diabetes_candidates.py` using the corresponding source files.

## Current targets and limitations

- Diabetes v1 predicts **prevalent, self-reported diagnosed diabetes** in the
  NHANES 2017–2018 adult sample. It does not predict future diabetes onset.
- Heart Disease v1 predicts **angiographic disease presence** in the UCI
  processed Cleveland hospital sample (303 records). It does not predict a
  person's future heart attack or cardiovascular event.
- Neither source population establishes accuracy for South African app users.

## Same-contract candidate comparison

Both scripts preserve the existing feature and label definitions, use a
stratified 80/20 split with random state 42, and choose a candidate on
five-fold out-of-fold predictions from the training partition. The held-out
partition is then evaluated once. These are development comparisons, not
external clinical validation.

| Model | Configuration | Held-out accuracy | Held-out sensitivity | Result |
| --- | --- | ---: | ---: | --- |
| Heart deployed v1 | Logistic regression, threshold 0.230 | 0.541 | 0.929 | Baseline |
| Heart selected candidate | Logistic regression, C=0.1, threshold 0.318 | 0.607 | 0.893 | Rejected: sensitivity fell |
| Diabetes deployed v1 | Logistic regression, threshold 0.455 | 0.677 | 0.803 | Baseline |
| Diabetes selected candidate | Logistic regression, C=0.1, threshold 0.140 | 0.699 | 0.781 | Rejected: sensitivity fell |

The deployed artifacts remain the safer choice under the requested rule to
preserve sensitivity. The diabetes artifact's recorded threshold was selected
against its held-out partition; a future retraining study should reserve a
genuinely untouched test set and external validation cohort.

## Data needed for a meaningful upgrade

The cited public source files are available directly from
[CDC NHANES 2017–2018](https://wwwn.cdc.gov/nchs/nhanes/search/DataPage.aspx?Cycle=2017-2018)
(`DEMO_J.xpt`, `BMX_J.xpt`, `BPX_J.xpt`, `GHB_J.xpt`, `DIQ_J.xpt`) and
[UCI Heart Disease](https://archive.ics.uci.edu/dataset/45/heart%2BdiseaseHeart)
(`processed.cleveland.data`). These alone do not solve population or target
mismatch.

For clinical performance work, provide **de-identified, legitimately
shareable** baseline and outcome records from the intended patient population:

1. Baseline date, age, sex coding, height/weight, waist, blood pressure,
   relevant laboratory values with units and dates, and source/provenance.
2. A precisely defined outcome and ascertainment date. For future-risk claims,
   include follow-up duration and incident outcomes, not only existing disease.
3. Missingness indicators, enrollment setting, inclusion/exclusion rules,
   permitted use terms, and train/validation/external-test site or time split.
4. No names, contact details, national IDs, or direct patient identifiers.

Any change to target, input features, score meaning, or classification
threshold requires a new versioned artifact, calibration and subgroup checks,
external validation, backend contract changes, and a new mobile explanation.

## Drug Assistant expansion

The current runtime separates catalogue resolution from reviewed, published
evidence. Adding names alone cannot create supported medical answers. For each
requested new medicine, supply generic name/aliases and current authoritative
source identifiers or documents. Candidate sources include
[DailyMed SPL labels](https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm),
[MotherToBaby fact sheets](https://mothertobaby.org/fact-sheets/), and
[LactMed](https://www.ncbi.nlm.nih.gov/books/NBK501922/).
An external clinical/content review must approve normalized claims before
publication; the app must keep returning insufficient evidence when an
eligible reviewed record is absent.
