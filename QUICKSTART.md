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

1. Optionally enter the company name and reporting year (e.g. `2023` or `2025-26`). Empty fields are filled from the report.
2. Choose a sustainability or TCFD report PDF and click **Analyse report**.
   - If the year you entered does not match the year detected in the report, a warning appears; correct it
     or tick the confirmation box (export is blocked until you do).
3. Each disclosure shows the **AI suggestion** with its reason, criteria coverage and confidence.
   Click **Review evidence** to see each criterion's result, the evidence passage (page, relevance, signals,
   surrounding context), **Open page ↗** to jump to the PDF page, and what is missing.
4. **Accept** the suggestion, or choose a different status and give a **reason** (required).
5. **Export report**: HTML report with the compliance score and evidence coverage, a pillar dashboard,
   AI suggestion vs final status and review decision per disclosure, criterion-level evidence with
   missing-evidence guidance, the review audit trail and the method. Use **Print / Save as PDF** for a PDF.
   **Download data (JSON)** exports the same content.

The calculator also works without the backend for manual assessment.

## Labelling and evaluation

Open http://localhost:8650/label.html to label reports per disclosure, then run
`python evaluate_reports.py` in `backend/`. See [LABELLING.md](LABELLING.md).

## How the automated assessment works

Assessment is criterion-level (`backend/assessment.py`, criteria in `backend/library/tcfd_requirements.json`):

1. **PDF processing**: text is extracted per page; running page headers are removed; pages are split into
   passages of complete sentences (~700 characters), keeping the neighbouring sentences as context. The
   company name and reporting year are detected from PDF metadata, the title pages and the file name.
2. **Retrieval**: each of the 34 criteria (1-4 per disclosure) has its own query. Passages are ranked by
   **retrieval relevance** = 0.8 × semantic similarity (sentence embeddings) + 0.2 × lexical similarity (TF-IDF).
3. **Criterion check**: the 12 most relevant passages are checked for the evidence the criterion needs
   (e.g. G.1.a needs a *board body*, a *frequency* and a *climate* reference), all within 3 adjacent sentences.
   - *Supported*: a passage with relevance ≥ 0.40 contains every signal, and is not only a plan or a training mention
   - *Partly supported*: some signals, weak relevance, or plan/training only
   - *Not found*: nothing relevant carries the evidence (with guidance on what to disclose)
4. **AI suggestion** per disclosure, with a reason:
   - Compliant: every essential criterion supported
   - Partially compliant: some criteria supported or partly supported
   - Non-compliant: no supporting evidence
   - Not assessable: document unreadable (scanned) or too short; never scored as non-compliant
5. **Human review**: each suggestion is accepted or changed; a change needs a reason; all actions go to an audit trail.

Three measures are kept separate and never blended:

| Measure | Meaning |
|---|---|
| Retrieval relevance (0-1) | how closely a passage matches a criterion's query |
| Evidence coverage | per disclosure: (supported + 0.5 × partly) ÷ criteria; overall: across all criteria |
| Classification confidence | High / Medium / Low, by how many criterion results are borderline |

The **compliance score** uses the final (reviewed) statuses: (Compliant + 0.5 × Partial) ÷ assessable disclosures.

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

- Evidence checks are pattern-based on top of semantic retrieval: they verify that the right *kinds* of
  information appear together, not that the disclosure is complete or high quality. Read the evidence.
- Thresholds were calibrated on the EBRD 2023 TCFD report and AstraZeneca 2023 sustainability report.
  Against the (unreviewed) AI-drafted labels for EBRD, Ujjivan and APAR, status agreement is 70%; the main
  disagreement is the pipeline calling Compliant where the drafts said Partial. Confirm the labels in the
  labelling tool to get a real measurement (`python evaluate_reports.py`).
- Documents that *describe* disclosure requirements (e.g. GRI standards) still score moderately.
- Integrated reports that refer to a separate TCFD report are assessed only on their own content.
- Large reports take 30-130 s on CPU (sentence embeddings for every passage).
- Scanned PDFs are reported as Not assessable; run OCR first.

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
