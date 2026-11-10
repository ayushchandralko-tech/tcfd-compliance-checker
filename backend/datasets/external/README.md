# External labelled TCFD datasets

Downloaded 2026-11-10 from Hugging Face (parquet exports). Used by `train_external.py`.

| File | Source | Rows | Labels | Licence |
|---|---|---|---|---|
| `climatebert_tcfd_train.parquet` | [climatebert/tcfd_recommendations](https://huggingface.co/datasets/climatebert/tcfd_recommendations) | 1,300 | 0 none, 1 metrics, 2 strategy, 3 risk, 4 governance | CC BY-NC-SA 4.0 |
| `climatebert_tcfd_test.parquet` | same, official test split | 400 | same | CC BY-NC-SA 4.0 |
| `rexarski_tcfd_disclosure_train.parquet` | [rexarski/TCFD_disclosure](https://huggingface.co/datasets/rexarski/TCFD_disclosure) | 593 (537 unique) | the 11 TCFD recommended disclosures, e.g. `Governance a)` = G.1 | MIT |

**Licence note:** the ClimateBERT data is non-commercial (CC BY-NC-SA 4.0). Models trained on it inherit that restriction; retrain with `rexarski` only (or your own labels) for commercial use.

**Quality notes:** rexarski has only positive examples (no "not relevant" class) and some noisy labels; ClimateBERT labels are at pillar level only.

To re-download:

```bash
B=https://huggingface.co/api/datasets
curl -L -o rexarski_tcfd_disclosure_train.parquet $B/rexarski/TCFD_disclosure/parquet/default/train/0.parquet
curl -L -o climatebert_tcfd_train.parquet $B/climatebert/tcfd_recommendations/parquet/default/train/0.parquet
curl -L -o climatebert_tcfd_test.parquet $B/climatebert/tcfd_recommendations/parquet/default/test/0.parquet
```
