# RiskSense AI backend

RiskSense AI is a FastAPI/PostgreSQL decision-support backend. It uses JWT authentication, database-backed RBAC, patient-clinician relationships, and authoritative access entitlements. Actual ML inference is intentionally not implemented in this repository state.

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

## Access model

Patient registration does not grant product access. Subscription and insurance submissions begin pending. Only backend-controlled staged verification can create an active `AccessEntitlement`. Mock completion endpoints require an ADMIN account and record their source as `MOCK_PAYMENT` or `MOCK_INSURANCE`. Clinician access requires both an approved clinician profile and an active `PatientClinician` relationship.

The existing unversioned routes remain available. Equivalent `/api/v1` aliases are provided for migration, currently hidden from the generated schema to avoid duplicate documentation.
