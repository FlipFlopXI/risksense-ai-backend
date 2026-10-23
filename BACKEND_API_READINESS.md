# RiskSense backend API readiness

Date: 18 September 2026

## Classification

**NOT YET FRONTEND-READY.** The missing frontend contracts are implemented, database-free validation passes, and all 416 Drug Assistant source operations were processed. The additive migration and controlled development-database smoke tests were not executed because automatic approval review rejected access to the configured database. Clinical evidence publication also remains correctly gated on human review.

The generated [endpoint inventory](BACKEND_ENDPOINT_INVENTORY.json) contains 74 canonical operations and 73 `/api/v1` compatibility aliases (147 application operations), with no duplicate operation IDs.

| Inventory state | Canonical operations | Meaning |
| --- | ---: | --- |
| WORKING | 18 | Database-free regression passed or a previously authorized development flow was exercised |
| UNTESTED | 55 | Contract is registered; current database validation is blocked |
| INTENTIONALLY UNAVAILABLE | 1 | Temporary clinician assessment returns 503 because no validated model exists |

## Implemented frontend contracts

- Authentication now issues short-lived access and rotating refresh tokens. `/auth/refresh` rotates the stored refresh-token JTI hash; `/auth/logout` revokes the session; access tokens carrying a session ID are rejected after revocation.
- `BodyMeasurement` preserves dated height, weight and waist measurements. `/health/body-measurements` exposes history, and `/health/trends` returns recorded BP, heart rate, fasting glucose, total cholesterol, weight and derived historical BMI. BMI is derived only when a recorded height exists at or before the weight measurement.
- `/patients/me/clinician` returns the patient's active approved clinician relationship with a minimal safe clinician identity.
- Reports support POST generation, list/detail retrieval and `/reports/{id}/pdf`. Prediction ownership is validated, linked clinicians use the existing authorization service, ADMIN has no implicit clinical access, and downloads are audited.
- `/admin/drug-assistant/status` exposes operational catalogue, intent, provider, evidence, queue and coverage counts without patient content.

## Security and data integrity

Public registration still creates PATIENT accounts only. Patients cannot activate subscriptions, approve insurance, or grant relationships. Risk analysis and patient-specific Drug Assistant requests require an effective ACTIVE, non-expired entitlement. Clinician reads require an approved clinician and ACTIVE relationship. Report access follows the same patient/linked-clinician boundary. Audit metadata excludes passwords, tokens, chat text and raw reproductive or medication payloads.

Migration `d54b8c21e7f0` is additive over `c83f20a6d912`: it creates `auth_sessions` and `body_measurements`, indexes their authorization/time access paths, and backfills one baseline body measurement from each existing profile that has recorded measurements. Its downgrade removes only these new tables. It was inspected and imported but was not applied to a database in this run.

## Drug evidence processing

| Source | SUCCESS | PARTIAL | NO_SOURCE | FAILED |
| --- | ---: | ---: | ---: | ---: |
| DailyMed | 7 | 193 | 8 | 0 |
| MotherToBaby | 87 | 1 | 119 | 1 |
| Total | 94 | 194 | 127 | 1 |

The remaining failure is the MotherToBaby retrieval for `nortriptyline` (`SOURCE_RETRIEVAL_FAILED`). All snapshots remain unreviewed. The published store therefore contains zero eligible reviewed records and coverage correctly remains 208 insufficient. The review workbench supports queue inspection, deterministic draft creation, approval, limited-evidence publication and rejection with reviewer attribution and content-hash validation.

## Validation result

- 301 tests collected.
- 155 database-free unit tests passed.
- The normal suite correctly refused to start without a confirmed isolated `risksense_test`; 146 database-backed/non-unit tests were not executed in this run.
- The generated validation PDF was rendered and visually inspected as one clean A4 page.

The database remains the release blocker. The configured development-database identity check, migration application and controlled smoke tests require explicit approval after the automatic reviewer rejected the attempted read-only connection due to an earlier instruction that prohibited `DATABASE_URL` and Supabase access.
