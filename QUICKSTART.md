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

Assessment is criterion-level (`backend/assessment.py`; criteria in `backend/library/tcfd_requirements.json`;
tables in `backend/tables.py`):

1. **PDF processing**: text per page with running headers removed, split into passages of complete
   sentences with neighbouring sentences as context. **Tables** are rebuilt from the PDF layout with row
   labels, units, column headings (e.g. FY 2025-26) and page numbers, including wrapped labels and section
   rows. Company name and reporting year are detected from PDF metadata, title pages and file name.
2. **Hybrid retrieval** for each of the 34 criteria: candidates are the union of the top **semantic** matches
   (sentence embeddings), the top **keyword** matches (TF-IDF) and the top **table** matches. Relevance =
   0.8 × semantic + 0.2 × keyword for text, 0.7 / 0.3 for tables and number-dense passages.
3. **Evidence check per criterion**: every required evidence signal must appear within 3 adjacent sentences
   (e.g. G.1.a: *board body* + *frequency* + *climate*). Statements of plans, intentions or training
   ("will", "plans to", "feasibility", "workshop", items in a "focus areas include:" list) are **not**
   counted as evidence of implementation.
   - *Supported* (relevance ≥ 0.40, tables ≥ 0.32), *Partly supported*, or *Not found*
   - each result has its own **confidence** (High / Medium / Low) and the **exact supporting sentences** or table
4. **Classification** from the **mandatory** criteria only (optional criteria change coverage, never status):
   - Compliant: every mandatory criterion has direct supporting evidence
   - Partially compliant: at least one mandatory criterion supported, others missing
   - Non-compliant: no mandatory criterion supported (partial or plan-only evidence is not enough)
   - Not assessable: document unreadable (scanned) or too short
5. **Human review**: accept each AI suggestion or change it with a reason; every action is in the audit trail.

| Measure | Meaning |
|---|---|
| Retrieval relevance (0-1) | how closely a passage or table matches a criterion |
| Criterion confidence | High / Medium / Low per criterion, from evidence strength |
| Evidence coverage | (supported + 0.5 × partly) ÷ criteria, per disclosure and overall |
| Disclosure confidence | from the confidence of its mandatory criteria |
| Compliance score | (Compliant × 1 + Partial × 0.5) ÷ assessable disclosures, shown with the actual calculation |

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

- Evidence checks are pattern-based on top of hybrid retrieval: they verify that the right *kinds* of
  information appear together, not that a disclosure is complete or of high quality. Read the quotes.
- Signals can still co-occur by accident within 3 sentences (e.g. a board sentence next to a management
  sentence); such results usually carry Medium or Low confidence.
- Table reconstruction relies on pypdf's layout mode: tables with text-only cells, rotated text or
  designed infographics (e.g. the APAR integrated report) are read as ordinary text instead.
- Against the (unreviewed) AI-drafted labels for EBRD, Ujjivan and APAR: 73% status agreement,
  macro-F1 0.80, average score error 10.6 points. Thresholds were tuned on EBRD 2023, AstraZeneca 2023
  and Ujjivan 2025-26, so those results are in-sample. Confirm the labels to get a real measurement.
- Large reports take 25-75 s on CPU.
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
