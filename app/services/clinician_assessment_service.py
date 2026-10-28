"""In-memory model inference for anonymous clinician demonstrations."""
from app.ml.common import ModelInputError, explain_logistic_features
from app.ml.diabetes import runtime as diabetes
from app.ml.heart_disease import runtime as heart
from app.schemas.clinician_assessment import ClinicalAssessmentRequest, ClinicalAssessmentResponse


def assess(request: ClinicalAssessmentRequest, loaded) -> ClinicalAssessmentResponse:
    if request.model == "diabetes":
        if (request.height_cm is None) != (request.weight_kg is None):
            raise ModelInputError(["height_cm", "weight_kg"], missing=True)
        bmi = (round(request.weight_kg / (request.height_cm / 100) ** 2, 2)
               if request.height_cm is not None and request.weight_kg is not None else None)
        features = diabetes.build_features(
            age=request.age, sex=request.sex, bmi=bmi,
            waist_circumference=request.waist_circumference_cm,
            systolic_bp=request.systolic_bp, diastolic_bp=request.diastolic_bp,
        )
        score, elevated = diabetes.predict(features, loaded)
        factors = explain_logistic_features(features, loaded, "Diabetes")
        disclaimer = diabetes.DISCLAIMER
    else:
        features = heart.build_features(
            age=request.age, sex=request.sex, systolic_bp=request.systolic_bp,
            total_cholesterol=request.total_cholesterol, cholesterol_unit="mg/dL",
            fasting_glucose=request.fasting_glucose, glucose_unit="mg/dL",
        )
        score, elevated = heart.predict(features, loaded)
        factors = explain_logistic_features(features, loaded, "Heart Disease")
        disclaimer = heart.DISCLAIMER + (
            " Missing laboratory readings were imputed from training data; this estimate has additional uncertainty."
            if request.fasting_glucose is None or request.total_cholesterol is None else ""
        )
    raised = [item["feature"].replace("_", " ") for item in factors
              if item["direction"] == "raises"][:2]
    interpretation = f"The model estimated a {score * 100:.1f}% score."
    if raised:
        interpretation += f" {', '.join(raised)} raised the score relative to the training baseline."
    interpretation += " These are model contributions, not clinical causes or a diagnosis."
    return ClinicalAssessmentResponse(
        model=request.model, risk_score=score,
        risk_classification="elevated" if elevated else "standard",
        interpretation=interpretation, contributing_factors=factors,
        model_version=loaded.version, decision_threshold=loaded.threshold,
        disclaimer=disclaimer, persisted=False,
    )
