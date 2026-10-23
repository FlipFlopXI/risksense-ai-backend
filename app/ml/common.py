"""Database-independent contracts shared by the fixed server-side runtimes."""
from dataclasses import dataclass
from datetime import date
from typing import Any
import math

import pandas as pd


class ModelUnavailableError(Exception):
    """Only fixed, safe messages are exposed by the API."""


class ModelInputError(Exception):
    def __init__(self, fields: list[str], *, missing: bool = False, message: str | None = None):
        self.fields = fields
        self.missing = missing
        self.message = message
        super().__init__("Required model inputs are missing or invalid.")


@dataclass(frozen=True)
class LoadedModel:
    pipeline: Any
    threshold: float
    feature_order: tuple[str, ...]
    version: str
    artifact_hash: str
    metadata: dict


def completed_age(born: date | None, today: date) -> int | None:
    if born is None:
        return None
    if born > today:
        raise ModelInputError(["age"])
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def predict_probability(features, model: LoadedModel, feature_order: tuple[str, ...], label: str):
    try:
        if model.feature_order != feature_order:
            raise ValueError
        values = features.model_dump()
        frame = pd.DataFrame([[values[name] for name in feature_order]], columns=feature_order)
        probabilities = model.pipeline.predict_proba(frame)
        if probabilities.shape != (1, 2):
            raise ValueError
        probability = float(probabilities[0, 1])
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError
        return probability, probability >= model.threshold
    except Exception:
        raise ModelUnavailableError(f"{label} inference is unavailable.") from None


def explain_logistic_features(features, model: LoadedModel, label: str) -> list[dict]:
    """Return exact signed contributions to this pipeline's log-odds score.

    These are model arithmetic relative to the scaler baseline, not causal
    clinical effects or independent probabilities.
    """
    try:
        values = features.model_dump()
        order = model.feature_order
        frame = pd.DataFrame([[values[name] for name in order]], columns=order)
        transformed = model.pipeline[:-1].transform(frame)
        classifier = model.pipeline.steps[-1][1]
        coefficients = classifier.coef_[0]
        if transformed.shape != (1, len(order)) or len(coefficients) != len(order):
            raise ValueError
        contributions = [float(transformed[0, index] * coefficients[index])
                         for index in range(len(order))]
        if not all(math.isfinite(value) for value in contributions):
            raise ValueError
        model_logit = float(model.pipeline.decision_function(frame)[0])
        reconstructed = float(classifier.intercept_[0]) + sum(contributions)
        if not math.isclose(model_logit, reconstructed, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError
        total = sum(abs(value) for value in contributions)
        return sorted(({
            "feature": name,
            "log_odds_contribution": value,
            "relative_magnitude": abs(value) / total if total else 0.0,
            "direction": "raises" if value > 0 else "lowers" if value < 0 else "neutral",
        } for name, value in zip(order, contributions)),
            key=lambda item: abs(item["log_odds_contribution"]), reverse=True)
    except Exception:
        raise ModelUnavailableError(f"{label} explanation is unavailable.") from None
