# RiskSense AI Backend Context

## 18 September 2026 evidence and API-readiness phase

The Drug Assistant has an additive, versioned, human-review-gated evidence store; pair-aware interaction retrieval; claim/citation validation; a restartable 208-medication ingestion queue; generated evidence coverage; and a golden question regression set. The five supplied artifacts remain unchanged. The reviewer externally reviewed and batch-attested 931 normalized candidates for 89 medications; all 931 passed independent publication validation. The other 119 medications remain entirely insufficient, and metformin side effects and interactions remain uncovered. See `DRUG_EVIDENCE_NORMALIZATION_REPORT.md` for counts and gaps.

API integration status is documented in `BACKEND_API_READINESS.md`, `BACKEND_ENDPOINT_INVENTORY.json`, and `FRONTEND_API_INTEGRATION_MATRIX.md`. The backend is not yet classified frontend-ready because the isolated PostgreSQL suite is blocked and several frontend functions lack endpoints.

Last updated: 17 September 2026

## Drug Assistant implementation update

The Drug & Pregnancy Information Assistant has now been implemented. See
`DRUG_ASSISTANT.md` for the current architecture, artifact hashes, source limitations,
API/Swagger workflow, authorization and persistence details. The current code
migration head is `c83f20a6d912`, following the Diabetes waist revision
`b72e9a61c403`. It adds optional reproductive context, normalized patient
medications and persistent Drug Assistant sessions/messages. All supplied drug
clinical cache records are unreviewed; current clinical questions correctly return
evidence-limited answers. This component is deterministic and does not use an LLM
or create ML predictions. The earlier validation figures below describe the
Diabetes checkpoint, not the later Drug Assistant test run.

This document records the backend as it currently exists in the repository. It is a technical handoff and working-state reference. `AGENTS.md` remains the source of truth for engineering and security constraints, while `README.md` contains setup and feature usage details.

## Current State

RiskSense AI is a synchronous FastAPI and SQLAlchemy 2.x backend using PostgreSQL, Alembic, Pydantic v2, OAuth2 Bearer authentication, JWTs, Argon2id password hashing, role-based authorization, access entitlements, clinician-patient relationships, audit logging, and persisted ML predictions.

Supported roles:

- `PATIENT`
- `CLINICIAN`
- `ADMIN`

Public registration creates patient accounts only. Clinician accounts require admin provisioning and approval. Admin accounts are not publicly self-created.

The application exposes both unversioned routes and compatibility aliases under `/api/v1`. Swagger is available at `/docs` when the FastAPI application is running.

## Configuration

Runtime configuration is read in `app/core/config.py` from environment variables, with `.env` loading supported for local development.

Relevant variables:

- `DATABASE_URL`
- `TEST_DATABASE_URL`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `ENVIRONMENT`
- `CORS_ORIGINS`

Do not print, document, commit, or hard-code their values. `.env` remains ignored by Git.

When `ENVIRONMENT=test`, database configuration comes from `TEST_DATABASE_URL`. The pytest guard requires:

- PostgreSQL;
- a local host (`localhost`, `127.0.0.1`, or `::1`);
- database name exactly `risksense_test`;
- no connection query overrides;
- a successful `SELECT current_database()` check before migrations or schema resets.

Tests must never fall back to `DATABASE_URL` or the development database.

## Authentication

Login endpoint:

```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=<email>&password=<password>
```

Versioned alias: `POST /api/v1/auth/login`.

The response contains `access_token` and `token_type: bearer`. Protected requests use:

```http
Authorization: Bearer <access_token>
```

Swagger uses the OAuth2 password flow. In `/docs`, click **Authorize**, enter the account email in **username** and its password in **password**, leave client credentials empty, and authorize. Swagger calls `/auth/login` and attaches the returned Bearer token.

JWT validation checks signature, expiry, token type, subject UUID, current database user existence, and current account activity. Invalid tokens and inactive accounts receive HTTP 401. Authorization always uses the current database user role rather than a client-provided role.

Auth endpoints:

- `POST /auth/register` — public patient registration only
- `POST /auth/login` — OAuth2 form login
- `GET /auth/me` — current authenticated user

Login success, login failure, invalid-token activity, and authorization failures are audited where implemented. Passwords, password hashes, JWTs, signing keys, and database credentials must never enter audit details.

## Core Data Model

The current PostgreSQL schema includes:

- `users`
- `patients`
- `clinicians`
- `health_profiles`
- `vitals`
- `lab_results`
- `subscriptions`
- `insurance`
- `access_entitlements`
- `patient_clinicians`
- `ml_models`
- `predictions`
- `reports`
- `audit_logs`

Important ownership and authorization relationships:

- A patient belongs to one user account.
- A clinician belongs to one user account and has an approval state plus a RiskSense clinician ID.
- `PatientClinician` is the authoritative clinician-patient link.
- `AccessEntitlement` is the authoritative patient entitlement record.
- A prediction belongs to one patient and one immutable model identity.
- Prediction provenance is stored in `Prediction.input_data` as JSONB.

## Entitlement and Access Rules

Patient risk analysis requires an effective entitlement. `get_effective_entitlement()` requires all of the following:

- entitlement status is `active`;
- `verified_at` is present;
- `expires_at` is absent or in the future;
- the linked clinician exists, is approved, and has an active user account;
- for subscription entitlements, the referenced subscription is active and unexpired;
- for insurance entitlements, the referenced insurance is verified and coverage is unexpired.

Patients cannot directly activate entitlements, subscriptions, insurance, or ML models. The existing zero-cost demonstration workflow uses explicitly staged endpoints:

- `POST /access/mock/subscription/complete`
- `POST /access/mock/insurance/complete`

These flows validate an existing approved clinician, activate the authoritative source record, create/update the entitlement, establish the patient-clinician relationship, and write audit events. They are staged demonstrations, not real payment or insurer integrations.

Clinicians may access only patients with an active `PatientClinician` relationship. Knowing a patient UUID does not grant access. Unlinked resources are returned as not found to avoid resource disclosure.

## Health Data

The patient health profile supports height in centimetres, weight in kilograms, waist circumference in centimetres, lifestyle fields, structured family-history flags, conditions, and medications.

BMI is not independently stored. The canonical `HealthProfile.bmi` property calculates:

```text
weight_kg / (height_cm / 100)^2
```

and rounds to two decimals. Diabetes inference validates the stored height and weight before using this value.

Waist circumference is stored in `health_profiles.waist_circumference_cm`. It is nullable for legacy patients and constrained to a finite API value greater than 0 and at most 300 cm. The database has the corresponding positive/maximum check constraint.

Vitals preserve their measurement timestamp. Blood-pressure inference uses systolic and diastolic values from the same complete, non-future vital record. Laboratory results are separate from vitals and retain test type, value, unit, source, verification state, and measurement time.

Patient health endpoints include:

- `POST`, `GET`, `PUT /health/profile`
- `POST`, `GET /health/vitals/`
- `POST`, `GET /health/labs/`
- `GET /health/trends`

## Risk Analysis API

Primary endpoint:

```http
POST /risk-analysis
Authorization: Bearer <access-token>
Content-Type: application/json
```

Versioned alias: `POST /api/v1/risk-analysis`.

Accepted requests:

```json
{"model": "heart_disease"}
```

```json
{"model": "diabetes"}
```

`patient_id` is optional for patients and must either be omitted or match the authenticated patient's record. Approved clinicians must supply `patient_id` and have an active link to that patient. Admin role alone does not grant clinical inference access.

The request schema rejects additional properties. Clients cannot submit raw model features, artifact paths, thresholds, model versions, or authoritative access state.

Before inference, the endpoint enforces authentication, account activity, RBAC, patient ownership or clinician linking, patient entitlement where required, active model registration, artifact integrity, and complete valid clinical inputs.

Successful inference returns HTTP 201 and persists the prediction plus `PREDICTION_CREATED` audit event in one transaction. A failed inference or audit write does not leave a successful prediction row.

Persisted provenance includes:

- exact feature values and order;
- model version;
- decision threshold;
- artifact SHA-256;
- source profile, vital, and lab record IDs;
- source units and measurement timestamps;
- the inference timestamp and safety explanation.

## Heart Disease Model

Runtime: `app/ml/heart_disease/runtime.py`

Artifact: `app/ml/heart_disease/risksense_heart_disease_model_v1.pkl`

Current contract:

- version: `1.0.0`
- target: `heart_disease`
- algorithm: Logistic Regression pipeline
- threshold: `0.23`
- artifact SHA-256: `8aa3839216060029bdd7fa133febfad5d0db00625c41f8f571d2979d04a90453`
- classification: probability at or above threshold is `elevated`; otherwise `not_elevated`

Exact feature order:

1. `age`
2. `sex`
3. `systolic_bp`
4. `total_cholesterol`
5. `fasting_blood_sugar_high`

Sources:

- age: completed years from `Patient.date_of_birth`
- sex: normalized `Patient.gender` (`female = 0`, `male = 1`)
- systolic BP: latest appropriate non-future vital, mmHg
- total cholesterol: latest total-cholesterol lab with supported unit conversion
- fasting-blood-sugar flag: derived from the latest fasting-glucose lab using the validated runtime contract

Activation endpoint: `POST /admin/models/heart-disease/activate`, ADMIN-only, no body.

## Diabetes Model v1

Runtime: `app/ml/diabetes/runtime.py`

Artifact: `app/ml/diabetes/risksense_diabetes_model_v1.pkl`

Metadata: `app/ml/diabetes/risksense_diabetes_model_v1_metadata.json`

Current contract:

- version: `1.0.0`
- prediction target: `diabetes_risk`
- algorithm: Logistic Regression pipeline
- source dataset: NHANES 2017–2018
- artifact SHA-256: `efe8967a0e70d2ee0f63cab2b02d03ba91685a3b75a8d8d6c90918a8ff3c6496`
- threshold: `0.455`, loaded from the artifact and checked against metadata
- classification: probability at or above threshold is `elevated`; otherwise `standard`
- supported population: adults aged 18 and older

The artifact is hashed before deserialization. Runtime validation checks its version, prediction target, feature order, threshold, population metadata, feature units, sex encoding, classifier type, class order, and pipeline feature names. Artifact or metadata mismatches fail closed with a sanitized model-unavailable response.

Exact feature order:

1. `age`
2. `sex`
3. `bmi`
4. `waist_circumference`
5. `systolic_bp`
6. `diastolic_bp`

Feature sources and units:

- age: completed years from `Patient.date_of_birth`
- sex: normalized `Patient.gender` (`female = 0`, `male = 1`)
- BMI: canonical BMI derived from health-profile kilograms and centimetres, kg/m²
- waist circumference: `HealthProfile.waist_circumference_cm`, cm
- systolic and diastolic BP: latest complete pair from the same non-future vital, mmHg

All six inputs are required by the patient-facing API. Although the training pipeline contains BP imputation, production inference does not use that to conceal missing clinical data. Missing values return HTTP 422 `MODEL_INPUT_INCOMPLETE`; invalid values or unsupported units return HTTP 422 `VALIDATION_ERROR`. Under-18 requests receive a clear validation response and no prediction.

Activation endpoint: `POST /admin/models/diabetes/activate`, ADMIN-only, no body.

Diabetes v1 estimates risk using a target representing prevalent, self-reported diagnosed diabetes. It is not a diagnosis, prospective disease-onset prediction, or externally validated clinical tool. Its persisted and returned explanation states that limitation.

## Model Registry

Heart Disease and Diabetes use deterministic model UUIDs derived from their target and artifact hash. Activation validates the fixed server-side artifact and creates or reuses its `ml_models` record. PostgreSQL advisory transaction locks serialize registration.

Multiple prediction targets can be active simultaneously. Activation of Diabetes does not suspend Heart Disease. For a given target, a conflicting or ambiguous active version fails closed.

Admin model endpoints:

- `GET /admin/models`
- `POST /admin/models/heart-disease/activate`
- `POST /admin/models/diabetes/activate`
- `POST /admin/models/{model_id}/suspend`

Model activation and suspension are audited.

## Alembic State

Migration chain:

```text
e31c044fd963  initial database schema
    -> a14f1c2d9b01  non-ML backend foundation
    -> b72e9a61c403  nullable health-profile waist circumference (current head)
```

`b72e9a61c403` adds `health_profiles.waist_circumference_cm` and `ck_health_profiles_waist_cm`. Its downgrade removes that column and constraint, which discards recorded waist measurements.

The configured development PostgreSQL database was successfully upgraded from `a14f1c2d9b01` to `b72e9a61c403` during local validation. No schema reset or downgrade was performed on development data.

## Automated Testing

The test suite currently collects 172 tests. It includes:

- database-independent model/runtime, JWT, schema, access-control, vital, and model tests;
- isolated PostgreSQL security integration tests;
- Heart Disease API-to-database integration tests;
- Diabetes API-to-database integration tests;
- Alembic clean-upgrade, legacy-upgrade, preservation, constraint, and downgrade tests.

The latest database-independent validation passed 125 tests. Python compilation, application imports, OpenAPI generation, artifact-integrity checks, and `git diff --check` also passed.

The full PostgreSQL suite was not executed in the latest session because `TEST_DATABASE_URL` was unavailable to that process. The guard correctly refused to use the application database. The following 47 database-backed tests remain to be run against a safely configured local `risksense_test` database:

- 17 Diabetes integration tests
- 1 Diabetes migration test
- 20 Heart Disease integration tests
- 3 foundation migration tests
- 5 security integration tests
- 1 database-safety test

Run the complete suite only after confirming the guarded test database:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Database-free Diabetes checks can run independently:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit --confcutdir=tests/unit -q
```

## Latest Local Development Validation

The existing development patient account supplied for the controlled test was reused. No replacement patient was created and no password was changed or stored in source.

Validated state:

- patient UUID: `d4259fe1-3cd6-4eda-b784-2ae86974c113`
- effective active entitlement: confirmed
- active approved clinician relationship: confirmed
- height and weight preserved: 178 cm and 80 kg
- canonical BMI: 25.25 kg/m²
- existing 130/80 mmHg BP pair reused
- waist circumference added to the existing health profile: 100 cm synthetic development value

The real development login flow and real application dependency graph were used. No authentication or database dependency override was used for the end-to-end request.

Diabetes end-to-end result:

- patient login: HTTP 200
- ADMIN model activation: HTTP 200
- `POST /risk-analysis` with `{"model":"diabetes"}`: HTTP 201
- exact vector received by the artifact: `[50, 1, 25.25, 100, 130, 80]`
- risk score: `0.410235721429783`
- classification: `standard`
- prediction UUID: `56aa3684-ed71-4260-9341-af94daba61e1`
- prediction, feature snapshot, measurement provenance, and audit persistence: confirmed

Heart Disease regression result:

- activation: HTTP 200
- `POST /risk-analysis` with `{"model":"heart_disease"}`: HTTP 201
- score: `0.506283882324414`
- classification: `elevated`
- prediction UUID: `cd2ac172-4061-4dd2-a872-1a408db9cf92`
- Heart Disease and Diabetes model records remained active together

These values describe synthetic local development validation and must not be treated as clinical findings or stable fixture IDs.

## Error Behavior

Current risk-analysis behavior includes:

- 401 for missing, malformed, expired, or inactive-user authentication
- 403 for wrong roles or missing effective patient entitlement
- 404 for cross-patient or unlinked clinician access
- 422 `MODEL_INPUT_INCOMPLETE` for missing required model data
- 422 `VALIDATION_ERROR` for invalid values or unsupported units
- 503 `MODEL_INACTIVE` when the requested target has no active registered model
- sanitized 503 responses for artifact, inference, registry, or persistence failures

Internal exceptions, SQL, file paths, secrets, and credentials are not returned to clients.

## Current Working Tree

The Diabetes implementation and documentation are intentionally uncommitted for manual review. Current work includes:

- shared fixed-artifact runtime utilities;
- Diabetes artifact runtime and service;
- Diabetes request routing and ADMIN activation;
- waist-circumference model/schema/service support;
- Alembic revision `b72e9a61c403`;
- comprehensive Diabetes unit, integration, and migration tests;
- Heart Disease reuse of shared runtime and prediction-persistence helpers;
- updated README documentation.

No commit or push has been performed. Before committing, run the complete PostgreSQL suite with a valid isolated `TEST_DATABASE_URL`, inspect `git diff`, and manually verify Swagger.

## Immediate Manual Swagger Workflow

1. Start Uvicorn with the configured development environment.
2. Open `/docs`.
3. Authorize through the OAuth2 form using the existing development patient account.
4. Call `POST /risk-analysis`.
5. Submit:

```json
{
  "model": "diabetes"
}
```

The authenticated patient does not need to retrieve or supply a patient UUID. With the validated development state above, the expected outcome is HTTP 201 with a persisted Diabetes risk estimate.

## Non-Negotiable Safety Boundaries

- Do not expose or commit secrets, credentials, JWTs, password hashes, or database URLs.
- Do not point tests at the development or production-like database.
- Do not weaken authentication, RBAC, entitlement, clinician-link, ownership, or artifact-integrity checks.
- Do not let patients activate subscriptions, insurance, entitlements, or ML models.
- Do not fabricate, zero-fill, or silently reinterpret missing clinical inputs.
- Do not retrain, resave, or alter supplied ML artifacts or metadata without an explicit model-development task.
- Do not describe either model as diagnostic or clinically validated.
- Do not commit, push, reset, or rewrite Git history without explicit authorization.
# Frontend-readiness completion (18 September 2026)

The current head adds rotating refresh sessions and logout revocation, longitudinal body measurements and historical BMI trends, direct patient-to-clinician relationship retrieval, prediction-backed report generation/PDF download, and an ADMIN-only Drug Assistant operational status endpoint. Alembic revision `d54b8c21e7f0` adds `auth_sessions` and `body_measurements` over `c83f20a6d912`; it has not yet been applied to the configured development database.

Drug evidence processing attempted all 416 DailyMed/MotherToBaby operations: 94 succeeded, 194 were partial, 127 had no source, and one failed. The externally reviewed 931 candidates are published with `LIMITED_EVIDENCE` status; 193 ambiguous DailyMed product selections remain unresolved. New or changed source records still require review and publication validation.

The repository currently collects 301 tests. The database-free unit run passes all 155 tests. Database-backed validation and migration smoke testing remain blocked pending approved access to the configured development database.

## Drug Assistant evidence expansion (23 September 2026)

The catalogue remains 208 medications. The runtime published store remains 931 `LIMITED_EVIDENCE` records for 89 medications, leaving 119 entirely without runtime evidence. A conservative, paginated DailyMed search and SPL identity check resolved one of 193 ambiguous products, bempedoic acid; 192 operations remain partial. One new authoritative SPL snapshot and 147 pending review candidates were generated. No new candidate was approved or published. The existing 931 reviewed candidates and fixed five JSON artifacts remain unchanged. See `DAILYMED_PRODUCT_RESOLUTION_REPORT.md`, `DRUG_ASSISTANT_NEW_EVIDENCE_REVIEW.md`, `DRUG_ASSISTANT_QUESTION_COVERAGE.md`, `DRUG_ASSISTANT_UNCOVERED_MEDICATIONS.md`, and `DRUG_EVIDENCE_WORKFLOW.md` for review and publication steps. Pair interaction replies now require explicitly linked evidence, and the new manifest confines later external attestation to this batch.

## Drug Assistant publication (23 September 2026)

The user explicitly confirmed external review and approved precisely the 147 candidates in `expansion_review_manifest_v1.json`. Manifest verification and dry run found 147 eligible, zero unrelated and zero invalid. Batch attestation created a backup and reviewed all 147. The independent publisher accepted all 1,078 reviewed candidates, with zero rejections. Current published evidence spans 90 of 208 medicines; 118 remain without published evidence. All records remain `LIMITED_EVIDENCE`. A fresh provider, full 244-test database-free suite, OpenAPI, compilation, normalization idempotency, live patient chat and live ADMIN status all passed. The local development API is running in a fresh process without auto-reload because the sandbox blocked Uvicorn's Windows reloader. No commit or push was made.
# Patient web activation (2026-09-30)

The patient activation path is separate from the admin mock-completion routes. Authenticated patients issue a 15-minute one-time handoff URL with `POST /api/v1/access/activation-session`. The website exchanges the token for a narrowly scoped credential, looks up an approved clinician, and calls `POST /api/v1/access/activation/complete` with exactly one demo access method. The backend derives patient identity from the activation session and commits the subscription or simulated insurance state, clinician link, active entitlement, audit events, and session consumption together. The patient app rechecks `GET /api/v1/access/status`. This workflow requires the additive `f29a6e7d104b` migration, `WEBAPP_BASE_URL`, and explicit `DEMO_ACTIVATION_ENABLED=true`; the flag defaults to false. Email verification is not currently represented on `User` and is not claimed. Production HTTPS App Link verification remains dependent on the final custom domain.
