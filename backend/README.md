# TCFD Compliance Checker - Backend

A focused backend API for TCFD (Task Force on Climate-related Financial Disclosures) compliance assessment using machine learning.

## Overview

This backend provides a FastAPI server that:
- Accepts sustainability report PDFs
- Assesses compliance against 11 TCFD recommendations
- Uses a trained TF-IDF + Logistic Regression classifier
- Returns structured compliance checklists with confidence scores

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
Assesses an uploaded PDF against the 11 TCFD recommended disclosures.

**Parameters:** `file` - PDF file (multipart)

**Returns:**
- `summary`: counts per status, `compliance_score` (Disclosed = 1, Partial = 0.5), pages read
- `compliance_checklist`: per requirement - `status`, `confidence` (evidence score 0-1), `keyword_coverage`,
  `matched_keywords`, `retrieval_score`, top-3 `evidence` passages with page numbers, and the baseline
  `classifier` prediction (if a model is loaded)

**How status is decided:** passages are ranked by TF-IDF similarity to the requirement text and keywords
in `library/tcfd_requirements.json`; evidence score = 0.6 x keyword coverage + 0.4 x normalised similarity
(halved if the passages never mention climate/emissions). >= 0.55 Disclosed, >= 0.30 Partial, else Not disclosed.

### POST /tcfd/compare
Compares the evidence-based status with the baseline classifier's prediction per requirement and reports the agreement rate.

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

1. **Heuristic status**: keyword coverage + TF-IDF similarity measures whether a topic is discussed, not the quality of the disclosure. Documents *about* climate disclosure (e.g. GRI sector standards) also score moderately.
2. **Classifier**: trained on 100 synthetic sentences; its predictions are not reliable on real reports.
3. **PDF parsing**: text-only extraction; scanned PDFs return HTTP 422.

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
