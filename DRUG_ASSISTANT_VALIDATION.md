# Drug Assistant implementation and validation report

## 23 September 2026 final publication validation

The reviewer explicitly approved the 147 records in `expansion_review_manifest_v1.json`. Manifest verification and dry run each found exactly 147 eligible records, zero unrelated candidates, and zero validation failures. The batch attestation created a backup and changed all 147 to `REVIEWED`; the publisher accepted all 1,078 reviewed candidates, rejected zero, and regenerated the runtime store. The final store has 1,078 unique records across 90 medications, with 118 of 208 medications still lacking published evidence. Source counts are 877 MotherToBaby and 201 DailyMed. No candidate remains `REVIEW_REQUIRED` in this queue. The five fixed Drug Assistant artifacts were not modified.

The fresh-process Drug Assistant unit suite passed **244/244**. Python compilation, imports, OpenAPI generation (3.1.0; 59 paths), a repeat full-catalogue normalization (1,078 reviewed, zero pending, no duplicates), and `git diff --check` passed. Uvicorn started successfully without auto-reload; the Windows sandbox denied named-pipe access to its `--reload` process. Live patient login returned 200 and `POST /drug-assistant/chat` returned 201 with two cited bempedoic-acid claims. Live ADMIN login and `/admin/drug-assistant/status` returned 200 with 1,078 records, 90 medications, zero pending and 192 unresolved DailyMed products. Pair interaction and conversational follow-up checks still fail closed where pair-specific or topic-specific evidence is absent.

Final topic record counts: general information 137; indications 8; administration 15; adverse effects 15; warnings 15; contraindications 15; drug interactions 11; monitoring 54; pregnancy 493; lactation 133; fertility 172; reproductive potential 2; clinician discussion 8. The older expansion section below describes the state **before** this authorized publication.

## 23 September 2026 question and evidence expansion

The published baseline remains 931 `LIMITED_EVIDENCE` records for 89 of 208 medicines. A full-catalogue normalization pass created 147 additional `REVIEW_REQUIRED` records for eight medicines; none were attested or published. The candidate set now totals 1,078 across 90 medicines, while 118 have no candidate from the approved source operations. Runtime evidence remains unchanged: 119 medicines have no published evidence. The DailyMed resolver selected one SPL-verified bempedoic-acid label out of 193 originally unresolved operations; 189 cases were ambiguous, two search attempts failed, and one failed SPL metadata verification. These three failures remain unresolved, so the queue has 192 `PARTIAL` DailyMed operations, eight `NO_SOURCE`, and eight `SUCCESS`.

The 36 policy-defined intents were audited. The new routing table has 71 direct paraphrase examples, with follow-up, brand/generic, multi-medicine, ambiguity and unsupported-name checks. The complete database-free unit suite passed **244 tests**. Direct published-store checks returned `LIMITED_EVIDENCE` with claim and citation for metformin general, pregnancy and lactation questions; metformin side effects remained `INSUFFICIENT_EVIDENCE` with no claim or citation. A new safety regression verifies that general interaction text cannot answer a named medication pair. Python compilation, import, OpenAPI generation (3.1.0, 59 paths) and `git diff --check` passed. No Flutter file or database record was changed; Flutter analysis was unnecessary for this backend-only phase.

Topic counts below are records, with the number of distinct medicines in parentheses. “Insufficient” counts medicines without **published evidence for that topic**, including those with pending proposals. A pending proposal is not runtime eligible.

| Topic | Published | New pending | Insufficient medicines |
| --- | ---: | ---: | ---: |
| General information | 121 (82) | 16 (8) | 126 |
| Indications | 0 (0) | 8 (8) | 208 |
| Administration | 0 (0) | 15 (8) | 208 |
| Adverse effects | 7 (7) | 8 (8) | 201 |
| Warnings | 7 (7) | 8 (8) | 201 |
| Contraindications | 7 (7) | 8 (8) | 201 |
| Drug interactions | 5 (5) | 6 (6) | 203 |
| Monitoring | 0 (0) | 54 (7) | 208 |
| Pregnancy | 485 (88) | 8 (8) | 120 |
| Lactation | 126 (86) | 7 (7) | 122 |
| Fertility | 172 (82) | 0 (0) | 126 |
| Reproductive potential | 1 (1) | 1 (1) | 207 |

The top of this report records the latest validation. Older sections below are retained as historical snapshots; their earlier evidence counts and test results are superseded where they differ.

## 22 September 2026 normalization and review-workspace addendum

The evidence architecture is additive and review gated across all 208 catalogue medicines. All 416 queued source operations were attempted: 94 `SUCCESS`, 194 `PARTIAL`, 127 `NO_SOURCE`, and 1 `FAILED`. Normalization of existing snapshots generated 931 candidates for 89 medications (877 MotherToBaby, 54 DailyMed), with source excerpts, snapshot hashes, sections and exact provenance. The reviewer attested external review of those 931 records; all passed independent publication validation. The runtime matrix now has 89 medications with partial coverage and 119 entirely `INSUFFICIENT`.

The current normalization report is `app/ml/drug_assistant/evidence_work/normalization_report_v1.json`. It lists retrieval, review, topic, publication and per-medication source gaps. Metformin has nine MotherToBaby candidates covering general information, pregnancy, lactation and fertility. Its DailyMed operation remains ambiguous, so adverse effects, warnings, interactions and monitoring lack metformin candidates. Publication is deliberately separate from human review and rejects changed source snapshots.

The normalization, provider, pipeline and response-validation tests pass. Database-backed tests require the guarded local `TEST_DATABASE_URL`; they are not part of the evidence-workspace checks. Full API readiness is maintained in `BACKEND_API_READINESS.md`; the detailed review process is in `DRUG_EVIDENCE_WORKFLOW.md`.

### Evidence-expansion changes

Created `evidence_store.py`, `evidence_pipeline.py`, `source_adapters.py`, `response_validator.py`, the empty reviewed store, generated coverage matrix, resumable ingestion queue, golden dataset, provider/pipeline tests, API inventory, evidence workflow, frontend matrix and backend readiness report. Updated provider composition, interaction handling, deterministic follow-ups, response schema/service auditing, and the existing Drug Assistant/backend documentation. No database schema change or Alembic revision was needed in this phase.

The provider stack consists of `PublishedEvidenceProvider` for additive reviewed records, `ReviewedLocalProvider` for backward compatibility with a future deliberately reviewed fixed cache, and `CompositeProvider` for deterministic merging. DailyMed retrieval is opt-in, bounded, restartable and stores source snapshots only in a review workspace. Multiple labels require explicit product selection. MotherToBaby HTML snapshots are also present in the review workspace and are normalized into pending candidates.

### Representative behavior

- Current real store, “Can I take metformin while pregnant?”: `INSUFFICIENT_EVIDENCE`, no claim and no fabricated citation.
- Synthetic reviewed test fixture, metformin/atorvastatin interaction: `SOURCE_SUPPORTED`, one claim mapped to one retrieved source. The text is explicitly synthetic and never published into the runtime store.
- Synthetic conflicting fixtures: `CONFLICTING_EVIDENCE`; both reviewed records remain visible and neither is selected as the preferred conclusion.
- Current active-medication interaction context: each unresolved pair is labelled unavailable with an explicit statement that missing evidence does not mean no interaction exists.
- “What are atorvastatin's side effects?” followed by “Can I take it while pregnant?” retains atorvastatin within that authorized session. A pronoun after multiple medicines requests clarification.
- “I took 40 tablets and feel sick”: urgent routing runs before medication resolution and ordinary evidence retrieval.

### Remaining evidence limitations

The eligible published store contains 931 `LIMITED_EVIDENCE` records. Human product/formulation selection remains unresolved for 193 DailyMed operations, and future evidence still requires external review and publication checks. A medication appearing in the catalogue alone does not make a clinical response source supported. The database-free regression suite passed 163 tests after publication.

Date: 17 September 2026. This report covers the Drug & Pregnancy Information Assistant work, including the resumed session. It distinguishes automated tests from manual checks against the configured development database.

## Outcome

The current 208-drug catalogue is usable through authenticated APIs and persistent conversations. All supplied clinical cache entries remain unreviewed placeholders. The implemented behavior correctly returns evidence-limited responses for those entries; this is not a populated or clinically validated medication knowledge base.

No external LLM, paid service, scraping integration, retraining, or artifact rewriting was introduced. Existing Heart Disease and Diabetes inference remained operational in the real development request flow.

## Architecture and contracts

- Fixed-artifact runtime: all five JSON files are checked against pinned SHA-256 values, parsed and semantically validated, then cached as recursively immutable mappings.
- Resolver: exact normalized generic/alias matching, word boundaries, combination-name precedence, explicit ambiguity and unsupported-name behavior. No fuzzy matching or pill-appearance identification.
- Intent router: deterministic English rules for all 36 supplied intents; urgent categories run first.
- Knowledge provider: reviewed local cache adapter behind `DrugKnowledgeProvider`. Non-null evidence requires review state, verification timestamp, revision, content hash and authoritative drug-specific HTTPS provenance. Section-level insufficient/uncached evidence cannot be overridden by non-null text.
- Composer: returns structured, source-cited excerpts when eligible, otherwise an explicit evidence limitation. Current files generate no drug-specific clinical claims. No prescription, dose modification, fetal-outcome prediction or safety conclusion is generated.
- Services: authorize patient resources, select minimal relevant context, serialize turns using row locks, persist ordered message pairs/state/audits atomically, and provide medication CRUD.
- APIs: reuse existing authentication, dependency injection and `/api/v1` alias pattern. New tags are Drug Assistant and Patient Medications. Chat success, including evidence-limited answers, is HTTP 201.

Full API and Swagger examples are in `DRUG_ASSISTANT.md`.

## Schema and migration

Created and applied revision `c83f20a6d912`, following `b72e9a61c403`.

New tables/models:

- `drug_chat_sessions` / `DrugChatSession`: patient, initiating actor, title, status, safe state, sequence counter, timestamps and closure.
- `drug_chat_messages` / `DrugChatMessage`: session, actor, ordered role/content/response, intent, resolved IDs, evidence status, relevant context snapshot, source/artifact provenance, urgent classification and timestamp.
- `patient_medications` / `PatientMedication`: patient, entered display name, optional supported catalogue ID, optional dose/unit/frequency/route/reason/prescriber, active state, dates and timestamps.

Added nullable health-profile fields: `pregnancy_status`, `estimated_due_date`, `pregnancy_context_updated_at`, `breastfeeding_status`, `infant_date_of_birth`, `infant_premature`. Existing profile endpoints accept the patient-entered fields; the update timestamp is server-controlled. Registration remains unchanged. Due-date/infant-date and merged-state checks are implemented. Gestational age is not stored as a redundant profile number.

Legacy `health_profiles.current_medications` text is retained without attempted automatic parsing. Structured medications coexist with it. Medication DELETE deactivates rather than deletes history. Clinicians have authorized linked read access; writes are patient-owned.

The development upgrade was executed through normal Alembic. Before/after counts for all existing clinical/account tables matched. Existing profile height, weight, waist and medication text matched. New reproductive status fields remained null. No reset or downgrade was performed on development data.

Isolated clean-database, legacy-preservation, constraint/FK/index and downgrade tests are implemented but **not run** because `TEST_DATABASE_URL` is unavailable. The new migration test seeds representative patient, profile, clinician/link, subscription/entitlement, vital, laboratory and prediction records and checks their preservation. Downgrade would discard new conversations, structured medications and reproductive fields and must be treated as destructive.

## Authorization, privacy and auditing

- Every API request validates the real current user.
- Patients access only their own patient/session/medication resources.
- Clinicians require current approval, active user, explicit patient ID and an active patient link.
- ADMIN role alone does not authorize clinical chat or medication access.
- The supplied Drug Assistant policy's entitlement requirement is enforced for both patient and clinician patient-specific chat/history/session operations. Medication recording retains the health-profile onboarding access policy.
- Non-disclosing resource failures use 404; role/entitlement failures use 403.
- Conversation context is isolated to its authorized patient/session. Pregnancy is never inferred from demographics or medication names. Explicit conversation reports do not silently update the health profile.
- Common credential and token patterns are rejected. Raw conversation text is confined to conversation tables, not generic audit details.
- Message rows, session updates and success audit events commit atomically. Session locking and unique sequence positions preserve ordering.

Audit actions: `DRUG_CHAT_SESSION_CREATED`, `DRUG_CHAT_SESSION_CLOSED`, `DRUG_CHAT_MESSAGE_CREATED`, `DRUG_KNOWLEDGE_RETRIEVED`, `DRUG_CHAT_URGENT_ROUTE`, `DRUG_CHAT_ACCESS_DENIED`, `PATIENT_MEDICATION_CREATED`, `PATIENT_MEDICATION_UPDATED`, `PATIENT_MEDICATION_DEACTIVATED`, `PREGNANCY_CONTEXT_UPDATED`.

Urgent messages bypass ordinary clinical retrieval. Urgent state persists until an explicit report of contacting emergency/poison services or being with a clinician/in hospital. That statement is not treated as medical proof of recovery. General emergency guidance has separate provenance and does not claim drug-specific evidence.

## Automated results

Final collection: **283 tests**.

| Result | Count |
| --- | ---: |
| Passed in database-independent run | 223 |
| Failed in final executed subset | 0 |
| Skipped in final executed subset | 0 |
| Blocked / not run without isolated PostgreSQL | 60 |

The database-free run explicitly disabled all SQLAlchemy connections and `.env` loading. A nonconnecting placeholder configuration was used only for importing ORM modules; no database operations were performed. The regular full-suite command was separately attempted and refused by the unchanged guard because `TEST_DATABASE_URL` was absent. The suite was not redirected to development.

Blocked modules:

| Module | Cases |
| --- | ---: |
| `tests/test_database_safety.py` | 1 |
| `tests/test_diabetes_integration.py` | 17 |
| `tests/test_diabetes_migrations.py` | 1 |
| `tests/test_drug_assistant_integration.py` | 12 |
| `tests/test_drug_assistant_migrations.py` | 1 |
| `tests/test_heart_disease_integration.py` | 20 |
| `tests/test_migrations.py` | 3 |
| `tests/test_security_integration.py` | 5 |

New Drug Assistant coverage consists of 94 database-free artifact/resolution/intent/provider/schema tests, 4 context tests, 12 PostgreSQL integration cases and 1 migration case. Existing Heart Disease runtime tests (59), Diabetes runtime/BMI tests (57) and the existing database-independent auth/schema/model tests passed.

Other checks: Python compilation passed; FastAPI imports passed; SQLAlchemy mapper configuration passed; OpenAPI generation passed with 53 documented paths; all five supplied artifact hashes passed; copied/original artifact byte comparisons passed; `git diff --check` passed. Existing TestClient emits a Starlette/httpx deprecation warning; Git emits LF/CRLF notices. Neither was hidden or described as a clinical validation result.

## Real development end-to-end results

Used the existing development patient with a real `/auth/login` response and returned Bearer token, no dependency overrides or injected JWT. Login returned HTTP 200. Real ADMIN login was used to verify clinical-chat denial, not to bypass the route.

Session: `77a775e5-1a57-42dc-9bca-1f41e37b6a36`.

| Case | Input category | HTTP | Intent | Evidence / urgent |
| --- | --- | ---: | --- | --- |
| A | What is metformin? | 201 | DRUG_GENERAL | INSUFFICIENT_EVIDENCE |
| B | Metformin in pregnancy | 201 | DRUG_PREGNANCY | INSUFFICIENT_EVIDENCE |
| C | Took metformin before knowing of pregnancy | 201 | DRUG_PREGNANCY_EXPOSURE | INSUFFICIENT_EVIDENCE |
| D | Breastfeeding with metformin | 201 | DRUG_LACTATION | INSUFFICIENT_EVIDENCE |
| E | Atorvastatin side effects | 201 | DRUG_SIDE_EFFECT | INSUFFICIENT_EVIDENCE |
| F | Atorvastatin and other medications | 201 | DRUG_INTERACTION | INSUFFICIENT_EVIDENCE |
| G | What to discuss with doctor about prior medicine | 201 | DRUG_CLINICIAN_DISCUSSION | INSUFFICIENT_EVIDENCE |
| H | Unsupported medication | 201 | UNSUPPORTED_DRUG | UNSUPPORTED_DRUG |
| I | Small blue pill | 201 | AMBIGUOUS_DRUG | INSUFFICIENT_EVIDENCE |
| J | Took 40 tablets and feels sick | 201 | EMERGENCY_OR_URGENT | urgent=true |

Verified session, message, resolved intent/IDs, evidence, source/artifact provenance and per-turn audit persistence in PostgreSQL. No drug-specific claims or fabricated citations were returned. A follow-up ordinary medication question correctly retained urgent routing; an explicit synthetic report of being with a doctor then allowed ordinary evidence-limited information. The test session was closed and further chat returned 409; its 24 message rows remain readable through authenticated history.

Additional real checks: unauthenticated chat returned 401; cross-patient request returned 404; ADMIN clinical chat and medication read returned 403; catalogue listing returned all 208 records; source endpoint showed no reviewed clinical sources; `/api/v1` session alias worked.

Created one explicitly labelled **inactive synthetic** medication CRUD record, `9741cc3e-e0a7-4e8e-9914-3eae9dae3390`. Create/read/update/deactivate succeeded; repeated inactive deactivation became idempotent after audit correction. No dose, prescription or active medication was invented for the patient. Existing pregnancy/breastfeeding profile statuses remained null.

Regression through the real authenticated risk-analysis API:

- Heart Disease: HTTP 201, score `0.506283882324414`, prediction `db28046b-7f2a-4263-8c87-8cecb3331d8f`.
- Diabetes: HTTP 201, score `0.410235721429783`, prediction `c0106c17-37c9-416f-bc3b-343cf85b1712`.

These manual checks are not substitutes for the 60 blocked automated PostgreSQL cases. Clinician-link, expiry, rollback and migration downgrade coverage is implemented but not claimed as executed in the full integration suite.

## Defects found and fixed

1. Urgent rules initially missed the phrase “severe medication reaction”; the matcher was corrected and tested.
2. Reviewed source metadata plus non-null text could have overridden a section explicitly marked `NOT_CACHED`/`INSUFFICIENT_EVIDENCE`; provider selection now respects those section states.
3. Editing an already inactive medication initially emitted a deactivation event; state transitions now choose the correct update action, and an unchanged repeated deactivation is a no-op. Existing audit history was retained.
4. Explicit “just found out I'm pregnant” context now recognizes the contraction; hypothetical statements remain unrecorded as facts. Lactation responses omit irrelevant infant data when breastfeeding is explicitly declined/not occurring.
5. Retrospective exposure statements now retain only reported exposure timing; they do not establish that the patient is currently pregnant. This correction does not rewrite the retained synthetic validation conversation.

## Files created for this task

```text
DRUG_ASSISTANT.md
DRUG_ASSISTANT_VALIDATION.md
alembic/versions/c83f20a6d912_drug_assistant.py
app/api/v1/drug_assistant.py
app/api/v1/patient_medications.py
app/ml/drug_assistant/runtime.py
app/ml/drug_assistant/resolver.py
app/ml/drug_assistant/intent.py
app/ml/drug_assistant/provider.py
app/ml/drug_assistant/composer.py
app/ml/drug_assistant/risksense_drug_assistant_model_v1.json (unchanged byte copy)
app/ml/drug_assistant/risksense_drug_assistant_model_v1_metadata.json (unchanged byte copy)
app/ml/drug_assistant/drug_knowledge_v1.json (unchanged byte copy)
app/ml/drug_assistant/drug_knowledge_v1_metadata.json (unchanged byte copy)
app/ml/drug_assistant/drug_assistant_policy_v1.json (unchanged byte copy)
app/models/drug_chat.py
app/models/patient_medication.py
app/schemas/drug_assistant.py
app/schemas/patient_medication.py
app/schemas/reproductive.py
app/services/clinical_access_service.py
app/services/drug_assistant_service.py
app/services/patient_medication_service.py
tests/unit/test_drug_assistant.py
tests/test_drug_assistant_context.py
tests/test_drug_assistant_integration.py
tests/test_drug_assistant_migrations.py
```

Modified during this task: `README.md`, `BACKEND_CONTEXT.md`, `app/db/models.py`, `app/main.py`, `app/models/health_profile.py`, `app/schemas/health.py`, `app/services/health_service.py`, and `tests/test_migrations.py` (expected new tables added without removing existing assertions). Prior uncommitted Diabetes changes were preserved.

## Remaining limitations

- Clinical evidence is still unpopulated. No claim of complete medication safety/interaction knowledge is made.
- No live authoritative retrieval exists; the provider boundary supports a future reviewed adapter.
- The English rule-based intent/urgent detector has bounded coverage and is not a validated clinical triage system.
- No arbitrary drug identification from images/appearance, prescribing, dosage selection or personalized suitability conclusions are supported.
- The isolated PostgreSQL suite still needs a valid guarded `TEST_DATABASE_URL`; missing configuration remains a blocker.
- Rate limiting, retention/deletion policy and broader production hardening require separate work. Sessions close without deleting history.
- Credentials were used only in ephemeral validation commands, not saved into source, test cases, `.env.example` or documentation.

No commit, push, reset, rebase or history rewrite was performed. The working tree retains both this work and the previous Diabetes work for manual review.

## Final Git state

Branch: `main`. Nothing staged. `git diff --stat` reports 12 tracked files changed,
244 insertions and 78 deletions; it excludes the untracked additions and includes
the pre-existing Diabetes changes. Exact `git status --short`:

```text
 M README.md
 M app/api/v1/admin.py
 M app/api/v1/intelligence.py
 M app/db/models.py
 M app/main.py
 M app/ml/heart_disease/runtime.py
 M app/models/health_profile.py
 M app/schemas/health.py
 M app/schemas/predictions.py
 M app/services/health_service.py
 M app/services/risk_analysis_service.py
 M tests/test_migrations.py
?? BACKEND_CONTEXT.md
?? DRUG_ASSISTANT.md
?? DRUG_ASSISTANT_VALIDATION.md
?? alembic/versions/b72e9a61c403_health_profile_waist.py
?? alembic/versions/c83f20a6d912_drug_assistant.py
?? app/api/v1/drug_assistant.py
?? app/api/v1/patient_medications.py
?? app/ml/common.py
?? app/ml/diabetes/
?? app/ml/drug_assistant/
?? app/ml/drug_response/
?? app/models/drug_chat.py
?? app/models/patient_medication.py
?? app/schemas/drug_assistant.py
?? app/schemas/patient_medication.py
?? app/schemas/reproductive.py
?? app/services/clinical_access_service.py
?? app/services/diabetes_service.py
?? app/services/drug_assistant_service.py
?? app/services/patient_medication_service.py
?? tests/test_diabetes.py
?? tests/test_diabetes_integration.py
?? tests/test_diabetes_migrations.py
?? tests/test_drug_assistant_context.py
?? tests/test_drug_assistant_integration.py
?? tests/test_drug_assistant_migrations.py
?? tests/unit/
```
