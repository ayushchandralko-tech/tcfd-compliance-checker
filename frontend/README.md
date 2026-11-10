# TCFD Compliance Calculator - Frontend

A simple, single-page TCFD compliance assessment tool with no backend dependencies for the basic calculator.

## Overview

This is a standalone web application that allows users to:
- Enter company details
- Select compliance status for 11 TCFD disclosures
- Automatically calculate overall compliance score
- Export assessment reports

## Features

- **Single Page Design**: No sidebar, no tabs, just the essential calculator
- **Company Details**: Company name and reporting year input
- **11 TCFD Disclosures**: All four pillars in one scrollable list
- **Status Selector**: Compliant / Partial / Non-compliant buttons
- **Automatic Calculation**: Instant percentage score calculation
- **Score Summary**: Overall score and status counts
- **Auto-fill from PDF**: Upload a report; the backend (`localhost:8250`) suggests a status per disclosure with page-cited evidence, which you can override
- **Export Report**: Download assessment as text file
- **Responsive Design**: Works on desktop and mobile

## Technology

- **Frontend**: Pure HTML, CSS, and JavaScript (no frameworks)
- **Styling**: Custom CSS with gradient design
- **Serving**: http-server for static file serving
- **Export**: JavaScript Blob API for text file generation

## Installation

### Prerequisites

- Node.js 16+
- npm

### Setup

```bash
cd frontend
npm install
```

## Running the Application

```bash
npm start
```

The application will be available at http://localhost:8650

## Usage

1. **Enter Company Details**: Fill in company name and reporting year
2. **Select Statuses**: For each of the 11 TCFD disclosures, click Compliant, Partial, or Non-compliant
3. **View Score**: The overall compliance score updates automatically
4. **Export Report**: Click "Export report" to download a text file with the assessment
5. **Reset**: Click "Reset assessment" to start over

## TCFD Disclosures

The calculator includes all 11 TCFD recommendations:

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

## Scoring Formula

- **Compliant**: 1 point
- **Partial**: 0.5 points
- **Non-compliant**: 0 points

```
Score = (Weighted points / 11) × 100
```

## Project Structure

```
frontend/
├── src/
│   ├── index.html    # Main HTML file
│   └── app.js        # JavaScript logic
├── package.json      # Dependencies and scripts
└── README.md         # This file
```

## Customization

### Adding New Disclosures

Edit `src/app.js` and add to the `disclosures` array:

```javascript
{
    id: 'X.1',
    pillar: 'Pillar Name',
    title: 'Disclosure Title',
    status: null
}
```

### Changing Colors

Edit the CSS in `src/index.html`:

```css
/* Primary gradient */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Status colors */
.status-btn.active-compliant { background: #48bb78; }
.status-btn.active-partial { background: #ed8936; }
.status-btn.active-noncompliant { background: #f56565; }
```

## Future Enhancements

- PDF export using jsPDF
- Save/load assessments to local storage
- Historical tracking
- Comparison with previous years
- Print-friendly layout
- Dark mode toggle

## License

MIT
