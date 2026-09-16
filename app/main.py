from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.vitals import router as vitals_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.insurance import router as insurance_router
from app.api.v1.labs import router as labs_router
from app.api.v1.clinicians import router as clinicians_router
from app.api.v1.admin import router as admin_router
from app.api.v1.patients import router as patients_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.access import router as access_router
from app.core.config import settings


app = FastAPI(
    title="RiskSense AI API",
    description=(
        "Backend API for RiskSense AI — "
        "a Zero-Trust Mobile Health Decision Support System."
    ),
    version="0.1.0",
)

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "RiskSense AI API",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
    }


app.include_router(auth_router)
app.include_router(health_router)
app.include_router(vitals_router)
app.include_router(subscriptions_router)
app.include_router(insurance_router)
app.include_router(labs_router)
app.include_router(clinicians_router)
app.include_router(admin_router)
app.include_router(patients_router)
app.include_router(intelligence_router)
app.include_router(access_router)

# Versioned compatibility aliases. Existing unversioned clients continue to work.
for versioned_router in (
    auth_router,
    health_router,
    vitals_router,
    subscriptions_router,
    insurance_router,
    labs_router,
    clinicians_router,
    admin_router,
    patients_router,
    intelligence_router,
    access_router,
):
    app.include_router(versioned_router, prefix="/api/v1", include_in_schema=False)
