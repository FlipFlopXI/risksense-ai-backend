"""Published hold-out accuracy for the two verified prediction artifacts."""

from fractions import Fraction
from math import ceil, isclose, isfinite

from app.ml.diabetes import runtime as diabetes_runtime
from app.ml.heart_disease import runtime as heart_runtime
from app.services.diabetes_service import MODEL_ID as DIABETES_MODEL_ID
from app.services.risk_analysis_service import MODEL_ID as HEART_MODEL_ID


def _diabetes_holdout_accuracy(summary: dict) -> float | None:
    """Recover correct/total from recorded rates and the stratified test split."""
    try:
        if summary["split"] != "80/20 stratified; random_state=42":
            return None
        total = int(summary["usable_records"])
        if int(summary["positive_records"]) + int(summary["negative_records"]) != total:
            return None
        held_out = ceil(total * 0.2)
        sensitivity = float(summary["held_out_sensitivity"])
        specificity = float(summary["held_out_specificity"])
        if not all(isfinite(v) and 0 <= v <= 1 for v in (sensitivity, specificity)):
            return None
        positive = Fraction(sensitivity).limit_denominator(held_out)
        negative = Fraction(specificity).limit_denominator(held_out)
        if positive.denominator + negative.denominator != held_out:
            return None
        if not (isclose(float(positive), sensitivity, abs_tol=1e-12)
                and isclose(float(negative), specificity, abs_tol=1e-12)):
            return None
        return (positive.numerator + negative.numerator) / held_out
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def verified_holdout_accuracy(record) -> tuple[float | None, str | None]:
    """Never attach one artifact's metric to another registry version."""
    try:
        if record.id == DIABETES_MODEL_ID and record.prediction_target == diabetes_runtime.TARGET:
            loaded = diabetes_runtime.load_model()
            if record.version == loaded.version:
                return _diabetes_holdout_accuracy(loaded.metadata["training_summary"]), "NHANES held-out test split"
        if record.id == HEART_MODEL_ID and record.prediction_target == heart_runtime.TARGET:
            loaded = heart_runtime.load_model()
            if record.version == loaded.version:
                value = float(loaded.metadata["holdout_metrics"]["accuracy"])
                if isfinite(value) and 0 <= value <= 1:
                    return value, "Cleveland held-out test split"
    except Exception:
        return None, None
    return None, None
