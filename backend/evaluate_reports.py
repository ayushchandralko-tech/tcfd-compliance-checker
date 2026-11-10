"""
End-to-end evaluation of the TCFD assessment against human labels.

Labels are the JSON files saved by the labelling tool (frontend/src/label.html)
into datasets/labels/. Each file names its source PDF, which is looked up in
library/ and datasets/reports/ (checked against the stored SHA-256).

Each labelled report is assessed with the criterion-level pipeline (assessment.py) and compared:
  - status accuracy and macro-F1 over Disclosed / Partially disclosed / Not disclosed
    (a "Not assessable" prediction counts as wrong unless the label is also Not assessable)
  - "within one step" agreement (Disclosed vs Partial counts as close)
  - per-report compliance-score error (labelled vs predicted, 0-100)
  - evidence hit rate: share of labels with evidence pages where at least one of the
    criterion evidence passages is on a labelled page

Reports are evaluated as whole units (no passage-level splitting), so results reflect
unseen-report performance; thresholds were calibrated on EBRD 2023 and AstraZeneca 2023,
so treat scores on those two reports as in-sample.

Only human-confirmed labels count by default; AI-drafted labels (source=ai_draft)
are skipped unless --include_drafts is given.

Usage:
    python evaluate_reports.py
    python evaluate_reports.py --include_drafts     # also count unreviewed AI-drafted labels
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import tcfd_api_server as server  # noqa: E402

STATUSES = ["Not disclosed", "Partially disclosed", "Disclosed"]
ALL_STATUSES = STATUSES + ["Not assessable"]
POINTS = {"Disclosed": 1.0, "Partially disclosed": 0.5, "Not disclosed": 0.0}


def find_pdf(meta: dict, pdf_dirs) -> Path:
    name = meta["source_file"]
    for d in pdf_dirs:
        for candidate in [d / name, *d.rglob(name)]:
            if candidate.is_file():
                if meta.get("sha256"):
                    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    if digest != meta["sha256"]:
                        print(f"  warning: {candidate} does not match the labelled file's SHA-256")
                return candidate
    raise FileNotFoundError(f"{name} not found in {', '.join(str(d) for d in pdf_dirs)}")


def load_labels(labels_dir: Path):
    files = sorted(labels_dir.glob("*.json"))
    if not files:
        sys.exit(f"No label files in {labels_dir}. Label reports with frontend/src/label.html first.")
    return [(f, json.loads(f.read_text(encoding="utf-8"))) for f in files]


def evaluate(reports) -> dict:
    y_true, y_pred, rows, score_errors, hits, hit_total = [], [], [], [], 0, 0
    elapsed = 0.0
    for label_file, record, pdf in reports:
        t = time.time()
        doc = server.parse_document(pdf.read_bytes())
        checklist = server.assess(doc, pdf.name)["compliance_checklist"]
        elapsed += time.time() - t

        true_points, pred_points = [], []
        for req_id, lab in record["labels"].items():
            pred = checklist[req_id]
            y_true.append(lab["label"])
            y_pred.append(pred["status"])
            if lab["label"] in POINTS and pred["status"] in POINTS:
                true_points.append(POINTS[lab["label"]])
                pred_points.append(POINTS[pred["status"]])
            if lab.get("evidence_pages"):
                hit_total += 1
                retrieved = {e["page"] for e in pred["evidence"]}
                hits += bool(retrieved & set(lab["evidence_pages"]))
            rows.append({"report": record["metadata"]["source_file"], "requirement": req_id,
                         "label": lab["label"], "predicted": pred["status"],
                         "coverage": pred["coverage"]["score"], "confidence": pred["confidence"]["level"]})
        if true_points:
            score_errors.append({"report": record["metadata"]["source_file"],
                                 "labelled_score": round(sum(true_points) / len(true_points) * 100, 1),
                                 "predicted_score": round(sum(pred_points) / len(pred_points) * 100, 1)})

    step = {s: i for i, s in enumerate(STATUSES)}
    near = [a == b or (a in step and b in step and abs(step[a] - step[b]) <= 1) for a, b in zip(y_true, y_pred)]
    return {
        "config": "criterion-level",
        "n_reports": len(reports),
        "n_labels": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 3),
        "macro_f1": round(f1_score(y_true, y_pred, labels=STATUSES, average="macro", zero_division=0), 3),
        "within_one_step": round(sum(near) / len(near), 3),
        "score_mae": round(sum(abs(e["labelled_score"] - e["predicted_score"]) for e in score_errors)
                           / len(score_errors), 1) if score_errors else None,
        "evidence_hit_rate": round(hits / hit_total, 3) if hit_total else None,
        "evidence_labels": hit_total,
        "seconds_per_report": round(elapsed / len(reports), 1),
        "confusion_matrix": {"labels(rows=true, cols=pred)": ALL_STATUSES,
                             "matrix": confusion_matrix(y_true, y_pred, labels=ALL_STATUSES).tolist()},
        "report_scores": score_errors,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels_dir", type=Path, default=BASE_DIR / "datasets" / "labels")
    parser.add_argument("--pdf_dirs", type=Path, nargs="+",
                        default=[BASE_DIR / "library", BASE_DIR / "datasets" / "reports"])
    parser.add_argument("--include_drafts", action="store_true",
                        help="also count unreviewed AI-drafted labels (source=ai_draft); off by default")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "models" / "eval" / "report_eval.json")
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.WARNING)

    server.state["requirements"] = server.load_requirements()
    reports, skipped_drafts = [], 0
    for f, record in load_labels(args.labels_dir):
        if not args.include_drafts:
            kept = {k: v for k, v in record["labels"].items() if v.get("source", "human") != "ai_draft"}
            skipped_drafts += len(record["labels"]) - len(kept)
            record["labels"] = kept
            if not kept:
                continue
        try:
            reports.append((f, record, find_pdf(record["metadata"], [d for d in args.pdf_dirs if d.exists()])))
        except FileNotFoundError as e:
            print(f"  skipping {f.name}: {e}")
    if skipped_drafts:
        print(f"Ignoring {skipped_drafts} unreviewed AI-drafted labels (confirm them in label.html, "
              f"or pass --include_drafts).")
    if not reports:
        sys.exit("No human-confirmed labels matched to a PDF.")
    n_labels = sum(len(r["labels"]) for _, r, _ in reports)
    print(f"{len(reports)} labelled reports, {n_labels} labels\n")

    results = [evaluate(reports)]

    header = f"{'config':32} {'acc':>5} {'mF1':>5} {'±1':>5} {'scoreMAE':>8} {'evHit':>6} {'s/rep':>6}"
    print(header + "\n" + "-" * len(header))
    for r in results:
        ev = f"{r['evidence_hit_rate']:.2f}" if r["evidence_hit_rate"] is not None else "  -"
        mae = f"{r['score_mae']:8.1f}" if r["score_mae"] is not None else "       -"
        print(f"{r['config']:32} {r['accuracy']:5.2f} {r['macro_f1']:5.2f} {r['within_one_step']:5.2f} "
              f"{mae} {ev:>6} {r['seconds_per_report']:6.1f}")
    for r in results:
        print(f"\n{r['config']} - per report (labelled vs predicted score):")
        for e in r["report_scores"]:
            print(f"  {e['report'][:50]:50} {e['labelled_score']:5.1f}  {e['predicted_score']:5.1f}")
        print("  confusion (rows = label, cols = predicted: Not / Partial / Disclosed / Not assessable):")
        for name, row in zip(ALL_STATUSES, r["confusion_matrix"]["matrix"]):
            print(f"    {name:20} {row}")
    if n_labels < 50:
        print(f"\nNote: only {n_labels} labels - treat these numbers as indicative, not conclusive.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved details to {args.output}")


if __name__ == "__main__":
    main()
