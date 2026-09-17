# RiskSense AI backend

RiskSense AI is a FastAPI/PostgreSQL decision-support backend. It uses JWT authentication, database-backed RBAC, patient-clinician relationships, and authoritative access entitlements. Heart Disease screening inference is implemented using the supplied trained artifact. Diabetes and drug-response directories remain empty; no inference implementations or dedicated regression tests exist for those targets yet.

## Local setup

1. Create a Python 3.13 virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env` and replace every placeholder.
4. Set `DATABASE_URL` to a development PostgreSQL database.
5. Apply Alembic migrations only to the intended development database.
6. Run `python -m uvicorn app.main:app --reload`.

## Tests

Tests require a dedicated local PostgreSQL database named `risksense_test` and an explicit `TEST_DATABASE_URL`. The test guard rejects missing URLs, the application URL, any database with another name, and Supabase hosts.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/risksense_test"
.\.venv\Scripts\python.exe -m pytest
```

Tests apply migrations only to that isolated database. Never point `TEST_DATABASE_URL` to Supabase or a development/production database.

The test bootstrap disables `.env` loading, uses a test-only JWT signing key, requires a literal local PostgreSQL host and the exact `risksense_test` database name, and checks `current_database()` before migrations. Integration tests reset the test schema and use synthetic records. Never run them against data you need to retain.

## Access model

Patient registration does not grant product access. Subscription and insurance submissions begin pending. Only backend-controlled staged verification can create an active `AccessEntitlement`. Mock completion endpoints require an ADMIN account and record their source as `MOCK_PAYMENT` or `MOCK_INSURANCE`. Clinician access requires both an approved clinician profile and an active `PatientClinician` relationship.

The existing unversioned routes remain available. Equivalent `/api/v1` aliases are provided for migration, currently hidden from the generated schema to avoid duplicate documentation.

## Heart Disease model

- Artifact: `app/ml/heart_disease/risksense_heart_disease_model_v1.pkl`
- Metadata: `app/ml/heart_disease/risksense_heart_disease_model_v1_metadata.json`
- Version: `1.0.0`; algorithm: logistic regression with the artifact's packaged imputer and scaler.
- Runtime threshold: `0.23`, retrieved from `artifact["decision_threshold"]`; classification uses `predict_proba()[0, 1] >= threshold`, never `predict()`.
- API target: `heart_disease`. Artifact target: `heart_disease_presence` (Cleveland dataset presence classification, not a future-event time horizon).
- SHA-256: `8aa3839216060029bdd7fa133febfad5d0db00625c41f8f571d2979d04a90453`.

The runtime validates the hash before deserializing the same bytes with joblib, compares all metadata against the artifact, checks feature order and class order, and caches the validated model once per process. Paths resolve from the runtime module, independently of the working directory. API input and database `model_path` never control deserialization. Restart workers after an intentional artifact deployment; an incompatible or altered artifact fails closed. There is no upload API.

Dependencies match the artifact's recorded scikit-learn `1.8.0`, pandas `2.2.3`, and joblib `1.5.3`. NumPy `2.2.6` is pinned and tested on Python 3.13. The supplied metadata does not record its training NumPy version. The artifact is not retrained, resaved, or modified.

### Feature mapping and measurement semantics

The single-row DataFrame uses exactly this ordered contract:

| Position | Feature | Existing source and transformation |
| --- | --- | --- |
| 1 | `age` | Completed years from `Patient.date_of_birth`, evaluated on the UTC analysis date. No duplicate age storage. |
| 2 | `sex` | Model-specific mapping of `Patient.gender`: female → 0, male → 1, ignoring case/outer whitespace. Canonical profile value is unchanged. Unknown/unsupported values are rejected. |
| 3 | `systolic_bp` | Latest non-null `Vital.blood_pressure_systolic` at or before analysis time, in mmHg. Uses the existing positive/≤300 validation bound. |
| 4 | `total_cholesterol` | Latest `LabResult` with `test_type="total_cholesterol"`, converted explicitly to mg/dL. LDL, HDL and triglycerides are never substituted. |
| 5 | `fasting_blood_sugar_high` | Latest `LabResult` with `test_type="fasting_glucose"`, converted to mg/dL, then 1 when >120, otherwise 0. Generic `glucose` records are never assumed fasting. |

Laboratory units must be `mg/dL` or `mmol/L`. Conversion factors are analyte-specific: cholesterol ×38.67 ([AHRQ lipid conversion table](https://www.ncbi.nlm.nih.gov/books/NBK83505/)); glucose ×18.018 ([published cohort methods](https://pure.rug.nl/ws/portalfiles/portal/695839986/Association_of_Initial_and_Longitudinal_Changes_in_C-reactive_Protein_With_the_Risk_of_Cardiovascular_Disease_Cancer_and_Mortality.pdf)). Decimal multiplication avoids intermediate binary rounding; results are not rounded before the strict >120 comparison. At exactly 120 mg/dL the feature is 0. Test cases cover values on both sides of this boundary.

RiskSense retains its broader health profile (height, weight, BMI, diastolic BP, pulse, family history and lifestyle); none of those extra fields is passed to this model. Labs remain optional for the overall profile but required for this inference. Missing values never become zero or reach the pipeline's imputer. Invalid numeric types, non-finite values, nonpositive labs/BP, future birth dates and unsupported units are rejected.

Measurements are selected independently by their recorded date (with deterministic tie-breaking); raw lab values, units, source, verification status and dates are saved alongside the transformed features. No clinical freshness cutoff is invented: older stored readings can currently be reused. They are not represented as newly measured or clinically verified. A clinically approved recency policy and use of gender versus model-specific sex require future product review.

### Activation and endpoint

An administrator first calls `POST /api/v1/admin/models/heart-disease/activate` with a Bearer token and no body. This validates the fixed artifact, creates/reuses its deterministic version record in `ml_models`, and writes `MODEL_ACTIVATED`. Registration is serialized in PostgreSQL. A conflicting active version prevents activation; inference also rejects ambiguous active versions. The existing `/api/v1/admin/models/{model_id}/suspend` disables new inference. A prediction request never implicitly activates a model.

`POST /api/v1/risk-analysis` (also `/risk-analysis`) requires a valid Bearer token:

- PATIENT: authenticated account's own profile and effective active entitlement; omit `patient_id` (or provide only the same patient's ID).
- CLINICIAN: approved clinician, explicit `patient_id`, active patient link and active patient account. Follows existing clinician access policy; a patient's expired subscription does not revoke a clinician's authorized relationship.
- ADMIN: cannot run patient analyses merely by having the administrator role.

The request accepts only `model` and optional `patient_id`. It does not accept raw feature overrides, artifact paths, or the derived fasting flag. Record/update information through the existing profile, vitals and lab APIs first.

Patient request:

```http
POST /api/v1/risk-analysis
Authorization: Bearer <access-token>
Content-Type: application/json

{"model":"heart_disease"}
```

Clinician request:

```json
{"model":"heart_disease","patient_id":"<linked-patient-uuid>"}
```

Success is HTTP 201 using the extended existing `PredictionResponse`: `id`, `patient_id`, `model_id`, `prediction_target`, `risk_score` (0–1), `risk_classification`, `prediction_result`, `explanation`, `predicted_at`, `model_version`, and `decision_threshold`. Below-threshold classification is `not_elevated`, which does not mean disease is absent. Every new result includes: “This result is a risk estimate and is not a medical diagnosis.”

Example success for **synthetic test data**: age 50, male, systolic BP 130 mmHg, total cholesterol 200 mg/dL, fasting glucose 120 mg/dL. Probability below is from the real artifact; identifiers/timestamp are illustrative:

```json
{
  "id": "<prediction-uuid>",
  "patient_id": "<authenticated-patient-uuid>",
  "model_id": "<registered-model-uuid>",
  "prediction_target": "heart_disease",
  "risk_score": 0.5062838823244137,
  "risk_classification": "elevated",
  "prediction_result": "Elevated predicted heart-disease risk",
  "explanation": "This result is a risk estimate and is not a medical diagnosis.",
  "predicted_at": "2026-09-16T14:00:00Z",
  "model_version": "1.0.0",
  "decision_threshold": 0.23
}
```

Missing-labs response (HTTP 422, no inference and no prediction row):

```json
{
  "detail": {
    "code": "MODEL_INPUT_INCOMPLETE",
    "status": "insufficient_data",
    "model": "heart_disease",
    "missing_fields": ["total_cholesterol", "fasting_glucose"],
    "message": "Additional health information is required before Heart Disease risk can be calculated."
  }
}
```

Invalid stored values return HTTP 422 with `VALIDATION_ERROR` and `invalid_fields`. Inactive models return HTTP 503 `MODEL_INACTIVE`; artifact, inference and persistence failures return a sanitized HTTP 503. Unauthenticated requests return 401; role/entitlement denials return 403; cross-patient or unlinked requests return 404.

### Persistence, migrations and tests

No schema migration is needed: lab types are stored as strings and `Prediction.input_data` is already JSONB. No old migration is changed. Predictions reference the existing `ml_models` row and save the exact feature vector, feature order, version, threshold, artifact hash and measurement provenance. History responses read version/threshold from the immutable prediction snapshot, not a later registry value; old predictions without that metadata return null for the new optional fields. Internal input snapshots are not added to API responses.

`PREDICTION_CREATED` is committed atomically with the prediction. Audit metadata contains only target/model identifiers, not raw measurements or credentials. Failed audit persistence rolls back the prediction. No feature-importance explanation is invented.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_heart_disease.py tests/test_heart_disease_integration.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover the real artifact and real API-to-PostgreSQL inference, exact DataFrame order, cached loading, hash/metadata rejection, custom threshold (including 0.23–0.5), missing/invalid inputs, unit conversions, source selection, history snapshots, entitlement/RBAC, suspension, sanitized failures, and atomic audit persistence. This is an academic screening prototype, not a clinically validated diagnostic system.
