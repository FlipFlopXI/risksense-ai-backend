from fastapi import FastAPI

from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend API for RiskSense AI — "
        "a Zero-Trust Mobile Health Decision Support System."
    ),
    version=settings.app_version,
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }