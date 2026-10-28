"""Evaluate missing-input candidates without changing deployed artifacts.

The same patient never appears in both training and validation folds. Training
copies have selected measurements hidden to model realistic absent inputs.
The untouched patient holdout is evaluated separately for every mask pattern.
"""
from argparse import ArgumentParser
from pathlib import Path
from hashlib import sha256
import json

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_heart_candidates import load_data as heart_data
from evaluate_diabetes_candidates import load_data as diabetes_data


MASKS = {
    "heart": [(), ("total_cholesterol",), ("fasting_blood_sugar_high",),
              ("total_cholesterol", "fasting_blood_sugar_high")],
    "diabetes": [(), ("systolic_bp", "diastolic_bp")],
}


def masked(frame, fields):
    result = frame.copy()
    for field in fields:
        result[field] = np.nan
    return result


def augmented(frame, labels, masks):
    import pandas as pd
    return pd.concat([masked(frame, mask) for mask in masks], ignore_index=True), np.tile(np.asarray(labels), len(masks))


def evaluate(labels, scores, threshold):
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, predicted).ravel()
    return {"accuracy": round(accuracy_score(labels, predicted), 4),
            "sensitivity": round(recall_score(labels, predicted), 4),
            "specificity": round(tn / (tn + fp), 4),
            "auc": round(roc_auc_score(labels, scores), 4),
            "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]]}


def candidate(weight, c):
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                         StandardScaler(), LogisticRegression(C=c, class_weight=weight,
                                                               max_iter=3000, random_state=42))


def run(name, x, y, masks, baseline_path):
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=.2, stratify=y, random_state=42)
    baseline = joblib.load(baseline_path)
    baseline_metrics = {}
    for mask in masks:
        key = "+".join(mask) if mask else "complete"
        try:
            baseline_metrics[key] = evaluate(y_test,
                baseline["pipeline"].predict_proba(masked(x_test, mask))[:, 1],
                baseline["decision_threshold"])
        except Exception:
            baseline_metrics[key] = {"unavailable": True}
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    options = []
    for weight in (None, "balanced"):
        for c in (.1, 1., 10.):
            scores = {mask: np.zeros(len(x_train)) for mask in masks}
            for train_idx, val_idx in folds.split(x_train, y_train):
                train_x, train_y = augmented(x_train.iloc[train_idx], y_train.iloc[train_idx], masks)
                model = candidate(weight, c).fit(train_x, train_y)
                for mask in masks:
                    scores[mask][val_idx] = model.predict_proba(masked(x_train.iloc[val_idx], mask))[:, 1]
            # Choose a single threshold using CV only, preserving sensitivity
            # separately for every missing-input scenario.
            floor = .98 if name == "heart" else .90
            threshold = min(
                float(np.sort(scores[mask][np.asarray(y_train) == 1])[
                    max(0, int(np.floor((1 - floor) * int(np.sum(y_train)))) - 1)])
                for mask in masks
            )
            cv = {("+".join(mask) if mask else "complete"): evaluate(y_train, scores[mask], threshold)
                  for mask in masks}
            options.append({"weight": weight, "c": c, "threshold": threshold,
                            "cv": cv, "score": min(row["specificity"] for row in cv.values())})
    selected = max(options, key=lambda row: (row["score"], row["cv"]["complete"]["accuracy"]))
    train_x, train_y = augmented(x_train, y_train, masks)
    model = candidate(selected["weight"], selected["c"]).fit(train_x, train_y)
    holdout = {("+".join(mask) if mask else "complete"):
               evaluate(y_test, model.predict_proba(masked(x_test, mask))[:, 1], selected["threshold"])
               for mask in masks}
    return {"name": name, "rows": len(x), "train_rows": len(x_train), "holdout_rows": len(x_test),
            "mask_patterns": [list(mask) for mask in masks], "baseline_holdout": baseline_metrics,
            "selected": {key: value for key, value in selected.items() if key != "score"},
            "candidate_holdout": holdout}, model


def main():
    args = ArgumentParser()
    args.add_argument("--heart-archive", type=Path, required=True)
    args.add_argument("--nhanes-dir", type=Path, required=True)
    args.add_argument("--output-dir", type=Path)
    parsed = args.parse_args()
    root = Path(__file__).resolve().parents[1]
    heart_x, heart_y = heart_data(parsed.heart_archive)
    diabetes_x, diabetes_y = diabetes_data(parsed.nhanes_dir)
    trained = [run("heart", heart_x, heart_y, MASKS["heart"],
                   root / "app/ml/heart_disease/risksense_heart_disease_model_v1.pkl"),
               run("diabetes", diabetes_x, diabetes_y, MASKS["diabetes"],
                   root / "app/ml/diabetes/risksense_diabetes_model_v1.pkl")]
    results = [summary for summary, _ in trained]
    if parsed.output_dir:
        parsed.output_dir.mkdir(parents=True, exist_ok=True)
        for summary, model in trained:
            path = parsed.output_dir / f"{summary['name']}_missing_input_candidate.pkl"
            joblib.dump(model, path)
            summary["candidate_artifact"] = path.name
            summary["candidate_sha256"] = sha256(path.read_bytes()).hexdigest()
        (parsed.output_dir / "evaluation.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
