# Labelling guide: building a test set

Goal: label a handful of real reports per TCFD disclosure so we can measure how well the
automated assessment matches a human, and compare model versions fairly.

## 1. Pick reports

Reports already used (download into `backend/datasets/reports/` with these exact file names to reuse the saved labels):

| File name | Source |
|---|---|
| `EBRD_TCFD_Report_2023.pdf` | https://www.ebrd.com/content/dam/ebrd_dxp/assets/pdfs/environment---sustainability/sustainability-reporting/TCFD-Report-2023.pdf |
| `Ujjivan_SR_2025-26.pdf` | https://www.ujjivansfb.bank.in/assets/Ujjivan_SR_25_26_FINAL_05_10_26_c71e946e65.pdf |
| `APAR_Integrated_Report_2025-26.pdf` | https://apar.com/wp-content/uploads/2026/08/apar-ir-25-26.pdf |


Aim for **5 reports** (55 labels) to start, ideally 10+. Mix them so all three labels occur:

| Kind | Why | Examples (find the PDF on the company's website) |
|---|---|---|
| 2 dedicated TCFD / climate reports | mostly *Disclosed* | a bank or utility "TCFD Report" |
| 2 general sustainability reports | mix of *Partial* / *Disclosed* | `library/AstraZeneca-Sustainability-Report-2023.pdf` (already here) |
| 1 report with little climate content | mostly *Not disclosed* | `library/AZ-Impact-Publication-2024.pdf` (already here) |

Put new PDFs in `backend/datasets/reports/` (PDFs there are git-ignored for copyright; label files in `datasets/labels/` are committed) (the evaluator looks there and in `backend/library/`).
Text-based PDFs only; scanned images won't work.

## 2. Label

1. Start the backend (`python tcfd_api_server.py` in `backend/`) and frontend (`npm start` in `frontend/`).
2. Open **http://localhost:8650/label.html** (also linked from the calculator header).
3. Enter your initials, load the PDF, and work through the 11 cards. For each one:
   - Read the sub-requirements, then look at the retrieved passages **and** search the report
     (e.g. "board", "scenario", "Scope 3", "remuneration", "enterprise risk"). Open the PDF itself when unsure.
   - Choose a label, list the pages where you found the evidence, and add a short note for borderline calls.
   - The model's suggestion appears only after you choose, so it can't bias you.
4. Click **Save labels**. The file goes to `backend/datasets/labels/<report>.json`. Drafts are kept in the browser
   if you stop half way; **Download JSON** is a backup.

Labelling rules:

- **Disclosed:** specific (named bodies, processes, numbers, time frames) and covers most sub-requirements.
- **Partially disclosed:** addressed but vague, or only some sub-requirements.
- **Not disclosed:** nothing relevant, or only generic statements not about climate.
- Judge the **whole report**, not just the passages shown.
- Expect roughly 15-25 minutes per report.

### Reviewing AI-drafted labels

Label files can contain AI drafts (`"source": "ai_draft"`, with a `rationale` and evidence pages).
Drafts exist for the three reports in `backend/datasets/reports/` (EBRD TCFD 2023, Ujjivan SR 2025-26,
APAR IR 2025-26). When you load one of those PDFs in the labelling page:

- drafted cards are purple and show the draft label and its rationale;
- click a label (the same one to agree, a different one to correct) to confirm it - it then counts as `human`;
- items marked **BORDERLINE** in the rationale deserve the closest look;
- click **Save labels** when done.

`evaluate_reports.py` ignores unconfirmed drafts unless you pass `--include_drafts`.

## 3. Evaluate

```bash
cd backend
python evaluate_reports.py --configs models/tcfd_external models/tcfd_external_tfidf none
```

Compares the current embedding models, the fast TF-IDF models and keyword-only scoring:

| Column | Meaning |
|---|---|
| acc / mF1 | status accuracy and macro-F1 vs your labels |
| ±1 | share within one step (e.g. Partial vs Disclosed) |
| scoreMAE | average error in the 0-100 compliance score per report |
| evHit | share of labels (with pages given) where a retrieved passage was on one of your pages |
| s/rep | seconds per report |

Details per label go to `backend/models/eval/report_eval.json`. With fewer than ~50 labels, treat
differences of a few points as noise.

### Criterion-level labels (optional, recommended)

To measure criterion-level precision and recall, add the criterion results you judged to a label:

```json
"G.1": {"label": "Disclosed", "source": "human",
        "criteria": {"G.1.a": "Supported", "G.1.b": "Supported", "G.1.c": "Partly supported"}}
```

`evaluate_reports.py` then reports precision, recall and F1 per class at both disclosure and criterion
level. Evaluation is per report (never split by passage), so no report is partly "seen".

## 4. What to do with the results

- Low **evHit** means retrieval is the problem: tune ranking/keywords first.
- Good evHit but low accuracy means scoring is the problem: recalibrate the thresholds
  (`DISCLOSED_SCORE`, `PARTIAL_SCORE`, `MODEL_FULL_SUPPORT` in `tcfd_api_server.py`) on half the reports
  and check on the other half.
- Pick between the embedding and TF-IDF models on these numbers rather than on benchmark scores.
