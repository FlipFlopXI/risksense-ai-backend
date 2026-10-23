# Frontend API integration matrix

Generated from the application contract on 18 September 2026. Canonical paths are shown; router endpoints also have hidden `/api/v1` compatibility aliases. `BLOCKED` means the implementation exists but its controlled database smoke test could not run in this phase.

| Frontend role | Screen | Operation | Method | Endpoint | Auth | Entitlement | Relationship | Request schema | Response schema | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Public | Sign up | Register patient | POST | `/auth/register` | No | No | No | `UserRegisterRequest` | `UserResponse` | READY |
| Public | Sign in | Login | POST | `/auth/login` | No | No | No | OAuth2 form | `TokenResponse` | BLOCKED |
| Any | Session | Refresh access | POST | `/auth/refresh` | Refresh token | No | No | `RefreshTokenRequest` | `TokenResponse` | BLOCKED |
| Any | Session | Logout/revoke | POST | `/auth/logout` | Bearer | No | No | `LogoutRequest` | 204 | BLOCKED |
| Any | Account | Current user | GET | `/auth/me` | Bearer | No | No | none | `UserResponse` | BLOCKED |
| PATIENT | Profile | Read/update identity | GET/PATCH | `/patients/me` | Bearer | No | No | `PatientUpdateRequest` | `PatientResponse` | BLOCKED |
| PATIENT | Health profile | Create/read/update | POST/GET/PUT | `/health/profile` | Bearer | No | No | health profile schemas | health profile schema | BLOCKED |
| PATIENT | Body history | List measurements | GET | `/health/body-measurements` | Bearer | No | No | query | `BodyMeasurementResponse[]` | BLOCKED |
| PATIENT | Vitals | Add/list/latest/batch | POST/GET | `/health/vitals/*` | Bearer | No | No | vital schemas | vital schemas | BLOCKED |
| PATIENT | Laboratory | Add/list | POST/GET | `/health/labs/` | Bearer | No | No | lab schemas | lab schemas | BLOCKED |
| PATIENT | Dashboard | Summary | GET | `/dashboard` | Bearer | No | No | none | `DashboardResponse` | BLOCKED |
| PATIENT | Trends | Longitudinal health series | GET | `/health/trends` | Bearer | No | No | query | trend object | BLOCKED |
| PATIENT | Risk analysis | Heart/Diabetes analysis | POST | `/risk-analysis` | Bearer | ACTIVE | Own patient | `RiskAnalysisRequest` | `PredictionResponse` | BLOCKED |
| CLINICIAN | Risk analysis | Linked-patient analysis | POST | `/risk-analysis` | Bearer | Patient ACTIVE | ACTIVE approved link | `RiskAnalysisRequest` | `PredictionResponse` | BLOCKED |
| PATIENT | Predictions | List/detail | GET | `/predictions*` | Bearer | No | Own patient | none | prediction schemas | BLOCKED |
| PATIENT | Reports | Generate/list/detail | POST/GET | `/reports*` | Bearer | No | Own patient | `ReportGenerateRequest` | report schemas | BLOCKED |
| PATIENT | Reports | Download PDF | GET | `/reports/{id}/pdf` | Bearer | No | Own patient | none | PDF | BLOCKED |
| CLINICIAN | Reports | Generate/read/download | POST/GET | `/reports*` | Bearer | No | ACTIVE approved link | report schemas | report/PDF | BLOCKED |
| PATIENT | Medications | CRUD | GET/POST/PATCH/DELETE | `/patient-medications*` | Bearer | No | Own patient | medication schemas | medication schemas | BLOCKED |
| PATIENT | Drug Assistant | Sessions/chat/history | POST/GET/PATCH | `/drug-assistant/*` | Bearer | ACTIVE | Own patient | assistant schemas | assistant schemas | BLOCKED |
| CLINICIAN | Drug Assistant | Linked-patient chat | POST/GET/PATCH | `/drug-assistant/*` | Bearer | Patient ACTIVE | ACTIVE approved link | assistant schemas | assistant schemas | BLOCKED |
| PATIENT/CLINICIAN | Drug catalogue | Browse medicines/sources | GET | `/drug-assistant/drugs*` | Bearer | No | No | query | catalogue schemas | READY |
| PATIENT | My clinician | Current relationship | GET | `/patients/me/clinician` | Bearer | No | ACTIVE approved link | none | `MyClinicianResponse` | BLOCKED |
| PATIENT | Clinician lookup | Verify identifier | GET | `/clinicians/lookup/{risk_sense_id}` | Bearer | No | No | path | `ClinicianLookupResponse` | BLOCKED |
| PATIENT | Access | Subscription/insurance request | POST/GET/PUT | `/subscriptions/`, `/insurance/` | Bearer | No | No | access schemas | access schemas | DEMO_WORKFLOW |
| PATIENT | Access | Entitlement history | GET | `/access/entitlements` | Bearer | No | Own patient | none | entitlement list | BLOCKED |
| CLINICIAN | Profile/patients | Profile and linked patients | GET | `/clinicians/me`, `/clinicians/patients*` | Bearer | No | ACTIVE approved link for patient data | query/path | clinician/patient schemas | BLOCKED |
| CLINICIAN | Assessment | Temporary assessment | POST | `/clinicians/assessment` | Bearer | N/A | N/A | assessment schema | 503 | INTENTIONALLY_EXCLUDED |
| ADMIN | Operations | Metrics/users/clinicians/audit | GET/POST/PATCH | `/admin/*` | Bearer | No | No clinical access | admin schemas | admin schemas | BLOCKED |
| ADMIN | Models | List/suspend/activate | GET/POST | `/admin/models*` | Bearer | No | No | path | model summaries | BLOCKED |
| ADMIN | Drug Assistant | Operational status | GET | `/admin/drug-assistant/status` | Bearer | No | No | none | `DrugAssistantStatusResponse` | READY |

Frontend display formatting, chart rendering, local navigation and countdown presentation are `FRONTEND_ONLY`. The backend remains **NOT FRONTEND-READY** until the additive migration and controlled database smoke matrix pass. Human evidence review is an operational limitation rather than an authorization bypass: patient-facing evidence remains safely unavailable when no reviewed source supports a claim.
