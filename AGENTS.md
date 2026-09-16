# RiskSense AI — Backend Engineering Instructions

## 1. Project Identity

Project Name: RiskSense AI

Formal Purpose:
RiskSense AI is a Zero-Trust Mobile Health Decision Support System for chronic disease risk and surrogate drug-response prediction.

The backend supports:
- Flutter patient application
- Clinician application/portal
- Administrator functionality
- RiskSense website
- Subscription activation
- Insurance-linked access
- Clinician-patient linking
- Health data management
- Machine-learning risk analysis
- Reports
- Audit/security monitoring

This is a university final-year project intended to demonstrate professional software engineering, cybersecurity, artificial intelligence, database, API, and mobile/web integration practices.

The project must remain zero-cost wherever possible.

---

# 2. Core Technology Stack

Backend:
- Python 3.13
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL
- Supabase PostgreSQL
- psycopg 3.x
- Alembic
- Pydantic v2

Authentication/Security:
- OAuth2 Bearer authentication
- JWT
- PyJWT
- pwdlib
- Argon2id password hashing
- Role-Based Access Control (RBAC)
- Zero-Trust authorization principles

ML:
- scikit-learn
- pandas
- numpy
- joblib
- matplotlib where development analysis requires it

Client systems:
- Flutter mobile application
- RiskSense web frontend

Do not unnecessarily replace the existing technology stack.

Do not convert the application to asynchronous SQLAlchemy unless explicitly requested.

---

# 3. Repository Architecture

Preserve the existing layered architecture unless a change is clearly justified.

Expected structure:

app/
├── main.py
├── api/
│   └── v1/
├── core/
├── db/
├── models/
├── schemas/
├── services/
└── ml/
    ├── diabetes/
    ├── heart_disease/
    └── drug_response/

tests/
alembic/

Responsibilities:

api/v1/
- HTTP/API layer
- request handling
- dependency injection
- response models
- HTTP status translation

schemas/
- Pydantic request/response contracts
- validation

services/
- business logic
- database operations
- transaction logic
- authorization-supporting operations

models/
- SQLAlchemy persistence models

core/
- security
- configuration
- dependencies
- cross-cutting backend infrastructure

ml/
- preprocessing
- model loading
- model inference
- model-specific feature definitions
- ML utilities

Do not place substantial business logic directly inside API route handlers.

---

# 4. Source of Truth

Before modifying functionality:

1. Inspect the existing implementation.
2. Inspect relevant models.
3. Inspect schemas.
4. Inspect services.
5. Inspect routers.
6. Inspect Alembic migrations.
7. Inspect existing tests.
8. Understand existing relationships.

Never assume a feature is absent merely because this file describes it as planned.

The repository is the source of truth for current implementation.

This AGENTS.md is the source of truth for intended architecture and engineering constraints.

If repository implementation conflicts with these requirements, identify the conflict before making a major architectural change.

---

# 5. Security Rules

RiskSense handles health-related information.

Security is a primary architectural requirement.

Never:

- expose secrets
- print secrets
- commit secrets
- hard-code credentials
- commit `.env`
- expose JWT signing keys
- expose database credentials
- expose passwords
- log passwords
- log access tokens
- trust client-side authorization state
- trust a client-supplied patient ID for ownership
- allow patients to grant themselves access
- allow patients to approve insurance
- allow patients to activate subscriptions
- allow patients to activate ML models
- allow clients to select arbitrary user roles during public registration

`.env` must remain ignored by Git.

An `.env.example` may document required variable names without containing real secrets.

---

# 6. Zero-Trust Principles

Authentication alone does not grant access.

Every sensitive request should evaluate relevant authorization information.

Conceptually:

Request
→ Token valid?
→ User exists?
→ Account allowed?
→ Correct role?
→ Resource ownership/relationship valid?
→ Entitlement valid where required?
→ Requested operation permitted?
→ Execute
→ Audit where appropriate

Never trust the frontend to enforce authorization.

The backend is authoritative.

---

# 7. Roles

Supported roles:

PATIENT
CLINICIAN
ADMIN

Public registration creates PATIENT accounts only.

A user must never be able to select CLINICIAN or ADMIN through public patient registration.

Clinician access requires an approved clinician workflow.

Admin accounts must not be publicly self-created.

RBAC must use the current database user rather than trusting a role supplied by the client.

---

# 8. Patient Registration and Onboarding

Target patient lifecycle:

Register
→ Patient account created
→ Access/entitlement verification
→ Clinician link established where required
→ Entitlement becomes active
→ Health onboarding completed
→ Dashboard access

Registration should collect appropriate identity/account fields including:

- first name
- last name
- email
- password
- date of birth
- gender/sex where required by the product/model
- other fields only when justified

Age should normally be derived from date of birth rather than stored independently.

Registration and entitlement are separate concepts.

A checkbox such as:

"I have a verified RiskSense AI subscription or insurance benefit."

is a frontend UX confirmation only.

It must never grant backend authorization.

The preferred architecture is:

REGISTER FIRST
→ VERIFY/LINK ACCESS
→ COMPLETE ONBOARDING

---

# 9. Access Entitlement Architecture

RiskSense is a subscription-based and insurance-linked application.

Patients may gain authorized access through:

1. SUBSCRIPTION
2. INSURANCE

Create/use an authoritative entitlement layer.

Conceptual AccessEntitlement:

- id
- patient_id
- source
- status
- clinician_id if appropriate
- insurance_id if applicable
- subscription_id if applicable
- reference_number / activation reference
- verified_at
- expires_at
- created_at
- updated_at

Possible source values:

SUBSCRIPTION
INSURANCE

Expected lifecycle statuses should support:

PENDING
ACTIVE
EXPIRED
CANCELLED

Add additional states only if justified.

The backend controls entitlement status.

Patients must not directly activate or extend entitlements.

Sensitive patient functionality may require an ACTIVE entitlement.

Centralize entitlement checking through reusable dependencies/services rather than duplicating it in every route.

---

# 10. Website Activation Flow

The RiskSense website is not merely a marketing site.

It acts as the product's access/subscription/insurance activation gateway.

Two primary flows exist.

## Subscription Route

Website
→ Choose subscription
→ Provide/verify clinician identifier
→ Payment or staged/mock payment verification
→ Subscription created/renewed
→ Entitlement activated
→ Patient-clinician relationship established
→ Continue application onboarding/access

Supported conceptual billing choices:

- monthly
- monthly debit order
- annual

Because this is a zero-cost university project, payment functionality may use a clearly labelled mock/staged verification workflow unless a legitimate free integration is deliberately added.

Never represent a mock payment as a real financial transaction.

## Insurance Route

Website
→ Select supported insurance provider
→ Enter policy/member details
→ Provide clinician identifier
→ Staged/mock insurance verification
→ Insurance record verified
→ Entitlement activated
→ Patient-clinician relationship established
→ Continue application onboarding/access

Because no real insurer agreements currently exist, insurance verification must be clearly represented as a demonstration/mock integration.

Never imply that a real insurer verified coverage when it did not.

---

# 11. Clinician Linking

Clinician linking is a core RiskSense requirement.

Both subscription and insurance activation workflows must support linking the patient to their referring/associated clinician.

Do not create arbitrary clinician accounts from patient-entered clinician details.

Clinicians must already exist as approved RiskSense clinicians.

Patients should preferably enter a RiskSense-specific clinician identifier.

Example:

RS-CLN-48291

The backend then:

1. searches for the clinician
2. confirms the clinician exists
3. confirms the clinician is active/approved
4. displays/returns safe clinician identity information for confirmation
5. establishes the relationship

Professional license numbers and RiskSense clinician identifiers are separate concepts.

Clinician should eventually support fields such as:

- internal UUID
- user_id
- risk_sense_id
- professional license number
- first name
- last name
- professional title
- specialization
- institution
- active/approval status
- joined timestamp

Do not expose unnecessary professional/private information to patients.

---

# 12. Patient-Clinician Relationship

Implement a dedicated relationship model rather than relying only on an entitlement foreign key.

Conceptually:

PatientClinician
- id
- patient_id
- clinician_id
- status
- linked_at
- unlinked_at
- created_at
- updated_at

Expected states:

ACTIVE
INACTIVE

Enforce appropriate uniqueness so duplicate active relationships are not accidentally created.

This relationship controls clinician access to patient resources.

A clinician must NEVER be allowed to access arbitrary patients merely by knowing their UUID.

Clinician access requires an authorized relationship.

Future architecture should allow safe clinician reassignment/unlinking.

---

# 13. Subscription Security

The current implementation must be hardened.

Patients must NOT be able to directly control:

- authoritative subscription status
- expiration date
- activation
- entitlement state
- payment verification

Patient-facing operations may allow actions such as:

- view subscription
- select/request a plan
- initiate renewal
- follow website renewal flow

Backend-controlled operations determine:

- ACTIVE
- EXPIRED
- CANCELLED
- activation timestamps
- expiration
- entitlement

Subscription should eventually support:

- subscription/reference number
- plan
- billing frequency
- status
- started_at
- expires_at
- renewal information
- created_at
- updated_at

Renewal behavior:

If a subscription is still active, purchased time should normally extend from the existing expiration date.

If already expired, renewal time should normally begin from the new activation time.

Do not silently destroy useful subscription history.

If necessary, introduce a subscription-event/history structure rather than forcing all history into one mutable row.

---

# 14. Insurance Security

Separate:

PATIENT-SUPPLIED INSURANCE DETAILS

from:

AUTHORITATIVE VERIFICATION STATE

A patient providing:

- insurer
- policy number
- member number
- plan

does NOT mean coverage is verified.

Patients must not set authoritative coverage status.

Insurance should support verification metadata such as:

- provider
- policy/member information
- verification status
- verified_at
- verification source
- coverage/effective dates where applicable

Consider an InsuranceProvider model for the website's supported provider list rather than unrestricted provider text.

Mock/staged verification must be clearly identified as such.

---

# 15. Patient Profile and Health Profile

Patient profile functionality must support the application UI.

Patient-facing profile information includes conceptually:

- name
- email
- gender/sex
- member/reference ID
- insurance company if insurance-linked
- subscription status/time remaining if subscription-linked
- renewal path

Health profile should contain reusable medical/lifestyle information rather than forcing the patient to enter everything for every prediction.

Relevant information includes:

- height
- weight
- smoking status
- exercise/activity status
- alcohol status
- family history
- existing conditions
- current medications
- other model-required persistent fields

Avoid unnecessary sensitive information.

Structured values should be preferred where ML or validation depends on them.

BMI should be calculated from validated height and weight rather than treated as an independently authoritative measurement.

---

# 16. Family History

Family history is used as a potential prediction factor.

Do not rely exclusively on an unstructured text string if ML requires specific family-history variables.

For relevant disease models, structured fields may include:

- family history of diabetes
- family history of heart disease
- family history of hypertension

A general notes field may coexist with structured model features if useful.

---

# 17. Vitals

Vitals represent actual recorded measurements.

Current core vital types include:

- heart rate
- oxygen saturation
- temperature
- systolic blood pressure
- diastolic blood pressure

Validate physiologically plausible ranges where appropriate without pretending validation establishes medical correctness.

Reject a vital record containing no measurements.

Validate timestamp behavior.

Do not allow obviously invalid BP relationships such as diastolic exceeding systolic without deliberate handling.

Every measurement should preserve its recorded timestamp.

Future wearable/device provenance may be added.

---

# 18. Laboratory Data

Laboratory measurements must not be confused with wearable vitals.

Risk analysis may use:

- glucose
- HbA1c
- LDL
- HDL
- creatinine

Home users may not have new laboratory measurements available every time they run a risk analysis.

Therefore:

- not every laboratory value should automatically be required
- model-specific required features must be explicit
- previously recorded lab values may be reused when clinically/product appropriate
- reused values must preserve measurement date/source
- never invent missing lab values
- never silently replace missing values with zero
- report missing required fields explicitly

A dedicated LabResult architecture is preferred over placing laboratory data inside wearable Vital records.

Conceptual LabResult fields may include:

- id
- patient_id
- test type
- value
- unit
- source
- measured_at
- verification/provenance where appropriate
- created_at

Exact implementation should be designed before migration.

---

# 19. Patient Risk Analysis

Primary planned disease models:

1. Diabetes
2. Heart Disease

The UI may expose separate actions such as:

Run Diabetes Risk Analysis
Run Heart Disease Risk Analysis

Backend endpoints should clearly identify the requested model/target.

Before inference:

1. authenticate user
2. authorize patient/clinician mode
3. validate entitlement where applicable
4. validate required inputs
5. retrieve permitted persistent profile/lab values
6. validate model is active
7. construct exact feature vector
8. run preprocessing associated with that model version
9. run inference
10. create prediction record where persistence is expected
11. create appropriate audit event

Never silently invent features.

---

# 20. Machine Learning Safety

RiskSense is decision-support software.

It must not claim:

- definitive diagnosis
- guaranteed disease development
- guaranteed treatment outcome
- genomic prediction when no genomic data exists

Use language such as:

- estimated risk
- risk assessment
- decision support
- surrogate drug-response assessment

Appropriate disclaimer concept:

"RiskSense AI provides risk estimates for decision support and does not replace professional medical diagnosis or treatment."

Do not present model output as medical certainty.

---

# 21. Diabetes Model

Current planned baseline:

- Logistic Regression
- StandardScaler
- class_weight="balanced"
- random_state=42
- max_iter=1000
- stratified train/test split
- threshold evaluation/tuning
- ROC-AUC
- confusion matrix
- coefficient-based feature interpretation where appropriate

Current dataset work uses DiaBD-style features.

Before production inference, define the exact persisted feature contract and ensure training preprocessing exactly matches runtime preprocessing.

Serialized model/preprocessor artifacts must be versioned and integrity-aware.

---

# 22. Heart Disease Model

Heart disease prediction is the second primary disease-risk model.

Before implementation:

- define dataset
- define exact features
- define preprocessing
- define units
- define missing-value behavior
- define evaluation methodology
- define probability/risk interpretation

Do not create an API contract before the model's feature contract is known.

---

# 23. Drug Response Assistant

Drug response is a surrogate clinical risk feature.

It must not claim pharmacogenomic/genomic analysis unless genomic data is actually collected and validated.

The Med Assistant UI may eventually provide a conversational interface, but medical claims must remain constrained.

The backend should separate:

- deterministic application logic
- model inference
- conversational explanation

Do not allow a chatbot layer to invent model outputs.

---

# 24. Model Registry and Versioning

The existing ML model registry must evolve into a reliable model-version system.

Each prediction must be traceable to the exact model version used.

Model records should capture appropriate metadata such as:

- name
- version
- prediction target
- algorithm
- dataset/provenance
- metrics
- artifact path
- artifact integrity/hash where feasible
- active status
- timestamps

Prefer immutable model-version records.

Deploying a new version should generally create a new version record rather than rewriting historical model identity.

Prevent ambiguous simultaneous active versions for the same target unless intentionally supported.

Admin model-management actions must be audited.

---

# 25. Predictions

Prediction records must preserve:

- patient
- exact model/model version
- prediction target
- probability/risk score where applicable
- risk classification
- input snapshot
- explanation/contributing factors
- prediction timestamp

Input snapshots are important for reproducibility.

Historical predictions must not change simply because a new model version becomes active.

Risk scores should have appropriate database/application constraints.

---

# 26. Prediction Result UI Support

Backend responses should support the patient result interface, including:

- risk percentage/probability where scientifically valid
- severity/risk classification
- primary contributing factors
- model/version metadata where appropriate
- timestamp
- safe explanation

The frontend may visualize contributing factors using progress bars.

Do not imply causal certainty merely because a feature has high model importance.

---

# 27. Prediction History

Patient prediction history should support:

- chronological listing
- target/type
- severity
- timestamp
- filtering
- opening an individual prediction
- recent history visualization

Clinicians may view predictions only for appropriately linked/authorized patients.

Admins should not automatically receive unrestricted clinical viewing merely because they are admins; expose only what administrative functionality legitimately requires.

---

# 28. Health Trends

Health Trends should visualize actual measurements.

Planned trends include:

- blood glucose
- BMI
- systolic blood pressure

Do not describe a measurement as being "generated by a prediction."

Predictions may contain snapshots of measurements used during inference, but measurements and predictions remain separate concepts.

Use measurement history as the authoritative trend source.

---

# 29. Reports

Reports may summarize prediction and health information.

Potential actions:

- generate report
- retrieve report
- list patient reports

Reports must be associated with the correct patient.

If linked to a prediction, database/application logic must prevent a report belonging to Patient A from referencing Patient B's prediction.

Report generation must be audited.

Medical wording must remain decision-support oriented.

---

# 30. Clinician Dashboard

Clinician functionality should support:

- clinician identity/profile
- linked patients
- recently linked patients
- high-risk alerts
- patients requiring review
- recent patient risk analyses
- drug-response flags
- authorized prediction review

Dashboard metrics must be derived from authorized data.

---

# 31. Clinician Patients Screen

Clinicians should be able to:

- list linked patients
- search linked patients
- filter linked patients
- view latest permitted risk information
- open authorized patient records

Every patient lookup must enforce the PatientClinician relationship.

Never implement:

GET arbitrary patient UUID → clinician sees patient

without relationship authorization.

---

# 32. Clinical Assessment Mode

Clinicians require a temporary/in-person assessment mode.

The clinician may enter patient-like demographic, lifestyle, vital, and laboratory inputs and run a risk assessment.

Unless a deliberate patient-linked workflow is selected:

- do not create a Patient record
- do not save Vitals
- do not save LabResults
- do not add the assessment to a real patient's history

This is intended for demonstrations or temporary in-person assessments.

Audit requirements should still be considered.

---

# 33. Clinician Profile

Clinician profile should eventually support:

- RiskSense clinician ID
- professional license
- name
- institution
- professional title
- specialization
- email
- joined date
- last login
- active/approval status

RiskSense clinician ID is an application identifier.

It is not the same as a professional license number.

---

# 34. Admin Dashboard

Admin functionality should support operational/security management including:

- total users
- users added recently
- clinician count
- predictions this month
- security events
- unreviewed events
- recent application activity

Do not expose more medical information than required for legitimate administration.

---

# 35. Admin User Management

Admin should eventually be able to:

- search users
- filter users
- inspect appropriate account information
- suspend account
- restore account

Account suspension/restoration must:

- be backend controlled
- affect authorization promptly
- be audited

Do not delete important audit history when suspending a user.

---

# 36. Account Lifecycle

The existing `is_active` boolean may eventually need a richer account lifecycle.

Possible conceptual states:

- PENDING_ACCESS
- ACTIVE
- SUSPENDED
- DEACTIVATED

Do not introduce this enum casually.

Design migration behavior and existing-user compatibility first.

Onboarding completion should preferably remain separate from security/account status.

---

# 37. Audit Logging

Audit logging is a major RiskSense requirement.

The existing AuditLog model must be used.

Important events include:

- REGISTER
- LOGIN_SUCCESS
- LOGIN_FAILURE
- LOGOUT where meaningful
- UNAUTHORIZED_ACCESS_ATTEMPT
- HEALTH_PROFILE_CREATED
- HEALTH_PROFILE_UPDATED
- relevant patient-record access
- VITAL_CREATED
- LAB_RESULT_CREATED
- PREDICTION_CREATED
- REPORT_GENERATED
- INSURANCE_VERIFICATION
- SUBSCRIPTION_ACTIVATION
- SUBSCRIPTION_RENEWAL
- CLINICIAN_LINKED
- CLINICIAN_UNLINKED
- USER_SUSPENDED
- USER_REACTIVATED
- MODEL_ACTIVATED
- MODEL_SUSPENDED
- MODEL_VERSION_UPDATED

Audit records must never contain:

- passwords
- password hashes
- JWTs
- secret keys
- database credentials
- unnecessary raw medical payloads

Use minimal useful metadata.

---

# 38. Standard API Errors

Move toward a consistent error contract.

Useful conceptual error codes include:

AUTHENTICATION_REQUIRED
INVALID_TOKEN
FORBIDDEN
ENTITLEMENT_REQUIRED
ENTITLEMENT_EXPIRED
RESOURCE_ACCESS_DENIED
DUPLICATE_RESOURCE
VALIDATION_ERROR
CLINICIAN_NOT_FOUND
CLINICIAN_INACTIVE
INSURANCE_VERIFICATION_FAILED
SUBSCRIPTION_VERIFICATION_FAILED
MODEL_INACTIVE
MODEL_INPUT_INCOMPLETE

Do not leak internal exceptions, SQL, credentials, or sensitive implementation details.

---

# 39. API Versioning

The target API contract is:

/api/v1/...

Current routes are not consistently versioned despite residing under `api/v1`.

Standardize carefully.

Do not unexpectedly break existing Flutter/web integrations.

If migration compatibility is needed, document it.

Use consistent naming and HTTP semantics.

Use PATCH rather than PUT when an operation is truly partial unless compatibility requires otherwise.

---

# 40. Configuration

Move toward one validated configuration source.

Configuration should include appropriate fields such as:

- DATABASE_URL
- JWT_SECRET_KEY
- JWT_ALGORITHM
- ACCESS_TOKEN_EXPIRE_MINUTES
- ENVIRONMENT
- CORS configuration where required

Do not repeatedly load `.env` independently throughout unrelated modules.

Never provide real secret values in source-controlled files.

---

# 41. Authentication Hardening

Correctly handle PyJWT exceptions.

Invalid, malformed, expired, or incorrectly signed tokens should result in appropriate authentication responses rather than internal server errors.

Consider appropriate JWT claims:

- sub
- exp
- iat
- token type
- issuer/audience if the architecture uses them

Do not add complexity without tests.

Future functionality may include:

- refresh tokens
- session revocation
- password reset/change
- logout/session invalidation
- signing-key rotation

Implement deliberately and incrementally.

---

# 42. Rate Limiting and Abuse Protection

Authentication and sensitive public endpoints require abuse protection before production-like deployment.

Particular attention:

- login
- registration
- clinician verification
- insurance verification
- subscription activation
- prediction endpoints

Use a solution compatible with zero-cost deployment constraints.

Do not implement an unreliable in-memory security mechanism and describe it as distributed production protection without qualification.

---

# 43. CORS

CORS must be explicit.

Do not use unrestricted origins together with credential-sensitive production behavior.

Support known development origins and configurable deployment origins.

---

# 44. Database Integrity

Use database constraints where they materially protect correctness.

Examples:

- unique user email
- unique clinician RiskSense ID
- appropriate professional-license uniqueness
- relationship uniqueness
- valid probability/risk ranges
- temporal consistency
- appropriate enum/state constraints
- cross-resource ownership validation

Indexes should support common access patterns including:

- vitals by patient/time
- labs by patient/test/time
- predictions by patient/time
- audit events by user/time
- patient-clinician relationships
- entitlements by patient/status

Do not add indexes blindly.

---

# 45. Transactions

Database writes should have predictable transaction behavior.

Handle:

- commit
- rollback
- integrity violations
- race conditions
- duplicate requests

Avoid fragile:

check if row exists
→ insert

logic where concurrency could produce uncontrolled server errors.

Translate expected integrity failures into safe API errors.

---

# 46. Alembic Rules

All schema changes must use Alembic.

Never manually alter the production/development Supabase schema as a substitute for migrations.

Before generating migrations:

- inspect current models
- inspect current migration head
- ensure models are registered in metadata

After generating:

- inspect migration contents
- verify upgrade path
- verify downgrade behavior where reasonable
- test against an appropriate development/test database before relying on it

Never run destructive migration commands without explicit approval.

Never drop existing user/health data casually.

---

# 47. Testing

Testing is required before major backend expansion.

Use pytest.

Tests should eventually cover:

Authentication:
- registration
- duplicate registration
- login success
- login failure
- invalid token
- expired token
- inactive/suspended user

RBAC:
- patient access
- clinician access
- admin access
- forbidden role behavior

Ownership:
- patient cannot access another patient's resources
- clinician cannot access unlinked patient
- linked clinician can access explicitly permitted resources

Entitlement:
- patient cannot activate own subscription
- patient cannot change authoritative expiry
- patient cannot approve own insurance
- inactive entitlement blocks protected functionality
- active entitlement permits intended functionality
- expired entitlement is rejected

Health:
- profile validation
- vital validation
- empty vital rejection
- timestamp behavior
- BP validation

Clinician:
- identifier verification
- patient linking
- duplicate relationship handling
- inactive clinician rejection

ML:
- feature validation
- preprocessing consistency
- model loading
- inactive model rejection
- deterministic test inference where appropriate

Predictions:
- model version recorded
- input snapshot recorded
- ownership enforced

Audit:
- required events generated
- secrets never included

Tests should not rely on the real production Supabase database.

Use an isolated test database strategy.

---

# 48. Dependency Management

requirements.txt must explicitly contain direct runtime dependencies.

Do not rely on transitive dependencies for critical libraries.

Ensure explicit dependencies for:

- FastAPI
- Uvicorn
- SQLAlchemy
- psycopg
- Alembic
- Pydantic
- environment/settings handling
- password hashing backend
- JWT
- multipart/form handling
- ML dependencies when ML is implemented
- testing dependencies where appropriate

Pin or constrain versions deliberately.

---

# 49. Git Safety

Do not automatically push changes to GitHub.

Do not force push.

Do not rewrite Git history.

Do not commit secrets.

Before a significant implementation:

- inspect git status
- understand current branch
- keep changes scoped

After implementation:

- show changed files
- summarize changes
- run relevant tests
- report failures honestly
- show git diff/status

The human user decides when important checkpoints are committed/pushed unless explicitly instructing otherwise.

---

# 50. Codex Working Method

For substantial tasks:

1. Read AGENTS.md.
2. Inspect relevant existing code.
3. State/understand the implementation plan.
4. Identify migrations/security implications.
5. Implement the smallest coherent change.
6. Add/update tests.
7. Run tests.
8. Run appropriate static/import checks.
9. Inspect the diff.
10. Report exactly what changed.
11. Report unresolved issues.
12. Stop before unrelated work.

Do not opportunistically rewrite unrelated architecture.

Do not "clean up" large areas that are outside the requested task.

Do not claim success when tests fail.

---

# 51. Architecture Decision Rule

Do not independently make major product, clinical, security, billing, insurance, or ML architecture decisions when the requirements are ambiguous.

Examples requiring deliberate confirmation:

- changing patient-clinician relationship cardinality
- deciding real insurer behavior
- changing payment semantics
- choosing medical model features
- changing model thresholds
- changing medical risk classifications
- changing account lifecycle
- changing entitlement lifecycle
- deleting historical health information
- changing how clinician consent/access works
- replacing authentication technology
- introducing paid infrastructure

When uncertain:

STOP
→ describe the decision required
→ provide technically reasonable options
→ wait for direction

---

# 52. Medical Data Rule

Never fabricate medical data.

Never fabricate:

- glucose
- HbA1c
- blood pressure
- cholesterol
- creatinine
- family history
- medication
- diagnosis
- vital measurements

Missing required information must remain missing until supplied or legitimately retrieved from stored records.

Do not zero-fill missing clinical inputs unless the specific validated ML preprocessing pipeline explicitly defines that behavior and it is scientifically justified.

---

# 53. Privacy Rule

Apply data minimization.

Only collect/store data required for a defined RiskSense function.

Do not expose full patient health records merely because a role technically has database access.

Authorization should be resource-specific and purpose-aware where practical.

Sensitive responses should expose only fields needed by the requesting client/function.

---

# 54. Current Implementation Baseline

At the time these instructions were established, the repository already contains working/scaffolded implementations for:

- FastAPI application
- PostgreSQL/Supabase connection
- SQLAlchemy
- Alembic
- User model
- Patient model
- Clinician model
- HealthProfile model
- Vital model
- Subscription model
- Insurance model
- Model/ML registry model
- Prediction model
- Report model
- AuditLog model
- patient registration
- login
- `/auth/me`
- JWT authentication
- password hashing
- coarse RBAC
- patient health profile API
- patient vitals API
- patient subscription API
- patient insurance API

However, repository inspection found important incomplete/insecure behavior including:

- patients can manipulate authoritative subscription state
- self-declared insurance becomes active without verification
- no entitlement layer
- no patient-clinician relationship
- no functioning clinician API
- no functioning admin API
- no audit events written
- no ML implementation
- no prediction API
- no report API
- no automated tests
- no actual `/api/v1` URL prefix
- incomplete JWT error handling
- incomplete dependency declarations
- incomplete configuration centralization

Treat these as known baseline issues, but verify the code before changing them.

---

# 55. Implementation Priority

Unless specifically directed otherwise, prioritize work in this general order:

PHASE 1 — Foundation and access-control hardening
- establish tests
- fix JWT error handling
- secure subscription state
- secure insurance verification state
- implement entitlement architecture
- implement clinician identifiers
- implement patient-clinician relationships
- audit critical access operations

PHASE 2 — Data architecture
- patient/profile improvements
- structured model-relevant health data
- lab-result architecture
- measurement validation/provenance
- dashboard query foundations

PHASE 3 — Clinician functionality
- clinician profile
- linked patient APIs
- authorization
- clinician dashboard queries
- temporary Clinical Assessment Mode

PHASE 4 — ML lifecycle
- diabetes model integration
- heart-disease model integration
- model registry/versioning
- input contracts
- inference services
- prediction persistence
- explanations

PHASE 5 — Patient intelligence
- prediction result
- prediction history
- health trends
- reports
- dashboard aggregations

PHASE 6 — Admin
- user management
- audit log APIs
- security event views
- model management
- model activation/suspension

PHASE 7 — Website integration
- subscription activation
- renewal
- mock payment workflow
- insurance-provider workflow
- mock insurance verification
- clinician verification
- entitlement activation

PHASE 8 — Hardening
- API versioning
- CORS
- rate limiting
- configuration cleanup
- database constraints
- authorization review
- security testing
- integration testing
- API documentation
- deployment readiness

This order may be adjusted when dependencies justify it.

---

# 56. Definition of Done

A backend feature is not considered complete merely because an endpoint returns HTTP 200.

A feature is complete when appropriate:

- requirements are implemented
- authorization is enforced
- ownership is enforced
- input is validated
- database integrity is protected
- errors are handled safely
- audit events exist where required
- tests exist
- tests pass
- migration is reviewed when schema changes occur
- API contract is documented/understandable
- no secrets are exposed
- existing functionality has not been unintentionally broken

---

# 57. Final Product Principle

RiskSense AI should be engineered as a credible secure health decision-support prototype, not as a collection of disconnected demo endpoints.

Every new implementation should reinforce:

SECURITY
+
TRACEABILITY
+
DATA INTEGRITY
+
CLEAR AUTHORIZATION
+
MODEL REPRODUCIBILITY
+
MEDICAL SAFETY
+
MAINTAINABLE SOFTWARE ENGINEERING