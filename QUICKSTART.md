# TCFD Compliance Checker - Quick Start

## Prerequisites

- Python 3.10+
- Node.js 16+

## 1. Backend API (needed for PDF auto-fill)

```bash
cd backend
pip install -r requirements.txt
python tcfd_api_server.py
```

- API: http://localhost:8250
- Interactive docs: http://localhost:8250/docs

Trained passage models (pillar + disclosure) are loaded from `models/tcfd_external/`. To retrain them on the public labelled datasets in `datasets/external/`:

```bash
python train_external.py                    # compares TF-IDF, embeddings and both; keeps the best
python train_external.py --features tfidf   # fast models only (~1 s per report instead of ~8 s)
```

The selected models use sentence embeddings (`all-MiniLM-L6-v2`, ~90 MB, downloaded to the Hugging Face cache on first use).

The older synthetic-data baseline classifier is loaded from `models/tcfd_classifier/baseline_model.pkl`. To (re)train it:

```bash
python train_baseline.py --data_path ./datasets/tcfd_training_sample.json --output_dir ./models/tcfd_classifier
```

## 2. Frontend calculator

```bash
cd frontend
npm install
npm start
```

Open http://localhost:8650.

## 3. Using it

1. Enter the company name and reporting year.
2. (Optional) Choose a sustainability report PDF and click **Analyse PDF**. Each of the 11 disclosures is pre-filled with a suggested status, an evidence-strength percentage and the page numbers the evidence came from. Click **Show evidence** to read the passages.
3. Review each suggestion and click Compliant / Partial / Non-compliant to override it. Overridden items are marked.
4. Click **Export report** for a formatted HTML report with every disclosure's status, suggestion, page-cited evidence passages and your notes. Open it and use **Print / Save as PDF** for a PDF.

The calculator also works without the backend for fully manual assessment.

## Labelling and evaluation

Open http://localhost:8650/label.html to label reports per disclosure, then run
`python evaluate_reports.py` in `backend/`. See [LABELLING.md](LABELLING.md).

## How the automated assessment works

1. Text is extracted page by page with `pypdf`.
2. Pages are split into overlapping ~900-character passages.
3. For each disclosure, passages are ranked by a mix of TF-IDF similarity to the requirement text (`library/tcfd_requirements.json`) and the trained models' probability that the passage belongs to that disclosure (P(pillar) x P(disclosure | pillar)). Passages that never mention climate/emissions are down-weighted.
4. Keyword coverage (45%), similarity (25%) and model support (30%) across the top 3 passages give an evidence score:
   - >= 0.55: Disclosed
   - >= 0.30: Partially disclosed
   - otherwise: Not disclosed
5. If the baseline classifier is loaded, its prediction on the top passage is returned in the `classifier` field for comparison.

## API examples

```bash
curl http://localhost:8250/health
curl http://localhost:8250/tcfd/requirements
curl -X POST http://localhost:8250/tcfd/assess -F "file=@report.pdf"
curl -X POST http://localhost:8250/tcfd/compare -F "file=@report.pdf"
curl -X POST http://localhost:8250/tcfd/labeling-task -F "file=@report.pdf"
curl http://localhost:8250/tcfd/labels      # saved label files
```

`/tcfd/labeling-task` returns the retrieved passages per requirement with a suggested label and an empty `label` field, ready for manual labeling to build real training data.

## Limitations

- The status is a keyword/similarity heuristic, not a judgement of disclosure quality. Treat it as a starting point for review.
- The passage models are modest: pillar macro-F1 0.71 on the ClimateBERT test set; 11-way disclosure macro-F1 0.46 (0.63 accuracy within the right pillar) in 5-fold CV. See `models/tcfd_external/results.json`.
- With embeddings, analysis takes ~8 s for a 40-page report on CPU.
- Thresholds are hand-set on 3 reports; there is no labelled end-to-end evaluation set yet.
- The trained models use CC BY-NC-SA data, so they are for non-commercial use only.
- The `classifier` field (synthetic-data baseline) is not reliable on real reports.
- Scanned (image-only) PDFs return an error; run OCR first.

## Tests

```bash
cd backend
pytest                  # all tests (~25 s; loads the embedding model)
pytest -m "not slow"    # fast tests only (what CI runs)
```

## Troubleshooting

**"Could not reach the backend"** in the UI: start `python tcfd_api_server.py` in `backend/`.

**Port already in use** (Windows):
```bash
netstat -ano | findstr :8250
taskkill /PID <PID> /F
```
