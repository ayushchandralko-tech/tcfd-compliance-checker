# TCFD Compliance Calculator

A simple, single-page TCFD (Task Force on Climate-related Financial Disclosures) compliance assessment tool.

## 🎯 Overview

This project provides two components:

1. **Frontend Calculator**: A standalone web-based calculator for manual TCFD compliance assessment
2. **Backend API**: An automated ML-powered API for analyzing sustainability reports

## ✨ Features

### Frontend Calculator
- **Single Page Design**: Clean, focused interface with no sidebar or tabs
- **Company Details**: Company name and reporting year input
- **11 TCFD Disclosures**: All four pillars in one scrollable list
- **Status Selector**: Compliant / Partial / Non-compliant buttons
- **Automatic Calculation**: Instant percentage score calculation
- **Score Summary**: Overall score and status counts
- **Auto-fill from PDF**: Upload a report to pre-fill statuses with page-cited evidence (needs the backend)
- **Export Report**: Formatted HTML report (print or save as PDF) with score, pillar summary, every disclosure's status, automated suggestion, page-cited evidence passages and reviewer notes; plus a JSON data export
- **Responsive Design**: Works on desktop and mobile

### Backend API (Optional)
- **PDF Analysis**: Automated compliance assessment from sustainability reports
- **Evidence retrieval**: TF-IDF passage ranking + keyword coverage per disclosure, with page numbers (baseline classifier prediction included for comparison)
- **RESTful API**: Simple endpoints for compliance assessment
- **Evidence-Based**: Provides supporting evidence snippets

## 🚀 Quick Start

### Frontend Calculator (Recommended)

The frontend calculator is a standalone tool that requires no backend.

```bash
cd frontend
npm install
npm start
```

Access at: http://localhost:8650

### Backend API (Optional)

For automated PDF analysis:

```bash
cd backend
pip install -r requirements.txt
python train_baseline.py --data_path ./datasets/tcfd_training_sample.json --output_dir ./models/tcfd_classifier
python tcfd_api_server.py
```

Access at: http://localhost:8250

## 📊 TCFD Framework

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

## 📁 Project Structure

```
InferESG/
├── frontend/                      # Web-based calculator
│   ├── src/
│   │   ├── index.html            # Main HTML file
│   │   └── app.js                # JavaScript logic
│   ├── package.json              # Dependencies
│   └── README.md                 # Frontend documentation
├── backend/                       # ML-powered API (optional)
│   ├── tcfd_api_server.py        # FastAPI server
│   ├── train_baseline.py         # Training script
│   ├── create_sample_data.py     # Sample data generator
│   ├── library/                  # TCFD knowledge base
│   ├── datasets/                 # Training data
│   ├── models/                   # Trained models
│   └── README.md                 # Backend documentation
├── QUICKSTART.md                  # Quick start guide
└── README.md                      # This file
```

## 📖 Usage

### Frontend Calculator

1. Open http://localhost:8650
2. Enter company name and reporting year
3. For each TCFD disclosure, click Compliant, Partial, or Non-compliant
4. View the automatically calculated compliance score
5. Expand a card to see the evidence (what TCFD asks, matched terms, page-cited passages) and add reviewer notes
6. Click "Export report" to download an HTML report with all evidence (use its Print / Save as PDF button for a PDF)

### Backend API

```bash
# Health check
curl http://localhost:8250/health

# Get TCFD requirements
curl http://localhost:8250/tcfd/requirements

# Assess compliance
curl -X POST http://localhost:8250/tcfd/assess \
  -F "file=@your_report.pdf"
```

## 🧮 Scoring Formula

- **Compliant**: 1 point
- **Partial**: 0.5 points
- **Non-compliant**: 0 points

```
Score = (Weighted points / 11) × 100
```

## 📚 Documentation

- **frontend/README.md** - Frontend calculator documentation
- **backend/README.md** - Backend API documentation
- **QUICKSTART.md** - Quick start guide
- **LABELLING.md** - Building a labelled test set and evaluating against it

## 🚀 Technology Stack

### Frontend
- **HTML5**: Structure
- **CSS3**: Custom properties (design tokens), responsive grid layout
- **JavaScript (Vanilla)**: Logic and calculations
- **http-server**: Static file serving

### Backend (Optional)
- **Python 3.10+**: Backend language
- **FastAPI**: Web framework
- **scikit-learn**: Machine learning
- **joblib**: Model persistence
- **pypdf**: PDF parsing

## ⚠️ Notes

- The frontend calculator is a standalone tool for manual assessment
- The backend API is optional and provides automated analysis
- The backend uses synthetic sample data for testing
- Real-world performance will vary with actual labeled data

## 🤝 Contributing

This project is adapted from InferESG (ScottLogic). Contributions are welcome!

Areas for contribution:
- Improve UI/UX
- Implement local storage for saving assessments
- Add historical tracking
- Improve backend model performance

## 📄 License

Based on InferESG (ScottLogic). Adapted for TCFD compliance checking.
