"""
Standalone training script for TF-IDF baseline classifier.
This script avoids importing the full classifier to bypass TensorFlow/protobuf conflicts.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
import joblib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Train TF-IDF baseline classifier for TCFD")
    parser.add_argument(
        "--data_path",
        type=str,
        required=True,
        help="Path to training data JSON file"
    )
    parser.add_argument(
        "--use_cross_validation",
        action="store_true",
        help="Use k-fold cross-validation"
    )
    parser.add_argument(
        "--n_splits",
        type=int,
        default=5,
        help="Number of folds for cross-validation"
    )
    parser.add_argument(
        "--max_features",
        type=int,
        default=5000,
        help="Maximum TF-IDF features"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./models/tcfd_classifier",
        help="Directory to save results"
    )

    args = parser.parse_args()

    # Check if data file exists
    data_path = Path(args.data_path)
    if not data_path.exists():
        logger.error(f"Training data file not found: {args.data_path}")
        sys.exit(1)

    # Load training data
    logger.info(f"Loading training data from {args.data_path}")
    with open(data_path, "r") as f:
        data = json.load(f)

    logger.info(f"Loaded {len(data)} training samples")

    # Import ML libraries here to avoid conflicts
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import KFold
    from sklearn.metrics import precision_recall_fscore_support, accuracy_score
    import numpy as np

    LABEL_MAP = {
        "Not disclosed": 0,
        "Partially disclosed": 1,
        "Disclosed": 2
    }
    LABEL_MAP_REVERSE = {v: k for k, v in LABEL_MAP.items()}

    # Prepare data
    texts = [item["text"] for item in data]
    labels = [LABEL_MAP[item["label"]] for item in data]

    logger.info("=" * 80)
    logger.info("Training TF-IDF Baseline Classifier")
    logger.info("=" * 80)

    if args.use_cross_validation:
        logger.info(f"Using {args.n_splits}-fold cross-validation")

        kf = KFold(n_splits=args.n_splits, shuffle=True, random_state=42)
        all_results = []

        for fold, (train_idx, val_idx) in enumerate(kf.split(texts)):
            logger.info(f"Training fold {fold + 1}/{args.n_splits}")

            train_texts = [texts[i] for i in train_idx]
            train_labels = [labels[i] for i in train_idx]
            val_texts = [texts[i] for i in val_idx]
            val_labels = [labels[i] for i in val_idx]

            # Initialize TF-IDF vectorizer
            vectorizer = TfidfVectorizer(
                max_features=args.max_features,
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.95,
                stop_words='english'
            )

            # Fit and transform training data
            X_train = vectorizer.fit_transform(train_texts)
            y_train = np.array(train_labels)

            # Initialize classifier
            classifier = LogisticRegression(
                max_iter=1000,
                class_weight='balanced',
                random_state=42
            )

            # Train classifier
            classifier.fit(X_train, y_train)

            # Evaluate
            X_val = vectorizer.transform(val_texts)
            y_pred = classifier.predict(X_val)

            # Compute metrics
            precision, recall, f1, _ = precision_recall_fscore_support(
                val_labels, y_pred, average=None, labels=[0, 1, 2]
            )
            accuracy = accuracy_score(val_labels, y_pred)

            fold_results = {
                "accuracy": accuracy,
                "precision_not_disclosed": precision[0],
                "precision_partially_disclosed": precision[1],
                "precision_disclosed": precision[2],
                "recall_not_disclosed": recall[0],
                "recall_partially_disclosed": recall[1],
                "recall_disclosed": recall[2],
                "f1_not_disclosed": f1[0],
                "f1_partially_disclosed": f1[1],
                "f1_disclosed": f1[2],
                "macro_f1": np.mean(f1)
            }

            all_results.append(fold_results)
            logger.info(f"Fold {fold + 1} - Accuracy: {accuracy:.4f}, Macro F1: {np.mean(f1):.4f}")

        # Aggregate results
        avg_results = {}
        for key in all_results[0].keys():
            avg_results[key] = np.mean([r[key] for r in all_results])

        logger.info("\n" + "=" * 80)
        logger.info("Cross-Validation Results")
        logger.info("=" * 80)
        logger.info(f"Accuracy: {avg_results['accuracy']:.4f}")
        logger.info(f"Macro F1: {avg_results['macro_f1']:.4f}")
        logger.info(f"\nPer-Class F1:")
        logger.info(f"  Not disclosed: {avg_results['f1_not_disclosed']:.4f}")
        logger.info(f"  Partially disclosed: {avg_results['f1_partially_disclosed']:.4f}")
        logger.info(f"  Disclosed: {avg_results['f1_disclosed']:.4f}")

        results = {"baseline": avg_results}

    else:
        logger.info("Using simple train/val split")

        # Simple 90/10 split
        split_idx = int(len(texts) * 0.9)
        train_texts = texts[:split_idx]
        train_labels = labels[:split_idx]
        val_texts = texts[split_idx:]
        val_labels = labels[split_idx:]

        # Initialize TF-IDF vectorizer
        vectorizer = TfidfVectorizer(
            max_features=args.max_features,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            stop_words='english'
        )

        # Fit and transform training data
        X_train = vectorizer.fit_transform(train_texts)
        y_train = np.array(train_labels)

        # Initialize classifier
        classifier = LogisticRegression(
            max_iter=1000,
            class_weight='balanced',
            random_state=42
        )

        # Train classifier
        classifier.fit(X_train, y_train)
        logger.info("Training completed")

        # Evaluate
        X_val = vectorizer.transform(val_texts)
        y_pred = classifier.predict(X_val)

        # Compute metrics
        precision, recall, f1, _ = precision_recall_fscore_support(
            val_labels, y_pred, average=None, labels=[0, 1, 2]
        )
        accuracy = accuracy_score(val_labels, y_pred)

        results = {
            "baseline": {
                "accuracy": accuracy,
                "precision_not_disclosed": precision[0],
                "precision_partially_disclosed": precision[1],
                "precision_disclosed": precision[2],
                "recall_not_disclosed": recall[0],
                "recall_partially_disclosed": recall[1],
                "recall_disclosed": recall[2],
                "f1_not_disclosed": f1[0],
                "f1_partially_disclosed": f1[1],
                "f1_disclosed": f1[2],
                "macro_f1": np.mean(f1)
            }
        }

        logger.info(f"\nAccuracy: {accuracy:.4f}")
        logger.info(f"Macro F1: {np.mean(f1):.4f}")
        logger.info(f"\nPer-Class F1:")
        logger.info(f"  Not disclosed: {f1[0]:.4f}")
        logger.info(f"  Partially disclosed: {f1[1]:.4f}")
        logger.info(f"  Disclosed: {f1[2]:.4f}")

    # Save results
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results_file = output_path / "baseline_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"\nResults saved to {results_file}")

    # Save the trained model for API use
    import joblib
    model_file = output_path / "baseline_model.pkl"
    joblib.dump({
        'vectorizer': vectorizer,
        'classifier': classifier
    }, model_file)
    logger.info(f"Trained model saved to {model_file}")

    logger.info("\nTraining completed successfully!")


if __name__ == "__main__":
    main()
