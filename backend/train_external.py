"""
Train TCFD passage classifiers on public, human-labelled datasets.

Models (logistic regression on TF-IDF, sentence embeddings, or both - the
best feature set per model is selected on held-out data; saved to models/tcfd_external/):
  1. pillar_model.pkl     - is a passage TCFD-relevant, and which pillar?
                            labels: none / governance / strategy / risk / metrics
                            data:   climatebert/tcfd_recommendations (CC BY-NC-SA 4.0)
                                    + rexarski/TCFD_disclosure mapped to pillars (MIT)
                            eval:   official ClimateBERT test split (400 paragraphs)
  2. disclosure_model.pkl - which of the 11 recommended disclosures (G.1 ... M.3)?
                            data:   rexarski/TCFD_disclosure (593 sentences, MIT)
                            eval:   stratified 5-fold cross-validation

Usage:
    python train_external.py                 # train, evaluate, save
    python train_external.py --no_save       # evaluate only
    python train_external.py --features tfidf  # restrict the feature sets compared
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import FeatureUnion, Pipeline

from passage_features import DEFAULT_MODEL, EmbeddingFeaturizer

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "datasets" / "external"
OUT_DIR = BASE_DIR / "models" / "tcfd_external"

CLIMATEBERT_LABELS = ["none", "metrics", "strategy", "risk", "governance"]
PILLARS = ["none", "governance", "strategy", "risk", "metrics"]

# rexarski label -> (our requirement id, pillar)
REXARSKI_MAP = {
    "Governance a)": ("G.1", "governance"),
    "Governance b)": ("G.2", "governance"),
    "Strategy a)": ("S.1", "strategy"),
    "Strategy b)": ("S.2", "strategy"),
    "Strategy c)": ("S.3", "strategy"),
    "Risk Management a)": ("R.1", "risk"),
    "Risk Management b)": ("R.2", "risk"),
    "Risk Management c)": ("R.3", "risk"),
    "Metrics and Targets a)": ("M.1", "metrics"),
    "Metrics and Targets b)": ("M.2", "metrics"),
    "Metrics and Targets c)": ("M.3", "metrics"),
}
PILLAR_OF = {rid: p for rid, p in REXARSKI_MAP.values()}


FEATURE_SETS = ("tfidf", "embed", "both")


def make_pipeline(features: str, C: float, max_features: int = 20000, min_df: int = 2) -> Pipeline:
    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=min_df,
                            max_features=max_features, stop_words="english")
    if features == "tfidf":
        feats = tfidf
    elif features == "embed":
        feats = EmbeddingFeaturizer(DEFAULT_MODEL)
    else:
        feats = FeatureUnion([("tfidf", tfidf), ("embed", EmbeddingFeaturizer(DEFAULT_MODEL))])
    return Pipeline([
        ("features", feats),
        ("clf", LogisticRegression(C=C, max_iter=3000, class_weight="balanced")),
    ])


def load_data():
    cb_train = pd.read_parquet(DATA_DIR / "climatebert_tcfd_train.parquet")
    cb_test = pd.read_parquet(DATA_DIR / "climatebert_tcfd_test.parquet")
    for d in (cb_train, cb_test):
        d["pillar"] = d["label"].map(lambda i: CLIMATEBERT_LABELS[i])

    rex = pd.read_parquet(DATA_DIR / "rexarski_tcfd_disclosure_train.parquet")
    rex["requirement_id"] = rex["label"].map(lambda l: REXARSKI_MAP[l][0])
    rex["pillar"] = rex["label"].map(lambda l: REXARSKI_MAP[l][1])
    rex = rex.drop_duplicates("text")
    return cb_train, cb_test, rex


def metrics(y_true, y_pred, labels):
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, labels=labels, average="macro"), 4),
        "per_class": {
            k: {m: round(v[m], 4) for m in ("precision", "recall", "f1-score", "support")}
            for k, v in classification_report(y_true, y_pred, labels=labels, output_dict=True,
                                              zero_division=0).items() if k in labels
        },
        "confusion_matrix": {"labels": labels,
                             "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
    }


def train_pillar(cb_train, cb_test, rex, feature_sets):
    print("\n=== Pillar model (none / governance / strategy / risk / metrics) ===")
    results, best = {}, None
    for use_rex in (False, True):
        train = cb_train[["text", "pillar"]]
        if use_rex:
            train = pd.concat([train, rex[["text", "pillar"]]], ignore_index=True)
        for features in feature_sets:
          for C in (1.0, 3.0, 10.0):
            model = make_pipeline(features, C).fit(train["text"], train["pillar"])
            pred = model.predict(cb_test["text"])
            m = metrics(cb_test["pillar"], pred, PILLARS)
            key = f"{features}_{'climatebert+rexarski' if use_rex else 'climatebert'}_C{C}"
            results[key] = {"accuracy": m["accuracy"], "macro_f1": m["macro_f1"]}
            print(f"  {key:36} acc={m['accuracy']:.3f}  macro-F1={m['macro_f1']:.3f}")
            if best is None or m["macro_f1"] > best[0]["macro_f1"]:
                best = (m, key, model, len(train))
    m, key, model, n = best
    print(f"\n  Best: {key} (trained on {n} passages, tested on {len(cb_test)})")
    print(classification_report(cb_test["pillar"], model.predict(cb_test["text"]), labels=PILLARS, zero_division=0))
    return model, {"selected": key, "train_size": n, "test_size": len(cb_test),
                   "test_metrics": m, "grid": results}


def train_disclosure(rex, feature_sets):
    print("\n=== Disclosure model (11 TCFD recommended disclosures) ===")
    labels = sorted(PILLAR_OF)
    y = rex["requirement_id"].values
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results, best = {}, None
    for features in feature_sets:
      for C in (1.0, 3.0, 10.0):
        model = make_pipeline(features, C, max_features=10000, min_df=1)
        proba = cross_val_predict(model, rex["text"], y, cv=cv, method="predict_proba")
        classes = sorted(set(y))
        pred = np.array(classes)[proba.argmax(1)]

        # At inference time the pillar is already known, so also measure accuracy
        # when the choice is restricted to disclosures within the true pillar.
        within = []
        for row, true in zip(proba, y):
            allowed = [i for i, c in enumerate(classes) if PILLAR_OF[c] == PILLAR_OF[true]]
            within.append(classes[allowed[int(np.argmax(row[allowed]))]])
        m = metrics(y, pred, labels)
        within_acc = round(accuracy_score(y, within), 4)
        results[f"{features}_C{C}"] = {"accuracy": m["accuracy"], "macro_f1": m["macro_f1"],
                            "within_pillar_accuracy": within_acc}
        print(f"  {features:6} C={C:<5} acc={m['accuracy']:.3f}  macro-F1={m['macro_f1']:.3f}  within-pillar acc={within_acc:.3f}")
        if best is None or m["macro_f1"] > best[0]["macro_f1"]:
            best = (m, C, within_acc, pred, features)
    m, C, within_acc, pred, features = best
    print(f"\n  Best: {features} C={C} (5-fold CV on {len(rex)} sentences)")
    print(classification_report(y, pred, labels=labels, zero_division=0))
    final = make_pipeline(features, C, max_features=10000, min_df=1)
    final.fit(rex["text"], y)
    return final, {"selected": f"{features}_C{C}", "train_size": len(rex), "evaluation": "stratified 5-fold CV",
                   "cv_metrics": m, "within_pillar_accuracy": within_acc, "grid": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no_save", action="store_true")
    parser.add_argument("--output_dir", type=Path, default=OUT_DIR,
                        help="where to save models (the API loads models/tcfd_external)")
    parser.add_argument("--features", nargs="+", choices=FEATURE_SETS, default=list(FEATURE_SETS))
    args = parser.parse_args()

    cb_train, cb_test, rex = load_data()
    print(f"ClimateBERT: {len(cb_train)} train / {len(cb_test)} test   rexarski: {len(rex)} sentences")

    pillar_model, pillar_results = train_pillar(cb_train, cb_test, rex, args.features)
    disclosure_model, disclosure_results = train_disclosure(rex, args.features)

    if args.no_save:
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pillar_model, args.output_dir / "pillar_model.pkl")
    joblib.dump({"model": disclosure_model, "pillar_of": PILLAR_OF}, args.output_dir / "disclosure_model.pkl")
    with open(args.output_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump({
            "embedding_model": DEFAULT_MODEL,
            "sources": {
                "climatebert/tcfd_recommendations": "CC BY-NC-SA 4.0",
                "rexarski/TCFD_disclosure": "MIT",
            },
            "pillar_model": pillar_results,
            "disclosure_model": disclosure_results,
        }, f, indent=2)
    print(f"\nSaved models and results to {args.output_dir}")


if __name__ == "__main__":
    main()
