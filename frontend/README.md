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
- **Status Selector**: Compliant / Partial / Non-compliant / Not assessable (N/A, excluded from the score)
- **Automatic Calculation**: Instant percentage score calculation
- **Score Summary**: Overall score and status counts
- **Auto-fill from PDF**: Upload a report; the backend (`localhost:8250`) suggests a status per disclosure with page-cited evidence, which you can override
- **Export Report**: Formatted HTML report (print or save as PDF) with score, pillar summary, every disclosure's status, automated suggestion, page-cited evidence passages and reviewer notes; plus a JSON data export
- **Responsive Design**: Works on desktop and mobile

## Technology

- **Frontend**: Pure HTML, CSS, and JavaScript (no frameworks)
- **Styling**: Custom CSS with design tokens in `:root` (colours, radius, shadow)
- **Serving**: http-server for static file serving
- **Export**: self-contained HTML report and JSON, generated in the browser (Blob API)

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
4. **Review**: Expand a card to see each criterion's result, evidence passage (page, relevance, context, link to the PDF page) and what is missing; accept the AI suggestion or change it with a reason
5. **Export Report**: Click "Export report" for an HTML report including all evidence and notes (Print / Save as PDF from the report), or "Download data (JSON)"
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
{ id: 'X.1', ref: 'Pillar (x)', pillar: 'Pillar Name', title: 'Disclosure title',
  description: 'What the disclosure asks for.',
  asks: ['Sub-requirement 1', 'Sub-requirement 2'] }
```

Add the pillar to `PILLARS` if it is new.

### Changing Colors

Edit the design tokens at the top of the `<style>` block in `src/index.html`:

```css
:root {
    --accent: #3b5bdb;   /* buttons, links, score ring */
    --ok: #2f9e44;       /* Compliant */
    --warn: #e67700;     /* Partial */
    --bad: #e03131;      /* Non-compliant */
}
```

## Future Enhancements

- Save/load assessments to local storage
- Historical tracking
- Comparison with previous years
- Print-friendly layout
- Dark mode toggle

## License

MIT
