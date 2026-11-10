# TCFD Compliance Checker - Adaptation Guide

> **Note:** This document describes the original InferESG-integrated design (`src/classifier/`, `src/agents/tcfd_agent.py`, Docker Compose, transformer training). Those modules have since been removed in favour of the standalone `backend/tcfd_api_server.py` and the static frontend calculator. See [QUICKSTART.md](QUICKSTART.md) for the current setup; this file is kept for design background.

This document describes the TCFD (Task Force on Climate-related Financial Disclosures) compliance checker that has been integrated into the InferESG platform.

## Overview

The TCFD compliance checker is an automated system that assesses sustainability reports against the 11 TCFD recommendations across four pillars: Governance, Strategy, Risk Management, and Metrics & Targets. It uses fine-tuned machine learning models to classify disclosure status as:
- **Disclosed**: Fully addressed with clear, specific information
- **Partially disclosed**: Some information provided but incomplete or vague
- **Not disclosed**: No relevant information found

## Architecture

### Components

1. **Data Processor** (`src/classifier/data_processor.py`)
   - PDF parsing and text extraction
   - Text chunking for semantic retrieval
   - Embedding generation using sentence-transformers
   - Semantic retrieval of relevant report chunks for each TCFD requirement

2. **Model Trainer** (`src/classifier/model_trainer.py`)
   - Fine-tunes transformer models (DistilBERT/ClimateBERT) for disclosure classification
   - Supports k-fold cross-validation
   - Implements per-class precision/recall/F1 metrics
   - Calibrated confidence scores

3. **Baseline Classifier** (`src/classifier/baseline_classifier.py`)
   - TF-IDF + Logistic Regression baseline
   - Provides classical ML comparison
   - Feature importance analysis

4. **Labeling Pipeline** (`src/classifier/labeling_pipeline.py`)
   - Generates labeling tasks from PDF reports
   - Supports LLM-assisted pre-labeling
   - Converts labeled data to training format
   - Merges multiple datasets

5. **Evaluator** (`src/classifier/evaluation.py`)
   - Per-class precision, recall, F1-score
   - Confusion matrix visualization
   - Model comparison reports
   - Per-requirement analysis

6. **TCFD Agent** (`src/agents/tcfd_agent.py`)
   - Integrates classifier into InferESG's multi-agent system
   - Provides natural language interface for TCFD queries
   - Formats compliance results for display

## TCFD Requirements

The system assesses compliance against 11 TCFD recommendations:

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

## Setup

### Prerequisites

1. Python 3.9+
2. Docker (for full InferESG deployment)
3. GPU (recommended for transformer training)

### Installation

1. Navigate to the backend directory:
```bash
cd InferESG/backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/Scripts/activate  # On Windows
# or
source venv/bin/activate  # On Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Configuration

The TCFD requirements are stored in `backend/library/tcfd_requirements.json`. This file contains:
- All 11 TCFD recommendations
- Keywords for semantic matching
- Detailed descriptions and requirements

## Usage

### 1. Data Collection and Labeling

#### Create Synthetic Sample Data (for testing)
```bash
cd backend
python -c "
from src.classifier import LabelingPipeline
pipeline = LabelingPipeline()
pipeline.create_sample_training_data(num_samples=100, output_path='./datasets/tcfd_training_sample.json')
"
```

#### Generate Labeling Task from Real Report
```bash
cd backend
python -c "
from src.classifier import LabelingPipeline
pipeline = LabelingPipeline()
task = pipeline.generate_labeling_task(
    pdf_path='./library/AstraZeneca-Sustainability-Report-2023.pdf',
    output_path='./datasets/labeling_task_example.json'
)
"
```

This creates a structured labeling task with relevant chunks for each requirement. Review and label each requirement as "Disclosed", "Partially disclosed", or "Not disclosed".

#### Convert Labeled Task to Training Data
```bash
cd backend
python -c "
from src.classifier import LabelingPipeline
pipeline = LabelingPipeline()
pipeline.convert_to_training_data(
    labeled_task=pipeline.load_labeling_task('./datasets/labeling_task_example.json'),
    output_path='./datasets/tcfd_training_data.json'
)
"
```

### 2. Training the Models

**Note**: If you encounter TensorFlow/protobuf import errors, use the standalone `train_baseline.py` script for baseline training instead of the full training script.

#### Train Baseline (Standalone - Recommended for Testing)
```bash
cd backend
python train_baseline.py \
    --data_path ./datasets/tcfd_training_data.json \
    --use_cross_validation \
    --n_splits 5 \
    --max_features 5000
```

#### Train Both Models with Cross-Validation
```bash
cd backend
python train_tcfd_classifier.py \
    --data_path ./datasets/tcfd_training_data.json \
    --model_type both \
    --use_cross_validation \
    --n_splits 5 \
    --epochs 3 \
    --batch_size 16
```

#### Train Only Transformer
```bash
python train_tcfd_classifier.py \
    --data_path ./datasets/tcfd_training_data.json \
    --model_type transformer \
    --transformer_model distilbert-base-uncased \
    --epochs 3
```

#### Train Only Baseline (Full Script)
```bash
python train_tcfd_classifier.py \
    --data_path ./datasets/tcfd_training_data.json \
    --model_type baseline \
    --max_features 5000
```

#### Use ClimateBERT (Domain-Specific Model)
```bash
python train_tcfd_classifier.py \
    --data_path ./datasets/tcfd_training_data.json \
    --model_type transformer \
    --transformer_model climatebert/distilbert-base-uncased-climate-sentence \
    --epochs 3
```

### 3. Running the Application

#### Start with Docker Compose (Recommended)
```bash
cd InferESG
docker compose up
```

The application will be available at:
- Frontend: http://localhost:8650
- Backend API: http://localhost:8250
- Neo4j Browser: http://localhost:7474

#### Start Backend Locally
```bash
cd InferESG/backend
uvicorn src.api:app --port 8250
```

### 4. API Endpoints

#### Assess TCFD Compliance
```bash
curl -X POST "http://localhost:8250/tcfd/assess" \
  -F "file=@/path/to/report.pdf" \
  -F "use_transformer=true"
```

Response:
```json
{
  "framework": "TCFD",
  "model_type": "transformer",
  "summary": {
    "total_requirements": 11,
    "disclosed": 7,
    "partially_disclosed": 2,
    "not_disclosed": 2,
    "disclosed_percentage": 63.6,
    "average_confidence": 0.85
  },
  "compliance_checklist": {
    "G.1": {
      "requirement_id": "G.1",
      "pillar": "Governance",
      "title": "Governance Disclosure",
      "description": "...",
      "status": "Disclosed",
      "confidence": 0.92,
      "evidence": "...",
      "retrieval_score": 0.87
    },
    ...
  }
}
```

#### Compare Models
```bash
curl -X POST "http://localhost:8250/tcfd/compare" \
  -F "file=@/path/to/report.pdf"
```

#### Create Labeling Task
```bash
curl -X POST "http://localhost:8250/tcfd/labeling-task" \
  -F "file=@/path/to/report.pdf"
```

#### Get TCFD Requirements
```bash
curl "http://localhost:8250/tcfd/requirements"
```

### 5. Using the Chat Interface

Start the application and use the chat interface at http://localhost:8650. The TCFD Agent can help with queries like:

- "Assess the TCFD compliance of this report"
- "What are the TCFD requirements?"
- "Compare the transformer and baseline predictions"
- "Which requirements are not disclosed?"

## Evaluation

### Training Results

After training, results are saved to `./models/tcfd_classifier/training_results.json` and include:
- Per-class precision, recall, F1-score
- Macro-averaged metrics
- Confusion matrix (if visualization enabled)
- Model comparison report

### Key Metrics

The system reports per-class metrics to handle class imbalance:
- **Precision**: Of all predictions for a class, how many were correct
- **Recall**: Of all actual instances of a class, how many were predicted correctly
- **F1-score**: Harmonic mean of precision and recall

Example results:
```
Not disclosed: Precision=0.85, Recall=0.78, F1=0.81
Partially disclosed: Precision=0.72, Recall=0.68, F1=0.70
Disclosed: Precision=0.89, Recall=0.92, F1=0.90
Macro F1: 0.80
```

## File Structure

```
InferESG/backend/
├── src/
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── tcfd_classifier.py          # Main classifier orchestrator
│   │   ├── data_processor.py           # PDF parsing, chunking, embeddings
│   │   ├── model_trainer.py            # Transformer fine-tuning
│   │   ├── baseline_classifier.py      # TF-IDF baseline
│   │   ├── labeling_pipeline.py        # Data collection and labeling
│   │   └── evaluation.py               # Metrics and evaluation
│   ├── agents/
│   │   └── tcfd_agent.py               # TCFD agent for chat interface
│   └── api/
│       └── app.py                      # API endpoints
├── library/
│   ├── tcfd_requirements.json         # TCFD knowledge base
│   └── catalogue.json                  # Updated with TCFD
├── datasets/
│   └── tcfd_training_data.json         # Training data (to be created)
├── models/
│   └── tcfd_classifier/               # Trained models
├── train_tcfd_classifier.py            # Full training script (may have TensorFlow conflicts)
├── train_baseline.py                  # Standalone baseline training (no TensorFlow)
├── create_sample_data.py              # Sample data generator (no TensorFlow)
└── requirements.txt                   # Updated dependencies
```

## Next Steps

1. **Collect Training Data**: Gather 20-40 real sustainability reports and label them
2. **Train Models**: Run the training script with cross-validation
3. **Evaluate Performance**: Review per-class metrics and confusion matrices
4. **Test on New Reports**: Assess compliance on unseen reports
5. **Iterate**: Refine labeling and hyperparameters based on results

## Integration with InferESG

The TCFD classifier is integrated into InferESG's multi-agent architecture:
- **TCFDAgent**: Added to the chat agent roster
- **Router**: Can route TCFD-related queries to the TCFD agent
- **API**: Dedicated endpoints for TCFD-specific operations
- **Frontend**: Can be extended to display TCFD compliance checklists

## Limitations and Future Work

### Current Limitations
- Requires manually labeled training data
- Trained on English-language reports only
- Does not handle structured/tabular data (XBRL)
- Limited to TCFD framework (not CSRD/ESRS/GRI)

### Future Extensions
1. **Multi-framework Support**: Extend to CSRD/ESRS, GRI
2. **Graph-based Rules**: Represent overlapping requirements as a knowledge graph
3. **LLM Explainability**: Add human-readable justifications with page citations
4. **Automated Labeling**: Improve LLM-assisted labeling pipeline
5. **Multi-language**: Support reports in other languages

## Troubleshooting

### Common Issues

**Issue**: "Trained models not found"
- **Solution**: Run the training script first: `python train_baseline.py` or `python train_tcfd_classifier.py`

**Issue**: ImportError for tensorflow/protobuf when running train_tcfd_classifier.py
- **Solution**: This is a known conflict between TensorFlow and protobuf versions. Use the standalone `train_baseline.py` script for baseline training instead. The TCFD classifier doesn't require TensorFlow. If you need transformer training, consider using a separate virtual environment without TensorFlow.

**Issue**: CUDA out of memory during training
- **Solution**: Reduce batch size or use CPU training

**Issue**: Poor classification performance
- **Solution**: Increase training data, try ClimateBERT model, adjust hyperparameters

**Issue**: PDF parsing fails
- **Solution**: Ensure PDF is text-based (not scanned images)

## References

- [TCFD Recommendations](https://www.fsb-tcfd.org/recommendations/)
- [ClimateBERT](https://github.com/climatebert/climatebert)
- [InferESG](https://github.com/ScottLogic/InferESG)
- [Original Proposal](./ESG_Compliance_Checker_Proposal.pdf)

## License

This adaptation follows the same license as the InferESG project (see LICENCE.md).
