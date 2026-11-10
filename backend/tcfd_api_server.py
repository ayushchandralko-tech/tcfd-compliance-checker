"""
Standalone API server for the TCFD compliance checker.

The assessment itself lives in assessment.py (criterion-level pipeline):
  PDF processing -> semantic retrieval per criterion -> evidence-sufficiency check per
  criterion -> disclosure classification with reasons -> scores (compliance and evidence
  coverage kept separate). Human review and final scoring happen in the frontend.

The passage models trained by train_external.py are optional and are not used for status
decisions; they remain available for experiments (passage_model_scores).
"""

import hashlib
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import uvicorn
from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Saved passage models reference passage_features.EmbeddingFeaturizer; make it importable
# regardless of the working directory the server is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import assessment  # noqa: E402  (needs the path above)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
REQUIREMENTS_PATH = BASE_DIR / "library" / "tcfd_requirements.json"
LABELS_DIR = BASE_DIR / "datasets" / "labels"
MODEL_PATH = BASE_DIR / "models" / "tcfd_classifier" / "baseline_model.pkl"
# Passage models directory (relative to backend/); TCFD_PASSAGE_MODELS=none disables them.
_passage_env = os.environ.get("TCFD_PASSAGE_MODELS", "models/tcfd_external")
EXTERNAL_DIR = None if _passage_env.lower() == "none" else (BASE_DIR / _passage_env)
PILLAR_KEY = {"Governance": "governance", "Strategy": "strategy",
              "Risk Management": "risk", "Metrics & Targets": "metrics"}

LABEL_MAP = {0: "Not disclosed", 1: "Partially disclosed", 2: "Disclosed"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

state: Dict = {"vectorizer": None, "classifier": None, "requirements": None,
               "pillar_model": None, "disclosure_model": None}


def load_requirements() -> Dict:
    with open(REQUIREMENTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_passage_models(external_dir: Optional[Path]) -> None:
    """Load (or, with None, unload) the pillar/disclosure passage models into `state`."""
    state["pillar_model"] = state["disclosure_model"] = None
    if external_dir is None:
        return
    try:
        state["pillar_model"] = joblib.load(external_dir / "pillar_model.pkl")
        state["disclosure_model"] = joblib.load(external_dir / "disclosure_model.pkl")["model"]
        # Warm up (loads the sentence-embedding model, if the pipelines use one).
        state["pillar_model"].predict_proba(["Scope 1 and 2 emissions decreased by 10%."])
        logger.info("Pillar and disclosure models loaded from %s", external_dir)
    except FileNotFoundError:
        state["pillar_model"] = state["disclosure_model"] = None
        logger.warning("No trained passage models in %s - run train_external.py", external_dir)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state["requirements"] = load_requirements()
    logger.info("Loaded %d TCFD requirements", len(list(iter_requirements(state["requirements"]))))

    if MODEL_PATH.exists():
        try:
            model_data = joblib.load(MODEL_PATH)
            state["vectorizer"] = model_data["vectorizer"]
            state["classifier"] = model_data["classifier"]
            logger.info("Baseline classifier loaded")
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to load classifier: %s", e)
    else:
        logger.warning("No classifier at %s - evidence-based scoring only", MODEL_PATH)

    try:
        load_passage_models(EXTERNAL_DIR)
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to load passage models: %s", e)
    yield


app = FastAPI(title="TCFD Compliance Checker API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Text processing
# --------------------------------------------------------------------------- #

def iter_requirements(requirements: Dict):
    for pillar, pillar_data in requirements["pillars"].items():
        for rec in pillar_data["recommendations"]:
            yield pillar, rec


def classify(text: str) -> Optional[Dict]:
    """Legacy synthetic-data baseline classifier (reported for comparison only)."""
    vec, clf = state["vectorizer"], state["classifier"]
    if vec is None or clf is None:
        return None
    try:
        proba = clf.predict_proba(vec.transform([text]))[0]
        probs = {LABEL_MAP[c]: float(p) for c, p in zip(clf.classes_, proba)}
        label = max(probs, key=probs.get)
        return {"label": label, "confidence": probs[label], "probabilities": probs}
    except Exception as e:  # noqa: BLE001
        logger.error("Classifier error: %s", e)
        return None


def passage_model_scores(texts: List[str], recs: List) -> Optional[np.ndarray]:
    """Experimental: P(pillar) x P(disclosure | pillar) from the models trained by train_external.py.

    Shape (passages, requirements). Not used for status decisions. Returns None if not loaded.
    """
    pm, dm = state["pillar_model"], state["disclosure_model"]
    if pm is None or dm is None or not texts:
        return None
    pillar_p = pm.predict_proba(texts)
    pillar_idx = {c: i for i, c in enumerate(pm.classes_)}
    disc_p = dm.predict_proba(texts)
    disc_idx = {c: i for i, c in enumerate(dm.classes_)}
    out = np.zeros((len(texts), len(recs)))
    for j, (pillar, req_id) in enumerate(recs):
        siblings = [disc_idx[r] for p, r in recs if p == pillar and r in disc_idx]
        within = disc_p[:, disc_idx[req_id]] / disc_p[:, siblings].sum(axis=1)
        out[:, j] = pillar_p[:, pillar_idx[PILLAR_KEY[pillar]]] * within
    return out


def parse_document(content: bytes) -> Dict:
    try:
        return assessment.read_pdf(content)
    except Exception as e:  # noqa: BLE001
        logger.error("Error opening PDF: %s", e)
        raise HTTPException(status_code=400, detail="Could not read the file as a PDF")


def parse_pdf(content: bytes) -> List[Dict]:
    """Pages with extractable text (kept for scripts that only need page text)."""
    return parse_document(content)["pages"]


def assess(doc: Dict, filename: str = "") -> Dict:
    return assessment.assess_document(doc, state["requirements"], filename)


async def read_pdf_upload(file: UploadFile):
    """Returns (document, sha256). An unreadable document is assessed as Not assessable, not rejected."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    return parse_document(content), hashlib.sha256(content).hexdigest()


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "TCFD Compliance Checker",
        "model": "loaded" if state["classifier"] is not None else "not loaded",
        "passage_models": "loaded" if state["pillar_model"] is not None else "not loaded",
        "requirements": len(list(iter_requirements(state["requirements"]))) if state["requirements"] else 0,
    }


@app.get("/tcfd/requirements")
async def get_tcfd_requirements():
    return state["requirements"] or load_requirements()


@app.post("/tcfd/assess")
async def assess_tcfd_compliance(file: UploadFile):
    """Assess a report PDF against the 11 TCFD recommended disclosures, criterion by criterion."""
    logger.info("Assessing %s", file.filename)
    doc, sha256 = await read_pdf_upload(file)
    result = assess(doc, file.filename or "")
    s = result["summary"]
    logger.info("Done: %d disclosed, %d partial, %d not disclosed, %d not assessable",
                s["disclosed"], s["partially_disclosed"], s["not_disclosed"], s["not_assessable"])
    return {
        "framework": "TCFD",
        "source_file": file.filename,
        "sha256": sha256,
        "method": "criterion-level: semantic retrieval + evidence-sufficiency checks",
        "method_details": {
            "relevance": "0.8 x semantic similarity (sentence embeddings) + 0.2 x lexical similarity (TF-IDF)",
            "criterion_supported": (f"a passage with relevance >= {assessment.RELEVANCE_SUPPORT} contains every "
                                    f"required evidence signal within {assessment.SIGNAL_WINDOW} adjacent sentences, "
                                    "and is not only a plan or training mention"),
            "status_rules": {"Disclosed": "all essential criteria supported",
                             "Partially disclosed": "some criteria supported or partly supported",
                             "Not disclosed": "no criterion has supporting evidence",
                             "Not assessable": "document unreadable or too short"},
            "coverage": "(supported + 0.5 x partly supported) / criteria",
            "confidence": "High / Medium / Low by how many criterion results are borderline",
        },
        **result,
    }


@app.post("/tcfd/compare")
async def compare_methods(file: UploadFile):
    """Compare the criterion-based status with the legacy baseline classifier's prediction."""
    if state["classifier"] is None:
        raise HTTPException(status_code=503, detail="Classifier not loaded; run train_baseline.py first")
    doc, _ = await read_pdf_upload(file)
    checklist = assess(doc, file.filename or "")["compliance_checklist"]
    comparison = {}
    for req_id, r in checklist.items():
        clf = classify(r["evidence"][0]["text"]) if r["evidence"] else None
        comparison[req_id] = {
            "title": r["title"],
            "criterion_status": r["status"],
            "classifier_status": clf["label"] if clf else None,
            "classifier_confidence": clf["confidence"] if clf else None,
            "agreement": bool(clf) and clf["label"] == r["status"],
        }
    agree = sum(1 for c in comparison.values() if c["agreement"])
    return {"source_file": file.filename,
            "agreement_rate": round(agree / len(comparison) * 100, 2) if comparison else 0.0,
            "comparison": comparison}


@app.post("/tcfd/labeling-task")
async def create_labeling_task(file: UploadFile, top_k: int = 5):
    """Build a labeling task: per-disclosure evidence plus full page text for searching.

    The automated status is returned as `suggested_label` so tools can hide it while labelling
    (to avoid anchoring) and compare afterwards. `top_k` limits the evidence passages shown.
    """
    doc, sha256 = await read_pdf_upload(file)
    checklist = assess(doc, file.filename or "")["compliance_checklist"]
    k = max(1, min(top_k, 10))
    tasks = [
        {
            "requirement_id": r["requirement_id"],
            "tcfd_ref": r["tcfd_ref"],
            "pillar": r["pillar"],
            "title": r["title"],
            "description": r["description"],
            "requirements": r["requirements"],
            "suggested_label": r["status"],
            "evidence_chunks": r["evidence"][:k],
            "label": None,
            "evidence_pages": [],
            "labeler_notes": "",
        }
        for r in checklist.values()
    ]
    return {
        "metadata": {
            "source_file": file.filename,
            "sha256": sha256,
            "num_pages": len(doc["pages"]),
            "total_requirements": len(tasks),
            "labeling_instructions": LABELING_GUIDE,
        },
        "pages": doc["pages"],
        "tasks": tasks,
    }


LABELING_GUIDE = (
    "Label the whole report, not just the passages shown. "
    "Disclosed: the report addresses the disclosure specifically (named bodies, processes, numbers, "
    "time frames) covering most of its sub-requirements. "
    "Partially disclosed: the topic is addressed but vaguely or only some sub-requirements are covered. "
    "Not disclosed: nothing relevant in the report, or only generic statements unrelated to climate."
)
VALID_LABELS = {"Disclosed", "Partially disclosed", "Not disclosed", "Not assessable"}


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:120] or "report"


@app.post("/tcfd/labels")
async def save_labels(payload: Dict = Body(...)):
    """Save a completed labelling task to datasets/labels/<report>.json."""
    meta = payload.get("metadata") or {}
    labels = payload.get("labels") or {}
    if not meta.get("source_file") or not labels:
        raise HTTPException(status_code=400, detail="metadata.source_file and labels are required")
    known = {rec["id"] for _, rec in iter_requirements(state["requirements"])}
    for req_id, item in labels.items():
        if req_id not in known:
            raise HTTPException(status_code=400, detail=f"Unknown requirement {req_id}")
        if item.get("label") not in VALID_LABELS:
            raise HTTPException(status_code=400, detail=f"{req_id}: label must be one of {sorted(VALID_LABELS)}")
    missing = sorted(known - set(labels))

    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    path = LABELS_DIR / f"{_safe_stem(meta['source_file'])}.json"
    record = {
        "metadata": {k: meta.get(k) for k in ("source_file", "sha256", "num_pages", "labeler", "company",
                                               "reporting_year", "labelled_at")},
        "labels": {k: {"label": v["label"],
                       # "human" = confirmed by a person; "ai_draft" = unreviewed draft (ignored by evaluation)
                       "source": "ai_draft" if v.get("source") == "ai_draft" else "human",
                       "evidence_pages": [int(p) for p in v.get("evidence_pages", []) if str(p).isdigit()],
                       "notes": str(v.get("notes", ""))[:2000],
                       **({"rationale": str(v["rationale"])[:4000]} if v.get("rationale") else {})}
                   for k, v in labels.items()},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    drafts = sorted(k for k, v in record["labels"].items() if v["source"] == "ai_draft")
    logger.info("Saved %d labels to %s", len(labels), path)
    try:
        shown = str(path.relative_to(BASE_DIR))
    except ValueError:
        shown = str(path)
    return {"saved_to": shown, "labelled": len(labels), "missing": missing,
            "unconfirmed_drafts": drafts}


@app.get("/tcfd/labels/{sha256}")
async def get_labels_for_report(sha256: str):
    """Return the saved label file for a report (matched by PDF SHA-256), so it can be reviewed."""
    for path in sorted(LABELS_DIR.glob("*.json")) if LABELS_DIR.exists() else []:
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        if rec.get("metadata", {}).get("sha256") == sha256:
            return {"file": path.name, **rec}
    raise HTTPException(status_code=404, detail="No saved labels for this report")


@app.get("/tcfd/labels")
async def list_labels():
    """List saved label files with how many requirements each covers."""
    out = []
    for path in sorted(LABELS_DIR.glob("*.json")) if LABELS_DIR.exists() else []:
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
            labs = rec.get("labels", {}).values()
            out.append({"file": path.name, "source_file": rec["metadata"].get("source_file"),
                        "labelled": len(rec.get("labels", {})),
                        "unconfirmed_drafts": sum(1 for v in labs if v.get("source") == "ai_draft")})
        except Exception:  # noqa: BLE001
            out.append({"file": path.name, "error": "unreadable"})
    return {"labels": out}


if __name__ == "__main__":
    print("Starting TCFD Compliance Checker API at http://localhost:8250 (docs: /docs)")
    uvicorn.run(app, host="127.0.0.1", port=8250)
