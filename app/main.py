from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
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
from app.api.v1.drug_assistant import router as drug_assistant_router
from app.api.v1.patient_medications import router as patient_medications_router
from app.api.v1.activation import router as activation_router
from app.api.v1.nutrition import router as nutrition_router
from app.api.v1.fitness import router as fitness_router
from app.api.v1.mindfulness import router as mindfulness_router


app = FastAPI(
    title="RiskSense AI API",
    description=(
        "Backend API for RiskSense AI — "
        "a Zero-Trust Mobile Health Decision Support System."
    ),
    version="0.1.0",
)


def registration_error_details(exc: RequestValidationError) -> list[dict]:
    return [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()]


@app.exception_handler(RequestValidationError)
async def sanitize_registration_errors(request: Request, exc: RequestValidationError):
    if request.scope["path"].startswith(("/auth/register", "/api/v1/auth/register")):
        return JSONResponse(status_code=422, content={"detail": registration_error_details(exc)})
    return await request_validation_exception_handler(request, exc)

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
app.include_router(drug_assistant_router)
app.include_router(patient_medications_router)
app.include_router(activation_router)
app.include_router(nutrition_router)
app.include_router(fitness_router)
app.include_router(mindfulness_router)

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
    drug_assistant_router,
    patient_medications_router,
    activation_router,
    nutrition_router,
    fitness_router,
    mindfulness_router,
):
    app.include_router(versioned_router, prefix="/api/v1", include_in_schema=False)
