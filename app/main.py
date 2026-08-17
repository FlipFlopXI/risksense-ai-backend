from fastapi import FastAPI


app = FastAPI(
    title="RiskSense AI API",
    description=(
        "Backend API for RiskSense AI — "
        "a Zero-Trust Mobile Health Decision Support System."
    ),
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "RiskSense AI API",
        "version": "0.1.0",
    }