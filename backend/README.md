# TCFD Compliance Checker - Backend

A focused backend API for TCFD (Task Force on Climate-related Financial Disclosures) compliance assessment using machine learning.

## Overview

FastAPI server that assesses sustainability / TCFD report PDFs against the 11 TCFD recommended disclosures,
criterion by criterion (34 criteria), and returns for each disclosure an AI suggestion with a reason, the
criterion results with page-cited evidence and missing-evidence guidance, evidence coverage and
classification confidence. See QUICKSTART.md, "How the automated assessment works", for the method.

Main modules: `assessment.py` (pipeline), `tcfd_api_server.py` (API), `passage_features.py` (embeddings),
`evaluate_reports.py` (evaluation against human labels).

## Project Structure

```
backend/
├── tcfd_api_server.py          # Main FastAPI server
├── train_baseline.py           # Training script for baseline model
├── create_sample_data.py       # Sample data generator
├── library/
│   ├── tcfd_requirements.json  # TCFD knowledge base (11 recommendations)
│   └── catalogue.json          # Framework catalog
├── datasets/
│   └── tcfd_training_sample.json  # Sample training data (100 samples)
└── models/
    └── tcfd_classifier/
        ├── baseline_model.pkl     # Trained baseline model
        └── baseline_results.json   # Training results
```

## Installation

### Prerequisites

- Python 3.10+
- pip

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Train the Model

```bash
python train_baseline.py --data_path ./datasets/tcfd_training_sample.json --output_dir ./models/tcfd_classifier
```

This will:
- Train a TF-IDF + Logistic Regression classifier
- Evaluate performance
- Save the trained model to `models/tcfd_classifier/baseline_model.pkl`

### 2. Start the API Server

```bash
python tcfd_api_server.py
```

The server will start at http://localhost:8250

### 3. Test the API

```bash
# Health check
curl http://localhost:8250/health

# Get TCFD requirements
curl http://localhost:8250/tcfd/requirements

# Assess compliance
curl -X POST http://localhost:8250/tcfd/assess \
  -F "file=@your_report.pdf"
```

## API Endpoints

### GET /health
Health check endpoint. Returns service status and model loading status.

### GET /tcfd/requirements
Returns the TCFD knowledge base with all 11 recommendations across 4 pillars.

### POST /tcfd/assess

Assesses an uploaded PDF (multipart field `file`).

Returns `metadata` (detected company, reporting year), `summary` (status counts including
`not_assessable`, `compliance_score`, `evidence_coverage_score`, criteria supported / partly / missing)
and `compliance_checklist`: per disclosure `status`, `reason`, `coverage`, `confidence`, and `criteria`
(each with `result`, `reason`, `evidence` {page, text, context, relevance, signals_found} and
`missing_guidance`). `method_details` documents every measure. Unreadable PDFs are returned as
Not assessable rather than rejected; non-PDF files return 400.

### POST /tcfd/compare

Compares the criterion-based status with the legacy synthetic-data baseline classifier (diagnostic only).

### POST /tcfd/labeling-task
Returns the retrieved evidence per requirement with a suggested label and an empty `label` field, for manual labeling.

## Training

### Passage models on public labelled data (used by the API)

```bash
python train_external.py
```

Trains two logistic-regression models from `datasets/external/` (see its README for sources and licences), comparing TF-IDF features, sentence embeddings (`all-MiniLM-L6-v2`) and both combined, and saves the best to `models/tcfd_external/`. Use `--features tfidf` for fast TF-IDF-only models.

| Model | Data | Evaluation | TF-IDF | Embeddings | **Both (selected)** |
|---|---|---|---|---|---|
| Pillar (none/governance/strategy/risk/metrics) | ClimateBERT tcfd_recommendations, 1,300 paragraphs | official 400-paragraph test split, macro-F1 | 0.60 | 0.68 | **0.71** (accuracy 0.75) |
| Disclosure (G.1 ... M.3) | rexarski TCFD_disclosure, 537 sentences | stratified 5-fold CV, macro-F1 | 0.43 | 0.43 | **0.46** (0.63 within the correct pillar) |

Weakest classes: pillar `risk` (F1 0.57), disclosures M.2, R.2, S.2 (F1 about 0.35).

**Speed:** with embeddings a 40-page report takes ~8 s on CPU (vs ~1 s with TF-IDF only).

### Synthetic baseline (legacy)

### Sample Data

The repository includes synthetic sample data for testing:
- 100 labeled samples
- 3 classes: Disclosed, Partially disclosed, Not disclosed
- Used for smoke testing only

### Real Data Training

For production use:

1. Collect 20-40 real sustainability reports
2. Use the labeling pipeline to create structured tasks
3. Manually label each requirement
4. Train on real data for accurate performance

```bash
python train_baseline.py --data_path ./datasets/real_training_data.json --use_cross_validation
```

## Model Performance

### Current Baseline (Synthetic Data)
- Accuracy: 100%
- Macro F1: 100%
- Per-Class F1: 100% for all classes

**Note:** Perfect scores are expected with synthetic data. Real-world performance will vary.

### Expected Real-World Performance
With properly labeled real data:
- Target: 70-85% accuracy
- Target: 0.65-0.80 macro F1
- Per-class precision/recall should be balanced

## TCFD Framework

The system assesses compliance against 11 TCFD recommendations across 4 pillars:

### Governance (2)
- G.1: Board oversight of climate-related risks and opportunities
- G.2: Management's role in assessing and managing them

### Strategy (3)
- S.1: Climate risks and opportunities (short, medium, long term)
- S.2: Impact on business, strategy and financial planning
- S.3: Resilience of strategy under different scenarios, incl. 2°C or lower

### Risk Management (3)
- R.1: Processes for identifying and assessing climate risks
- R.2: Processes for managing climate risks
- R.3: Integration into overall risk management

### Metrics & Targets (3)
- M.1: Metrics used to assess climate risks and opportunities
- M.2: Scope 1, 2 and (if appropriate) 3 GHG emissions
- M.3: Targets and performance against targets

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

## Future Improvements

- Label real reports (via `/tcfd/labeling-task`) and train/evaluate on them
- Calibrate the evidence thresholds against labelled data
- Embedding-based retrieval (sentence-transformers) instead of TF-IDF
- Train a transformer classifier (ClimateBERT/DistilBERT)
- Support additional frameworks (ISSB/IFRS S2, CSRD/ESRS)

## Documentation

- **QUICKSTART.md** - Quick start guide for the full application
- **TCFD_ADAPTER_README.md** - Comprehensive technical documentation
- **library/tcfd_requirements.json** - TCFD knowledge base

## License

Based on InferESG (ScottLogic). Adapted for TCFD compliance checking.
