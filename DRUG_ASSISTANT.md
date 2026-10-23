# Drug & Pregnancy Information Assistant

RiskSense Drug Assistant provides educational/source-grounded medication information and is not a diagnosis, prescription, or replacement for a clinician/pharmacist. It has not been clinically validated.

## Current evidence and scope

The supplied version 1 catalogue contains 208 medications across 16 therapeutic groups and 36 routing intents. All current clinical cache records are unreviewed placeholders. Recognition of a supported drug does **not** mean RiskSense has evidence to answer a clinical question about it.

The fixed cache is not a source of clinical claims. The separate published store currently provides 931 externally reviewed `LIMITED_EVIDENCE` records for 89 medicines. Other topics and medicines return `INSUFFICIENT_EVIDENCE` unless eligible reviewed evidence exists. Unknown medication names return `UNSUPPORTED_DRUG`; unclear names or appearance-only descriptions request clarification.

This is a functioning evidence-limited assistant, not a completed clinical knowledge base. Runtime does not scrape sources, use an LLM, or require API keys. An additive reviewed evidence store and ingestion/review workflow now extend `DrugKnowledgeProvider` without modifying the five supplied artifacts. See `DRUG_EVIDENCE_WORKFLOW.md`.

The generated coverage matrix processes all 208 catalogue entries. The published store now contains 1,078 externally reviewed records for 90 medications; 118 medications remain entirely `INSUFFICIENT`. Published records retain `LIMITED_EVIDENCE` status. See `DRUG_ASSISTANT_VALIDATION.md` for the current topic counts and remaining gaps.

The September question-coverage expansion added 147 DailyMed candidates. After explicit external review and manifest-scoped attestation, all 147 passed independent publication validation and became runtime eligible. See `DRUG_ASSISTANT_QUESTION_COVERAGE.md`, `DAILYMED_PRODUCT_RESOLUTION_REPORT.md`, `DRUG_ASSISTANT_NEW_EVIDENCE_REVIEW.md`, and the per-medicine source gap inventory `DRUG_ASSISTANT_UNCOVERED_MEDICATIONS.md`. A named interaction pair requires evidence explicitly linking that pair; a general interaction section does not establish it.

## Architecture and fixed artifacts

The fixed runtime directory is `app/ml/drug_assistant/`:

| File | SHA-256 |
| --- | --- |
| `risksense_drug_assistant_model_v1.json` | `204b226dd6dadec6395af07b8e6bc4accadd886de8dcf019db1a94f47bb397e8` |
| `risksense_drug_assistant_model_v1_metadata.json` | `445695b68e7bbd0859b8d1daa2fa96820dd534031bbf1815e545df9ae3e8c825` |
| `drug_knowledge_v1.json` | `87286993cfe138528babfb7e313f7b39ae4ba40abe87b48715cdb3c1107b2ceb` |
| `drug_knowledge_v1_metadata.json` | `5d965635f61dabb904a892b30e9c4deb0eeb63125c0459a70d8f913fb2ae1035` |
| `drug_assistant_policy_v1.json` | `6efcbedd976b3634eec6b7c47ae2787ca9d04b35eb743aafeb0c2e49352e2876` |

The supplied files were found in `app/ml/drug_response/` and copied byte-for-byte into the requested runtime directory. The originals are retained. Neither copy is rewritten by application code.

`runtime.py` verifies all five pinned hashes, JSON/schema/version compatibility, model and knowledge metadata hashes, counts, unique IDs, normalized aliases, intents, pregnancy sections, evidence states, source hierarchy and required policy switches. It caches recursively immutable data once per worker under a lock. It never holds patient or conversational state. Restart workers after a deliberately reviewed artifact deployment. Runtime failures return sanitized 503 errors.

`resolver.py` normalizes case, whitespace and punctuation, uses token boundaries and supplied aliases, and avoids fuzzy matching. It supports paracetamol/acetaminophen, salbutamol/albuterol, glibenclamide/glyburide, isophane insulin/NPH insulin and TMP-SMX/co-trimoxazole. Supported combination names take precedence over contained component names. Explicit pronouns may refer to authorized context within the same persisted session. An unsupported or ambiguous turn clears the prior medication rather than silently assigning it to a new unknown name.

`intent.py` implements deterministic, ordered rules. Supported categories cover general information, indications/class/identification/aliases; pregnancy, exposure, timing, evidence and registries; lactation; reproductive potential, fertility, contraception and pregnancy testing; adverse effects, warnings, contraindications, interactions including food/alcohol, monitoring, storage/formulation, heart/diabetes/patient context, comparison, sources, evidence strength, clinician discussion and missed doses. Unknown intents remain out of scope. This is a bounded rule-based English router, not unrestricted natural-language understanding.

`provider.py` defines `DrugKnowledgeProvider`, compatibility `ReviewedLocalProvider`, additive `PublishedEvidenceProvider`, and `CompositeProvider`. Both evidence paths read only fields/topics relevant to the resolved intent. Non-null clinical content is eligible only after explicit review with timestamps, revision and integrity metadata, and drug-specific HTTPS provenance on an approved authoritative domain. A homepage/retrieval template is not a clinical citation. Narrow food, alcohol and missed-dose answers require correspondingly specific reviewed fields rather than guessing from general interaction text.

`evidence_store.py` validates the versioned evidence schema, approved domains, catalogue IDs, pair mappings, review state and canonical content hash. A material content change invalidates the reviewed hash. `response_validator.py` maps every claim to a retrieved citation, resolved medicine and intent domain; invalid output is stripped to an evidence-limited response and persisted turns audit `DRUG_RESPONSE_VALIDATION_FAILED`.

`evidence_pipeline.py` creates a restartable 416-operation queue, validates review packages, publishes only `REVIEWED` records, and regenerates `evidence_coverage_v1.json` directly from the eligible store. `evidence_normalization.py` extracts source sections into separate `REVIEW_REQUIRED` candidate packages without selecting ambiguous products or inferring conclusions. `scripts.review_drug_evidence` supports explicit individual review; `scripts.publish_drug_evidence` publishes approved records. Automation may retrieve and structure a proposal but cannot confer medical review.

`composer.py` formats reviewed excerpts with provenance or an evidence-limited explanation. It never independently recommends starting, stopping, switching or changing medication. It does not infer interactions from therapeutic group membership. It never converts null/empty content into “safe”, “no risk” or “no interaction”.

## Evidence states

| State | Meaning |
| --- | --- |
| `SOURCE_SUPPORTED` | Requested content is present in a reviewed cache with source provenance; does not establish individual suitability |
| `LIMITED_EVIDENCE` | Reviewed content exists but the requested information is incomplete or explicitly limited |
| `INSUFFICIENT_EVIDENCE` | No eligible reviewed content supports the requested conclusion |
| `CONFLICTING_EVIDENCE` | The reviewed section explicitly records conflicting evidence; no conflict is silently resolved |
| `UNSUPPORTED_DRUG` | The medication is outside the supported catalogue |

## Pregnancy and patient context

The assistant follows the supplied FDA label structure: 8.1 Pregnancy, 8.2 Lactation and 8.3 Females and Males of Reproductive Potential. It does not assign A/B/C/D/X or binary safe/unsafe categories. See the [FDA PLLR explanation](https://www.fda.gov/drugs/labeling-information-drug-products/questions-and-answers-pregnancy-and-lactation-labeling-rule).

Optional fields on the existing `HealthProfile`:

- `pregnancy_status`: `NOT_PREGNANT`, `PREGNANT`, `POSSIBLY_PREGNANT`, `TRYING_TO_CONCEIVE`, `POSTPARTUM`, `PREFER_NOT_TO_SAY`, `UNKNOWN`, or null
- `estimated_due_date`: optional date
- `pregnancy_context_updated_at`: server-controlled timestamp
- `breastfeeding_status`: `YES`, `NO`, `PREFER_NOT_TO_SAY`, `UNKNOWN`, or null
- `infant_date_of_birth`: optional non-future date
- `infant_premature`: optional boolean

These fields can be set through existing patient `POST /health/profile` and partial `PUT /health/profile`. Registration requirements are unchanged. Updates validate the merged profile: changing to a non-pregnant/unknown status requires explicitly clearing an existing due date. Dates before 1900, infant dates in the future and due dates over a year ahead are rejected. Responses do not revalidate historical due dates as new writes.

Pregnancy is never inferred from age, gender, diagnosis, medications or another session. Explicit first-person reports may be retained in the same conversation with source and timestamp. Hypothetical questions are not profile facts. Chat does not silently write these reports into the health profile. Reported gestational weeks are an exposure-time statement with a report timestamp, not a new permanent profile age; the profile stores only the due date. No gestational week is guessed from demographics.

Only intent-relevant context is selected: pregnancy/timing for pregnancy questions; breastfeeding and infant context for lactation; actual recorded conditions for condition questions; active structured medications and labelled legacy medication text for interactions/patient-context questions. The response exposes the material context considered without declaring medication suitability. Vitals, labs and full medical history are not indiscriminately copied into conversations; no evidence-backed need for them exists in the current cache.

## Authorization and persistence

Every request authenticates independently. Patients access their own resources. Approved, active clinicians must provide `patient_id` and have an active `PatientClinician` link. ADMIN role alone does not permit clinical chat or medication access. Inaccessible patient/session resources use non-disclosing 404 responses. Patients must not submit role, entitlement, raw evidence or source overrides.

The supplied assistant policy explicitly requires effective entitlement for patient-specific chat. This is enforced for both patient and clinician chat, session listings, history and session closure. Medication management remains available under existing health-profile ownership rules without a product-entitlement gate so patients can record onboarding data. Clinicians have linked read access; medication writes are patient-owned. The nonclinical catalogue requires an active patient or approved clinician account.

`drug_chat_sessions` stores patient ownership, initiating actor, title, open/closed status, timestamps, safe conversation state and a sequence counter. `drug_chat_messages` stores ordered user/assistant messages, actor, intent, drug IDs, evidence status, the material context snapshot, source/artifact provenance and urgent classification. No messages are stored in `predictions` or the ML model registry.

Each turn locks its session and commits both message rows, state and audit events atomically. A unique `(session_id, sequence)` constraint prevents duplicate positions. Closing a session retains history and blocks further messages. History is paginated; use `after_sequence` to fetch subsequent messages. Common credential/token patterns are rejected before persistence; users must never put secrets into clinical free text.

Audit events include `DRUG_CHAT_SESSION_CREATED`, `DRUG_CHAT_SESSION_CLOSED`, `DRUG_CHAT_MESSAGE_CREATED`, `DRUG_KNOWLEDGE_RETRIEVED`, `DRUG_CHAT_URGENT_ROUTE`, `DRUG_CHAT_ACCESS_DENIED`, `PATIENT_MEDICATION_CREATED`, `PATIENT_MEDICATION_UPDATED`, `PATIENT_MEDICATION_DEACTIVATED` and `PREGNANCY_CONTEXT_UPDATED`. Generic audit details do not contain conversation text, medication lists or reproductive information. `DRUG_KNOWLEDGE_RETRIEVED` records an evidence lookup, including an unsuccessful/insufficient result; it does not claim clinical evidence exists.

## Urgent routing

Suspected overdose, breathing difficulty, severe allergic reactions, loss of consciousness, severe bleeding/reactions, immediate danger and severe pregnancy-related symptom phrases route before drug resolution or clinical retrieval. Responses set `urgent: true`, provide brief instructions to seek local emergency/poison-service help and persist the urgent event. No guessed regional emergency number is supplied.

Urgent state remains in the session until the user explicitly reports contacting emergency/poison services or being with a doctor/paramedic/in hospital. Such a report does not establish clinical recovery. The rule-based detector is not a validated emergency triage tool; users should not rely on absence of an urgent flag as evidence of safety. General urgent-help guidance is based on [NHS poisoning guidance](https://www.nhs.uk/conditions/poisoning/), separately from medication evidence sources.

## API

All routes also have `/api/v1` compatibility aliases. Swagger shows unversioned routes.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/drug-assistant/sessions` | Create an optional titled session |
| GET | `/drug-assistant/sessions` | List authorized sessions (`limit`, `offset`) |
| GET | `/drug-assistant/sessions/{id}` | Read a session |
| PATCH | `/drug-assistant/sessions/{id}` | Close with `{"status":"CLOSED"}` |
| GET | `/drug-assistant/sessions/{id}/messages` | History (`limit`, `after_sequence`) |
| POST | `/drug-assistant/chat` | Send a message; create a session if omitted |
| GET | `/drug-assistant/drugs` | Search catalogue (`q`, `limit`, `offset`) |
| GET | `/drug-assistant/drugs/{drug_id}` | Safe medication identity |
| GET | `/drug-assistant/drugs/{drug_id}/sources` | Reviewed citations and separately labelled retrieval mappings |
| POST / GET | `/patient-medications` | Create / list patient medication records |
| GET / PATCH / DELETE | `/patient-medications/{id}` | Read / update / deactivate (retain history) |

Clinicians pass `patient_id` in create/chat bodies and as a query parameter for reads. Cross-patient IDs cannot change session ownership. Chat success is HTTP 201, including unsupported/ambiguous/insufficient evidence states. Missing authentication is 401; role/entitlement failure 403; inaccessible resources 404; closed sessions 409; validation 422; sanitized runtime/storage failures 503.

Chat responses include session/message IDs, intent, one `drug` or multiple `drugs`, resolution status, summary, evidence status, source-cited claims, material patient context, pregnancy/lactation/reproductive/general sections, warnings, interactions, monitoring, discussion points, safety message, urgent flag/category and generation timestamp.

`patient_medications` coexists with `health_profiles.current_medications`, which is an unstructured string. No legacy text is parsed, deleted or represented as a verified drug identity. A medication record stores display name, optional catalogue ID, patient-entered dose/unit/frequency/route/reason/prescriber, active state, start/end dates and timestamps. Storage is not a RiskSense recommendation. Unsupported names remain storable with null catalogue ID. Identity resolution is exact and server-controlled.

## Migration and validation

Revision `c83f20a6d912` follows `b72e9a61c403`. It adds the three tables, optional profile columns, status/date/name/sequence constraints, foreign keys and patient/history indexes. Upgrade preserves existing records and medication text. Downgrade removes all new conversation/medication records and reproductive fields; it must never be run casually on development data.

Tests cover fixed-artifact integrity and policy compatibility, aliases and ambiguity, all intent families, urgent precedence, null evidence, reviewed synthetic cache/provenance, optional profile/medication validation, role/ownership/link/entitlement authorization, persistence, atomic audit failure, medication CRUD and migration preservation. Complete PostgreSQL testing uses only the guarded local `risksense_test` database. If it is absent, report those tests as blocked.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit --confcutdir=tests/unit -q
# Only with the guarded isolated PostgreSQL database configured:
.\.venv\Scripts\python.exe -m pytest -q
```

## Manual Swagger workflow

Start Uvicorn, open `/docs`, and use **Authorize** with the existing account email as username and its password. Swagger obtains a real token from `/auth/login`. Do not paste passwords or tokens into chat.

Create a session through `POST /drug-assistant/sessions` with `{}`. Copy its `id`, then send:

```json
{
  "session_id": "<returned session UUID>",
  "message": "What is metformin?"
}
```

Use `POST /drug-assistant/chat` for each following question:

1. `Can I take metformin while pregnant?`
2. `I took metformin before I knew I was pregnant.`
3. `Can I breastfeed while taking metformin?`
4. `What are atorvastatin's side effects?`
5. `Does atorvastatin interact with my other medications?`
6. `What should I ask my doctor about this medicine?`
7. `What is xyzunsupportedmedicine?`
8. `What is the small blue pill?`
9. `I took 40 tablets and I feel sick.`

Expect evidence-limited responses for currently uncached clinical content, unsupported/ambiguous identity responses where appropriate, and an urgent response for the last message. Retrieve `GET /drug-assistant/sessions/{id}/messages` to inspect the persisted history. These are synthetic development prompts; they are not clinical facts about the test patient.
