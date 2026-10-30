# RiskSense AI deployment: Render backend and Vercel website

This is a deployment checklist. Publishing remains a separate action. Keep all secrets in hosting environment variables, never in Git or `NEXT_PUBLIC_*` values.

## 1. Render backend

Create a **Web Service** from the `risksense-ai-backend` GitHub repository. Select the Python runtime and the intended branch. The repository's `.python-version` selects Python 3.13.

| Render setting | Value |
| --- | --- |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Root directory | Repository root |

Set these **private Render environment variables**:

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | Existing Supabase PostgreSQL connection string, using the SQLAlchemy `postgresql+psycopg` driver; use the Supabase session pooler if Render cannot reach the direct IPv6 endpoint. Require TLS. |
| `JWT_SECRET_KEY` | Strong private signing key. Changing it invalidates existing JWTs. |
| `JWT_ALGORITHM` | `HS256` unless deliberately changed across the system. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session lifetime, for example `30`. |
| `WEBAPP_BASE_URL` | Exact final Vercel HTTPS origin, without a trailing slash. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins, including the exact final Vercel HTTPS origin. Add only other origins actually used. |
| `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME` | Existing email integration; sender must be verified in Brevo. |
| `DEMO_ACTIVATION_ENABLED` | Set to `true` only when the project's clearly labelled staged subscription/insurance activation is intended to work on the hosted site. This is not a real payment or insurer verification. |

Do not set `ENVIRONMENT=test` or `TEST_DATABASE_URL` on Render. The application uses `DATABASE_URL` outside the test environment.

Do not put `alembic upgrade head` in the service start command. Before launch, inspect the current Supabase Alembic revision and repository head; apply any outstanding migration as a separate, reviewed operation. A successful `/health` response checks process startup, not database connectivity or migration state.

Render free services may sleep after inactivity. Allow for a cold start during demos; initial API requests may take longer than client timeouts. A paid always-on service is optional, not required to prepare the deployment.

## 2. Vercel website

Import the `risksense-ai-website` GitHub repository as a Next.js project. Use its repository root and default build command. Set **Production environment variables**:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Exact Render HTTPS origin, without a trailing slash. The website rewrites `/backend/*` requests to this origin. |
| `NEXT_PUBLIC_SITE_URL` | Exact final Vercel HTTPS origin. |
| `NEXT_PUBLIC_MOBILE_RETURN_URL` | Set only after a verified mobile app link/deep link exists; otherwise leave unset. |
| `NEXT_PUBLIC_SUPPORT_EMAIL` | Optional public support address. |

Never put the database URL, JWT key or Brevo key in Vercel's `NEXT_PUBLIC_*` variables. The website should talk to the backend API, not connect directly to Supabase PostgreSQL.

Once Vercel assigns its final domain, update `WEBAPP_BASE_URL` and `CORS_ORIGINS` on Render. Add a custom domain later if desired, then update both services' origin variables and redeploy.

## 3. Mobile build and smoke checks

The Flutter app defaults to the Android emulator's local backend. For a hosted build, pass `--dart-define=RISKSENSE_API_URL=https://<render-service>.onrender.com` when building or running it. Do not leave the emulator URL in a production build.

After deployment, verify in this order:

1. `GET https://<render-service>.onrender.com/health` returns healthy.
2. The final Vercel site loads and `/backend/health` reaches the Render API through the website rewrite.
3. Registration email, OTP, login, account activation and onboarding work against Supabase using a dedicated test account.
4. Subscription/insurance screens clearly identify their staged verification, and access authorization remains enforced.
5. Flutter login and a protected API request reach the Render origin.

Do not use the live Supabase database for automated destructive test suites. Preserve existing data and audit records.
