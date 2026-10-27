"""Offline candidate audit for the existing five-feature UCI heart contract.

Reads an official UCI archive supplied via --archive. Never writes model
artifacts or changes the deployed model. Requires scikit-learn and pandas.
"""

import argparse
from io import BytesIO
from pathlib import Path
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = ["age", "sex", "systolic_bp", "total_cholesterol", "fasting_blood_sugar_high"]
COLUMNS = ["age", "sex", "cp", "trestbps", "chol", "fbs", "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal", "num"]


def load_data(archive: Path):
    with zipfile.ZipFile(archive) as source:
        data = source.read("processed.cleveland.data")
    raw = pd.read_csv(BytesIO(data), names=COLUMNS, na_values="?")
    x = raw.rename(columns={"trestbps": "systolic_bp", "chol": "total_cholesterol", "fbs": "fasting_blood_sugar_high"})[FEATURES].apply(pd.to_numeric, errors="coerce")
    y = (raw["num"] > 0).astype(int)
    return x, y


def threshold_for_recall(y, scores, minimum=0.90):
    candidates = np.unique(scores)
    eligible = [float(value) for value in candidates if recall_score(y, scores >= value) >= minimum]
    return max(eligible)


def report(label, y, scores, threshold):
    labels = scores >= threshold
    print(f"{label}: threshold={threshold:.3f} accuracy={accuracy_score(y, labels):.3f} recall={recall_score(y, labels):.3f} auc={roc_auc_score(y, scores):.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    x, y = load_data(args.archive)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=.2, stratify=y, random_state=42)
    current_path = Path(__file__).resolve().parents[1] / "app/ml/heart_disease/risksense_heart_disease_model_v1.pkl"
    current = joblib.load(current_path)
    report("deployed v1 on reconstructed holdout", y_test, current["pipeline"].predict_proba(x_test)[:, 1], current["decision_threshold"])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results = []
    for weight in (None, "balanced"):
        for c in (.1, 1., 10.):
            pipeline = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), LogisticRegression(C=c, class_weight=weight, max_iter=1000, random_state=42))
            scores = cross_val_predict(pipeline, x_train, y_train, cv=cv, method="predict_proba")[:, 1]
            threshold = threshold_for_recall(y_train, scores)
            accuracy = accuracy_score(y_train, scores >= threshold)
            results.append((accuracy, weight, c, threshold, pipeline))
            print(f"CV weight={weight} C={c}: accuracy={accuracy:.3f} recall={recall_score(y_train, scores >= threshold):.3f} auc={roc_auc_score(y_train, scores):.3f}")
    _, weight, c, threshold, selected = max(results, key=lambda row: row[0])
    selected.fit(x_train, y_train)
    report(f"selected candidate weight={weight} C={c}", y_test, selected.predict_proba(x_test)[:, 1], threshold)


if __name__ == "__main__":
    main()
