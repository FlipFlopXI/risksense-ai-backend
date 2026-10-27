"""Offline NHANES candidate audit for the existing six-feature diabetes contract.

Reads official NHANES 2017–2018 XPT files via --data-dir. Does not alter or
write deployed artifacts. The label is prevalent self-reported diagnosis.
"""

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = ["age", "sex", "bmi", "waist_circumference", "systolic_bp", "diastolic_bp"]


def load_data(folder: Path):
    demo, body, bp, diabetes = [pd.read_sas(folder / f"{name}.xpt") for name in ("DEMO_J", "BMX_J", "BPX_J", "DIQ_J")]
    data = demo.merge(body, on="SEQN").merge(bp, on="SEQN").merge(diabetes, on="SEQN")
    data = data[data.RIDAGEYR.between(18, 79) & data.DIQ010.isin([1, 2])]
    data = data.dropna(subset=["RIDAGEYR", "RIAGENDR", "BMXBMI", "BMXWAIST"])
    x = pd.DataFrame({
        "age": data.RIDAGEYR,
        "sex": (data.RIAGENDR == 1).astype(int),
        "bmi": data.BMXBMI,
        "waist_circumference": data.BMXWAIST,
        "systolic_bp": data[[f"BPXSY{i}" for i in range(1, 5)]].mean(axis=1),
        "diastolic_bp": data[[f"BPXDI{i}" for i in range(1, 5)]].mean(axis=1),
    })[FEATURES]
    return x, (data.DIQ010 == 1).astype(int)


def threshold_for_recall(y, scores, minimum=.80):
    candidates = np.unique(scores)
    return max(float(value) for value in candidates if recall_score(y, scores >= value) >= minimum)


def report(label, y, scores, threshold):
    labels = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, labels).ravel()
    print(f"{label}: threshold={threshold:.3f} accuracy={accuracy_score(y, labels):.3f} sensitivity={recall_score(y, labels):.3f} specificity={tn/(tn+fp):.3f} auc={roc_auc_score(y, scores):.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    x, y = load_data(args.data_dir)
    print(f"training contract rows={len(x)} positive={int(y.sum())}")
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=.2, stratify=y, random_state=42)
    current = joblib.load(Path(__file__).resolve().parents[1] / "app/ml/diabetes/risksense_diabetes_model_v1.pkl")
    report("deployed v1 on reconstructed holdout", y_test, current["pipeline"].predict_proba(x_test)[:, 1], current["decision_threshold"])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results = []
    for weight in (None, "balanced"):
        for c in (.1, 1., 10.):
            candidate = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("classifier", LogisticRegression(C=c, class_weight=weight, max_iter=3000, random_state=42))])
            scores = cross_val_predict(candidate, x_train, y_train, cv=cv, method="predict_proba")[:, 1]
            threshold = threshold_for_recall(y_train, scores)
            tn, fp, fn, tp = confusion_matrix(y_train, scores >= threshold).ravel()
            specificity = tn / (tn + fp)
            results.append((specificity, weight, c, threshold, candidate))
            print(f"CV weight={weight} C={c}: sensitivity={recall_score(y_train, scores >= threshold):.3f} specificity={specificity:.3f} auc={roc_auc_score(y_train, scores):.3f}")
    _, weight, c, threshold, selected = max(results, key=lambda row: row[0])
    selected.fit(x_train, y_train)
    report(f"selected candidate weight={weight} C={c}", y_test, selected.predict_proba(x_test)[:, 1], threshold)


if __name__ == "__main__":
    main()
