"""
Standalone API server for the TCFD compliance checker.

Pipeline for each uploaded report:
  1. Extract text page by page (pypdf).
  2. Split pages into overlapping passages, keeping the page number.
  3. For each of the 11 TCFD recommended disclosures, rank passages by TF-IDF
     cosine similarity to the requirement (title, description, sub-requirements
     and keywords).
  4. Measure keyword coverage across the top passages and turn the evidence
     strength into a status: Disclosed / Partially disclosed / Not disclosed.
  5. If a trained baseline classifier is available, its prediction on the
     retrieved evidence is reported alongside (it is trained on synthetic data
     today, so the evidence-based status is the primary result).
"""

import hashlib
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import uvicorn
from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Saved passage models reference passage_features.EmbeddingFeaturizer; make it importable
# regardless of the working directory the server is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

STATUSES = ["Not disclosed", "Partially disclosed", "Disclosed"]
LABEL_MAP = {0: "Not disclosed", 1: "Partially disclosed", 2: "Disclosed"}

# Evidence thresholds (tuned on the AstraZeneca 2023 report in library/).
TOP_K = 3
DISCLOSED_SCORE = 0.55
PARTIAL_SCORE = 0.30
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# TF-IDF cosine similarity of ~0.25+ to a requirement query is a strong match.
SIM_SCALE = 0.25
# Embedding-based passage models are confident; require ~0.9 probability for full support.
MODEL_FULL_SUPPORT = 0.9
CLIMATE_RE = re.compile(r"climate|emission|carbon|ghg|greenhouse|net[- ]zero|decarboni|warming", re.I)

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


def parse_pdf(file_content: bytes) -> List[Dict]:
    """Return [{'page': n, 'text': ...}] for every page with extractable text."""
    try:
        reader = PdfReader(BytesIO(file_content))
    except Exception as e:  # noqa: BLE001
        logger.error("Error opening PDF: %s", e)
        raise HTTPException(status_code=400, detail="Could not read the file as a PDF")

    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            pages.append({"page": i, "text": text})
    return pages


def chunk_pages(pages: List[Dict], chunk_size: int = 900, overlap: int = 150) -> List[Dict]:
    """Split each page into overlapping passages, breaking on word boundaries."""
    chunks = []
    for p in pages:
        text = p["text"]
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                space = text.rfind(" ", start + chunk_size // 2, end)
                if space != -1:
                    end = space
            chunks.append({"page": p["page"], "text": text[start:end].strip()})
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return [c for c in chunks if len(c["text"]) > 40]


def requirement_query(rec: Dict) -> str:
    return " ".join([rec["title"], rec["description"], " ".join(rec.get("requirements", [])),
                     " ".join(rec.get("keywords", []))])


def keyword_hits(text: str, keywords: List[str]) -> List[str]:
    lower = text.lower()
    return [k for k in keywords if k.lower() in lower]


def classify(text: str) -> Optional[Dict]:
    vec, clf = state["vectorizer"], state["classifier"]
    if vec is None or clf is None:
        return None
    try:
        x = vec.transform([text])
        proba = clf.predict_proba(x)[0]
        classes = list(clf.classes_)
        probs = {LABEL_MAP[c]: float(p) for c, p in zip(classes, proba)}
        label = max(probs, key=probs.get)
        return {"label": label, "confidence": probs[label], "probabilities": probs}
    except Exception as e:  # noqa: BLE001
        logger.error("Classifier error: %s", e)
        return None


# --------------------------------------------------------------------------- #
# Assessment
# --------------------------------------------------------------------------- #

def retrieve(chunks: List[Dict], requirements: Dict, top_k: int = TOP_K) -> Dict[str, List[Dict]]:
    """Rank passages for every requirement in one TF-IDF pass."""
    recs = list(iter_requirements(requirements))
    if not chunks:
        return {rec["id"]: [] for _, rec in recs}

    queries = [requirement_query(rec) for _, rec in recs]
    tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    matrix = tfidf.fit_transform([c["text"] for c in chunks] + queries)
    chunk_m, query_m = matrix[: len(chunks)], matrix[len(chunks):]
    sims = cosine_similarity(query_m, chunk_m)
    model_probs = passage_model_scores([c["text"] for c in chunks], [(p, r["id"]) for p, r in recs])

    # Passages that never mention climate/emissions are rarely TCFD evidence; halve their rank.
    climate_weight = np.array([1.0 if CLIMATE_RE.search(c["text"]) else 0.5 for c in chunks])

    results = {}
    for qi, (_, rec) in enumerate(recs):
        sim_norm = np.minimum(sims[qi] / SIM_SCALE, 1.0)
        if model_probs is not None:
            rank_score = 0.5 * sim_norm + 0.5 * model_probs[:, qi]
        else:
            rank_score = sim_norm
        rank_score = rank_score * climate_weight
        order = rank_score.argsort()[::-1][:top_k]
        results[rec["id"]] = [
            {"page": chunks[i]["page"], "text": chunks[i]["text"], "similarity": float(sims[qi][i]),
             "model_score": float(model_probs[i, qi]) if model_probs is not None else None}
            for i in order if rank_score[i] > 0
        ]
    return results


def passage_model_scores(texts: List[str], recs: List) -> Optional[np.ndarray]:
    """P(passage supports requirement) = P(pillar) x P(disclosure | pillar), shape (passages, requirements).

    Uses models trained by train_external.py on public labelled TCFD data. Returns None if not loaded.
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
        key = PILLAR_KEY[pillar]
        siblings = [disc_idx[r] for p, r in recs if p == pillar and r in disc_idx]
        within = disc_p[:, disc_idx[req_id]] / disc_p[:, siblings].sum(axis=1)
        out[:, j] = pillar_p[:, pillar_idx[key]] * within
    return out


def score_requirement(rec: Dict, passages: List[Dict]) -> Dict:
    keywords = rec.get("keywords", [])
    evidence_text = " ".join(p["text"] for p in passages)
    hits = keyword_hits(evidence_text, keywords)
    coverage = len(hits) / len(keywords) if keywords else 0.0
    top_sim = passages[0]["similarity"] if passages else 0.0
    mentions_climate = bool(CLIMATE_RE.search(evidence_text))

    sim_component = min(top_sim / SIM_SCALE, 1.0)
    model_scores = [p["model_score"] for p in passages if p.get("model_score") is not None]
    model_support = None
    if model_scores:
        # Strongest support, scaled so that MODEL_FULL_SUPPORT probability counts as full support.
        model_support = min(max(model_scores) / MODEL_FULL_SUPPORT, 1.0)
        evidence_score = 0.45 * coverage + 0.25 * sim_component + 0.30 * model_support
    else:
        evidence_score = 0.6 * coverage + 0.4 * sim_component
    if not mentions_climate:
        evidence_score *= 0.5

    if evidence_score >= DISCLOSED_SCORE:
        status = "Disclosed"
    elif evidence_score >= PARTIAL_SCORE:
        status = "Partially disclosed"
    else:
        status = "Not disclosed"

    return {
        "status": status,
        "confidence": round(evidence_score, 3),
        "keyword_coverage": round(coverage, 3),
        "matched_keywords": hits,
        "retrieval_score": round(top_sim, 3),
        "model_support": round(model_support, 3) if model_support is not None else None,
    }


def assess_text(pages: List[Dict], top_k: int = TOP_K) -> Dict:
    requirements = state["requirements"]
    chunks = chunk_pages(pages)
    retrieved = retrieve(chunks, requirements, top_k=top_k)

    checklist = {}
    for pillar, rec in iter_requirements(requirements):
        passages = retrieved[rec["id"]]
        scored = score_requirement(rec, passages)
        evidence = [
            {"page": p["page"], "text": p["text"][:600] + ("..." if len(p["text"]) > 600 else ""),
             "similarity": round(p["similarity"], 3),
             "model_score": round(p["model_score"], 3) if p.get("model_score") is not None else None}
            for p in passages
        ]
        checklist[rec["id"]] = {
            "requirement_id": rec["id"],
            "tcfd_ref": rec.get("tcfd_ref"),
            "pillar": pillar,
            "title": rec["title"],
            "description": rec["description"],
            "requirements": rec.get("requirements", []),
            **scored,
            "evidence": evidence,
            "classifier": classify(passages[0]["text"]) if passages else None,
        }

    total = len(checklist)
    counts = {s: sum(1 for r in checklist.values() if r["status"] == s) for s in STATUSES}
    points = counts["Disclosed"] + 0.5 * counts["Partially disclosed"]
    summary = {
        "total_requirements": total,
        "disclosed": counts["Disclosed"],
        "partially_disclosed": counts["Partially disclosed"],
        "not_disclosed": counts["Not disclosed"],
        "compliance_score": round(points / total * 100, 2) if total else 0.0,
        "disclosed_percentage": round(counts["Disclosed"] / total * 100, 2) if total else 0.0,
        "average_confidence": round(sum(r["confidence"] for r in checklist.values()) / total, 3) if total else 0.0,
        "pages_with_text": len(pages),
        "passages": len(chunks),
    }
    return {"summary": summary, "compliance_checklist": checklist}


async def read_pdf_upload(file: UploadFile, with_hash: bool = False):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    pages = parse_pdf(content)
    if not pages:
        raise HTTPException(
            status_code=422,
            detail="No extractable text found. The PDF may be scanned images; run OCR first.",
        )
    if with_hash:
        return pages, hashlib.sha256(content).hexdigest()
    return pages


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
    """Assess a sustainability report PDF against the 11 TCFD recommended disclosures."""
    logger.info("Assessing %s", file.filename)
    pages = await read_pdf_upload(file)
    result = assess_text(pages)
    s = result["summary"]
    logger.info("Done: %d disclosed, %d partial, %d not disclosed",
                s["disclosed"], s["partially_disclosed"], s["not_disclosed"])
    return {
        "framework": "TCFD",
        "source_file": file.filename,
        "method": ("tfidf-retrieval + keyword-coverage + trained pillar/disclosure models"
                   if state["pillar_model"] is not None else "tfidf-retrieval + keyword-coverage"),
        "classifier_loaded": state["classifier"] is not None,
        **result,
    }


@app.post("/tcfd/compare")
async def compare_methods(file: UploadFile):
    """Compare the evidence-based status with the baseline classifier's prediction."""
    if state["classifier"] is None:
        raise HTTPException(status_code=503, detail="Classifier not loaded; run train_baseline.py first")
    pages = await read_pdf_upload(file)
    checklist = assess_text(pages)["compliance_checklist"]

    comparison = {}
    for req_id, r in checklist.items():
        clf = r["classifier"] or {}
        comparison[req_id] = {
            "title": r["title"],
            "evidence_status": r["status"],
            "evidence_confidence": r["confidence"],
            "classifier_status": clf.get("label"),
            "classifier_confidence": clf.get("confidence"),
            "agreement": clf.get("label") == r["status"],
        }
    agree = sum(1 for c in comparison.values() if c["agreement"])
    return {
        "source_file": file.filename,
        "agreement_rate": round(agree / len(comparison) * 100, 2) if comparison else 0.0,
        "comparison": comparison,
    }


@app.post("/tcfd/labeling-task")
async def create_labeling_task(file: UploadFile, top_k: int = 5):
    """Build a labeling task: top retrieved passages per requirement plus full page text for searching.

    The automated status is returned as `suggested_label` so tools can hide it while labelling
    (to avoid anchoring) and compare afterwards.
    """
    pages, sha256 = await read_pdf_upload(file, with_hash=True)
    checklist = assess_text(pages, top_k=max(1, min(top_k, 10)))["compliance_checklist"]
    tasks = [
        {
            "requirement_id": r["requirement_id"],
            "tcfd_ref": r["tcfd_ref"],
            "pillar": r["pillar"],
            "title": r["title"],
            "description": r["description"],
            "requirements": r["requirements"],
            "suggested_label": r["status"],
            "evidence_chunks": r["evidence"],
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
            "num_pages": len(pages),
            "total_requirements": len(tasks),
            "labeling_instructions": LABELING_GUIDE,
        },
        "pages": pages,
        "tasks": tasks,
    }


LABELING_GUIDE = (
    "Label the whole report, not just the passages shown. "
    "Disclosed: the report addresses the disclosure specifically (named bodies, processes, numbers, "
    "time frames) covering most of its sub-requirements. "
    "Partially disclosed: the topic is addressed but vaguely or only some sub-requirements are covered. "
    "Not disclosed: nothing relevant in the report, or only generic statements unrelated to climate."
)
VALID_LABELS = set(STATUSES)


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
