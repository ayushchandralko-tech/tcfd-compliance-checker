"""
Criterion-level TCFD assessment.

Pipeline
--------
1. PDF processing      pages -> sentences -> passages of complete sentences (~700 chars),
                       each with the neighbouring sentences kept as context.
2. Retrieval           for every criterion (34 in total), passages are ranked by
                       relevance = 0.8 x semantic similarity (sentence embeddings, cosine)
                                 + 0.2 x lexical similarity (TF-IDF cosine, scaled to 0-1).
3. Criterion check     the top candidates (up to CANDIDATES) are checked for the evidence
                       signals the criterion needs (e.g. board body + frequency + climate).
                       Supported         - a relevant passage contains every signal
                       Partly supported  - a relevant passage contains some signals, or every
                                           signal but with weak relevance
                       Not found         - no relevant passage carries the evidence
4. Classification      Compliant      - every essential criterion supported
                       Partial        - some criteria supported or partly supported
                       Non-compliant  - no criterion has supporting evidence
                       Not assessable - the document cannot be assessed (unreadable / too short)
5. Measures (kept separate, never blended)
   - retrieval relevance       per passage, 0-1
   - evidence coverage         per disclosure: (supported + 0.5 x partly) / criteria
   - classification confidence High / Medium / Low, from how clear-cut each criterion result is

API status names are kept as Disclosed / Partially disclosed / Not disclosed / Not assessable.
"""

import re
from collections import Counter
from io import BytesIO
from typing import Dict, List, Optional

import numpy as np
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from passage_features import DEFAULT_MODEL, load_model
from tables import extract_tables, table_to_text

# Thresholds on retrieval relevance (0-1). Calibrated on the EBRD 2023 TCFD report and
# AstraZeneca 2023 sustainability report; see tests/ and evaluate_reports.py.
RELEVANCE_SUPPORT = 0.40   # passage is relevant enough to count as evidence
RELEVANCE_STRONG = 0.52    # clearly relevant
RELEVANCE_FLOOR = 0.30     # below this nothing in the document is about the criterion
CANDIDATES = 12            # passages checked per criterion before concluding "not found"
TFIDF_SCALE = 0.30         # TF-IDF cosine at which lexical similarity counts as 1.0
SEMANTIC_WEIGHT = 0.8       # prose passages
TABLE_SEMANTIC_WEIGHT = 0.7 # table passages: lexical overlap with long numeric rows is low
RELEVANCE_SUPPORT_TABLE = 0.32  # a table row set with every evidence signal is precise evidence
KEYWORD_CANDIDATES = 6     # extra candidates from keyword (TF-IDF) search
TABLE_CANDIDATES = 4       # extra candidates from table search

PASSAGE_TARGET = 700
PASSAGE_MAX = 1100
MIN_TEXT_CHARS = 1000      # less extractable text than this: Not assessable
MIN_TEXT_PAGE_SHARE = 0.5  # fewer pages with text than this share: Not assessable

CLIMATE_RE = re.compile(r"climate|emission|carbon|ghg|greenhouse|net[- ]?zero|decarboni|tcfd", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(•])|\s+(?=•)")

STATUS_DISCLOSED = "Disclosed"
STATUS_PARTIAL = "Partially disclosed"
STATUS_NOT = "Not disclosed"
STATUS_NA = "Not assessable"
STATUSES = [STATUS_NOT, STATUS_PARTIAL, STATUS_DISCLOSED, STATUS_NA]

SUPPORTED, PARTLY, NOT_FOUND = "Supported", "Partly supported", "Not found"

# Sentences that only announce plans or describe training are not evidence of current practice.
NON_EVIDENCE = re.compile(
    r"\b(?:will|plans? to|planned|intends? to|intention|feasibility|in the process of|proposed|"
    r"aims? to|working towards|is developing|are developing|future focus|key focus areas include|going forward|"
    r"training|trainings|course|workshop|webinar|awareness|learning (?:and|&) development|capacity[- ]building)\b",
    re.I)


# --------------------------------------------------------------------------- PDF processing

def read_pdf(content: bytes) -> Dict:
    """Pages with text plus document metadata. Raises ValueError if the bytes are not a PDF."""
    reader = PdfReader(BytesIO(content))  # raises on invalid PDFs
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            pages.append({"page": i, "text": text})
    pages = strip_running_headers(pages)
    try:
        doc_tables = extract_tables(reader, {p["page"]: p["text"] for p in pages})
    except Exception:  # noqa: BLE001  (table extraction is best-effort)
        doc_tables = []
    meta = {}
    try:
        info = reader.metadata or {}
        meta = {"title": str(info.get("/Title") or "").strip(), "author": str(info.get("/Author") or "").strip(),
                "subject": str(info.get("/Subject") or "").strip(),
                "created": str(info.get("/CreationDate") or "").strip()}
    except Exception:  # noqa: BLE001
        pass
    return {"pages": pages, "total_pages": len(reader.pages), "pdf_metadata": meta, "tables": doc_tables}


def strip_running_headers(pages: List[Dict], min_share: float = 0.3) -> List[Dict]:
    """Remove a running header (e.g. 'TCFD REPORT 2023 17') repeated at the start of many pages.

    Finds the longest opening phrase (3-12 words, digits ignored) shared by at least `min_share`
    of the pages, and strips it plus any page number next to it.
    """
    if len(pages) < 4:
        return pages

    def norm_words(text):
        return [re.sub(r"\d+", "#", w) for w in text.split()[:14]]

    best = None
    for n in range(12, 2, -1):
        counts = Counter(tuple(norm_words(p["text"])[:n]) for p in pages if len(p["text"].split()) > n)
        prefix, count = counts.most_common(1)[0] if counts else ((), 0)
        if count >= max(3, min_share * len(pages)) and any(not w.startswith("#") for w in prefix):
            best = n
            break
    if not best:
        return pages
    out = []
    for p in pages:
        words = p["text"].split()
        common = tuple(norm_words(p["text"])[:best])
        if common == counts.most_common(1)[0][0]:
            rest = words[best:]
            while rest and re.fullmatch(r"\d{1,4}", rest[0]):
                rest = rest[1:]
            out.append({**p, "text": " ".join(rest)})
        else:
            out.append(p)
    return [p for p in out if p["text"]]


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def build_passages(pages: List[Dict]) -> List[Dict]:
    """Group consecutive sentences on a page into passages of complete sentences."""
    passages = []
    for p in pages:
        sentences = split_sentences(p["text"])
        current: List[str] = []
        for s in sentences:
            # Very long "sentences" (tables, lists) are cut on word boundaries.
            while len(s) > PASSAGE_MAX:
                cut = s.rfind(" ", 0, PASSAGE_MAX)
                cut = cut if cut > PASSAGE_MAX // 2 else PASSAGE_MAX
                if current:
                    passages.append({"page": p["page"], "sentences": current})
                    current = []
                passages.append({"page": p["page"], "sentences": [s[:cut].strip()]})
                s = s[cut:].strip()
            if current and len(" ".join(current)) + len(s) > PASSAGE_TARGET:
                passages.append({"page": p["page"], "sentences": current})
                current = []
            current.append(s)
        if current:
            passages.append({"page": p["page"], "sentences": current})

    out = []
    for i, ps in enumerate(passages):
        text = " ".join(ps["sentences"])
        if len(text) < 40:
            continue
        prev_same = i > 0 and passages[i - 1]["page"] == ps["page"]
        next_same = i + 1 < len(passages) and passages[i + 1]["page"] == ps["page"]
        out.append({
            "page": ps["page"],
            "text": text,
            # Number-dense prose is usually a flattened table: weight and threshold it like one.
            "tabular": len(re.findall(r"\d[\d,.]*", text)) >= max(8, len(text) // 90),
            "context_before": passages[i - 1]["sentences"][-1] if prev_same else "",
            "context_after": passages[i + 1]["sentences"][0] if next_same else "",
        })
    return out


TABLE_CHUNK_ROWS = 12


def table_passages(tables: List[Dict]) -> List[Dict]:
    """One passage per table (long tables in chunks of TABLE_CHUNK_ROWS rows), keeping title and columns."""
    out = []
    for t in tables:
        for start in range(0, len(t["rows"]), TABLE_CHUNK_ROWS):
            part = {**t, "rows": t["rows"][start:start + TABLE_CHUNK_ROWS]}
            out.append({"page": t["page"], "text": table_to_text(part), "context_before": "", "context_after": "",
                        "is_table": True, "table": part})
    return out


# --------------------------------------------------------------------------- metadata

_GENERIC_META = re.compile(r"\b(?:untitled|microsoft|adobe|indesign|acrobat|word|document|pdf|admin|user)\b|^\d+$|\.(?:pdf|docx?|indd)$", re.I)
_ORG_SUFFIX = re.compile(
    r"\b((?:[A-Z][A-Za-z&.'-]+\s+){0,5}(?:Limited|Ltd\.?|plc|PLC|Inc\.?|Bank|Group|Corporation|Industries|"
    r"Holdings|AG|SA|N\.V\.|S\.p\.A\.)(?:\s+(?:for|of)\s+[A-Z][a-z]+(?:\s+(?:and\s+)?[A-Z][a-z]+){0,3})?)\b")
_CAMEL = re.compile(r"\b[A-Z][a-z]+[A-Z][a-z]+\b")
_ACRONYM = re.compile(r"\b[A-Z]{3,6}\b")
_ACRONYM_STOP = {"TCFD", "GHG", "ESG", "CEO", "CFO", "CRO", "CSO", "COO", "BRSR", "GRI", "SDG", "NGFS", "IEA", "PDF",
                 "THE", "AND", "FOR", "KPI", "CSR", "ISO", "SBTI", "IFRS", "SASB", "CDP", "UN", "USD", "EUR", "INR",
                 "REPORT", "ANNUAL", "TASK", "FORCE", "PCAF", "NPL", "RCP", "SSP", "LTD", "PLC", "CO2", "CO2E",
                 "LIMITED", "BANK", "GROUP", "FY", "ERM", "ICAAP", "RBI", "SEBI", "CEEW", "IPCC", "COP", "EU"}
_YEAR = re.compile(r"\b(?:FY\s?)?(20[0-6]\d)(?:\s?[-–/]\s?(\d{2}|20\d\d))?\b")


_ROLE_WORDS = {"chief", "risk", "officer", "executive", "president", "vice", "director", "directors", "managing",
               "head", "chairman", "chair", "chairperson", "annual", "report", "integrated", "sustainability",
               "the", "our", "this", "message", "from", "letter", "foreword", "independent", "board", "of"}


def _strip_role_words(name: str) -> str:
    words = name.split()
    while len(words) > 1 and words[0].lower().strip(".,") in _ROLE_WORDS:
        words.pop(0)
    return " ".join(words)


def _years_in(text: str) -> List[str]:
    out = []
    for m in _YEAR.finditer(text):
        start, end = m.group(1), m.group(2)
        if end:
            end_full = end if len(end) == 4 else start[:2] + end
            if int(end_full) == int(start) + 1:
                out.append(f"{start}-{end_full[2:]}")
                continue
        out.append(start)
    return out


def detect_metadata(doc: Dict, filename: str = "") -> Dict:
    """Best-effort company name and reporting year from PDF metadata, title pages and file name."""
    meta = doc.get("pdf_metadata") or {}
    pages = doc["pages"]
    head = " ".join(p["text"][:1500] for p in pages[:3])

    # Reporting year: weight the PDF title and file name, then the first pages.
    votes: Counter = Counter()
    for source, text, weight in [("title", meta.get("title", ""), 3), ("file name", filename, 3),
                                 ("first pages", head, 1)]:
        for y in _years_in(text):
            votes[(y, source)] += weight
    year, year_source = None, None
    if votes:
        totals: Counter = Counter()
        for (y, _), w in votes.items():
            totals[y] += w
        year = totals.most_common(1)[0][0]
        year_source = max((s for (y, s) in votes if y == year), key=lambda s: votes[(year, s)])

    # Company: PDF author/title if meaningful, else "<Name> Limited/plc/Bank", else frequent acronym.
    company, company_source = None, None
    author = meta.get("author", "")
    if author and not _GENERIC_META.search(author) and len(author) < 80 and not re.search(r"\d{4}", author):
        company, company_source = author, "PDF metadata (author)"
    if not company:
        # Candidates: "<Name> Limited/plc/Bank/...", and CamelCase brand names (e.g. AstraZeneca).
        # The one mentioned most often in the opening pages wins; a short name that is part of a
        # longer candidate (e.g. "European Bank") counts towards the longer one.
        lead = " ".join(p["text"][:3000] for p in pages[:6])
        body = " ".join(p["text"] for p in pages[:10])
        cands = {_strip_role_words(x.strip()) for x in _ORG_SUFFIX.findall(lead)
                 if not re.match(r"(The|Our|This|World|Central|Reserve)\b", x)}
        cands = {c for c in cands if len(c.split()) > 1}
        cands |= {c for c, n in Counter(_CAMEL.findall(body)).items() if n >= 5}
        scored = []
        for cand in cands:
            n = len(re.findall(re.escape(cand), body))
            scored.append((n, len(cand), cand))
        scored.sort(reverse=True)
        if scored and scored[0][0] >= 3:
            company = scored[0][2]
            company_source = "most frequent organisation name in the opening pages"
    if not company:
        body = " ".join(p["text"] for p in pages[:10])
        acr = Counter(a for a in _ACRONYM.findall(body) if a not in _ACRONYM_STOP)
        if acr:
            name, n = acr.most_common(1)[0]
            if n >= 5:
                company, company_source = name, "most frequent organisation acronym"

    return {"company": company, "company_source": company_source,
            "reporting_year": year, "reporting_year_source": year_source,
            "title": meta.get("title") or None}


def year_range(label: Optional[str]) -> List[int]:
    """'2025-26' -> [2025, 2026]; '2023' -> [2023]."""
    if not label:
        return []
    m = re.match(r"(20\d\d)(?:-(\d\d))?$", str(label).strip())
    if not m:
        return []
    start = int(m.group(1))
    return [start, start + 1] if m.group(2) else [start]


# --------------------------------------------------------------------------- retrieval

def _embed(texts: List[str]) -> np.ndarray:
    return load_model(DEFAULT_MODEL).encode(texts, batch_size=64, normalize_embeddings=True,
                                             show_progress_bar=False)


def relevance_matrices(passages: List[Dict], queries: List[str]):
    """Hybrid retrieval scores, each (queries x passages), all 0-1:

    semantic  cosine similarity of sentence embeddings
    lexical   TF-IDF cosine (word and phrase overlap), scaled so TFIDF_SCALE counts as 1.0
    relevance the combined score used for ranking and thresholds:
              prose passages 0.8 x semantic + 0.2 x lexical; table passages 0.7 / 0.3.
    """
    texts = [p["text"] for p in passages]
    semantic = np.clip(_embed(queries) @ _embed(texts).T, 0, 1)
    tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    m = tfidf.fit_transform(texts + queries)
    lexical = np.minimum(cosine_similarity(m[len(texts):], m[: len(texts)]) / TFIDF_SCALE, 1.0)
    is_table = np.array([bool(p.get("is_table") or p.get("tabular")) for p in passages])
    w = np.where(is_table, TABLE_SEMANTIC_WEIGHT, SEMANTIC_WEIGHT)
    relevance = w * semantic + (1 - w) * lexical
    return relevance, semantic, lexical


def relevance_matrix(passages: List[Dict], queries: List[str]) -> np.ndarray:
    return relevance_matrices(passages, queries)[0]


def candidate_passages(relevance: np.ndarray, lexical: np.ndarray, passages: List[Dict]) -> List[int]:
    """Union of three searches: top by combined relevance, top by keywords, top tables."""
    by_rel = list(relevance.argsort()[::-1][:CANDIDATES])
    by_lex = list(lexical.argsort()[::-1][:KEYWORD_CANDIDATES])
    table_idx = [i for i, p in enumerate(passages) if p.get("is_table")]
    by_table = sorted(table_idx, key=lambda i: -relevance[i])[:TABLE_CANDIDATES]
    seen, out = set(), []
    for i in by_rel + by_lex + by_table:
        if i not in seen:
            seen.add(i)
            out.append(int(i))
    return sorted(out, key=lambda i: -relevance[i])


SIGNAL_WINDOW = 3  # all signals of a criterion must co-occur within this many adjacent sentences

# A list item that follows a plan heading ("Key focus areas include: Completion of ...") is part of the plan.
LIST_ITEM = re.compile(r"^(?:[•\-–]\s*)?[A-Z][a-z]+(?:tion|sion|ment|ing|ance|ence|al)\b")


def _signal_hits(criterion: Dict, text: str) -> List[str]:
    return [s["name"] for s in criterion["signals"] if re.search(s["pattern"], text, re.I)]


def _passage_sentences(passage: Dict) -> List[str]:
    if passage.get("is_table"):
        return [passage["text"]]  # a table is evaluated as one unit
    return ([passage["context_before"]] if passage["context_before"] else []) + split_sentences(passage["text"]) \
        + ([passage["context_after"]] if passage["context_after"] else [])


def _plan_flags(sentences: List[str]) -> List[bool]:
    """Which sentences describe plans, intentions or training rather than current practice."""
    flags, in_plan_list = [], False
    for s in sentences:
        is_plan = bool(NON_EVIDENCE.search(s))
        if not is_plan and in_plan_list and LIST_ITEM.match(s):
            is_plan = True  # continues a list of planned items ("Advancement of ...", "Completion of ...")
        in_plan_list = is_plan
        flags.append(is_plan)
    return flags


def _best_window(criterion: Dict, passage: Dict):
    """Best window of SIGNAL_WINDOW adjacent sentences: (signals found, window text, only plans/training?).

    Requiring co-occurrence in a short window (rather than anywhere in the passage) stops unrelated
    sentences - e.g. a management-committee sentence next to a 'Board of Directors' heading - from
    jointly 'satisfying' a criterion.
    """
    sentences = _passage_sentences(passage)
    flags = _plan_flags(sentences)
    key = [s for s in criterion["signals"] if s["name"] != "climate"] or criterion["signals"]
    best = ([], "", False)
    for start in range(max(1, len(sentences) - SIGNAL_WINDOW + 1)):
        win = sentences[start:start + SIGNAL_WINDOW]
        hits = _signal_hits(criterion, " ".join(win))
        carrying = [k for k, s in enumerate(win) if any(re.search(x["pattern"], s, re.I) for x in key)]
        plan_only = bool(carrying) and all(flags[start + k] for k in carrying)
        better = len(hits) > len(best[0]) or (len(hits) == len(best[0]) and best[2] and not plan_only)
        if better:
            # Quote only the sentences that carry evidence signals, so the quote is the exact support.
            specific = [s for s in win if any(re.search(x["pattern"], s, re.I) for x in key)]
            names = {n for s in specific for n in _signal_hits(criterion, s)}
            extra = [] if (len(names) == len(hits)) else \
                [next(s for s in win if set(_signal_hits(criterion, s)) - names)]
            quote_sents = [s for s in win if s in specific or s in extra]
            best = (hits, " ".join(quote_sents) or " ".join(win), plan_only)
            if len(hits) == len(criterion["signals"]) and not plan_only:
                break
    return best


def _criterion_confidence(result: str, rel: float, top_rel: float) -> Dict:
    if result == SUPPORTED:
        if rel >= RELEVANCE_STRONG:
            return {"level": "High", "basis": f"all evidence signals present in a clearly relevant passage ({rel:.2f})"}
        return {"level": "Medium", "basis": f"all evidence signals present, but relevance is moderate ({rel:.2f})"}
    if result == NOT_FOUND:
        if top_rel < RELEVANCE_SUPPORT:
            return {"level": "High", "basis": f"nothing in the report is close to this criterion (best {top_rel:.2f})"}
        return {"level": "Medium", "basis": f"related passages exist (best {top_rel:.2f}) but lack the required evidence"}
    return {"level": "Low", "basis": "partial evidence: a human should decide whether it is sufficient"}


def evaluate_criterion(criterion: Dict, passages: List[Dict], relevance: np.ndarray,
                       lexical: Optional[np.ndarray] = None) -> Dict:
    lexical = relevance if lexical is None else lexical
    order = candidate_passages(relevance, lexical, passages)
    n_signals = len(criterion["signals"])
    best_full, best_partial, planned = None, None, None
    checked = 0
    for i in order:
        rel = float(relevance[i])
        if rel < RELEVANCE_FLOOR:
            continue
        checked += 1
        hits, window, plan_only = _best_window(criterion, passages[i])
        cand = (rel, i, hits, window)
        if len(hits) == n_signals and plan_only:
            planned = planned or cand
            continue
        if len(hits) == n_signals and (best_full is None or rel > best_full[0]):
            best_full = cand
        if hits and (best_partial is None or len(hits) > len(best_partial[2])
                     or (len(hits) == len(best_partial[2]) and rel > best_partial[0])):
            best_partial = cand

    top_rel = float(relevance[order[0]]) if order else 0.0
    signal_names = [s["name"] for s in criterion["signals"]]
    def threshold(c):
        p = passages[c[1]]
        return RELEVANCE_SUPPORT_TABLE if (p.get("is_table") or p.get("tabular")) else RELEVANCE_SUPPORT

    window = ""
    if best_full and best_full[0] >= threshold(best_full):
        rel, i, hits, window = best_full
        result = SUPPORTED
        kind = "table" if passages[i].get("is_table") else "page"
        reason = f"{kind.capitalize()} evidence on page {passages[i]['page']} (relevance {rel:.2f}) shows: {', '.join(hits)}."
    elif planned and planned[0] >= threshold(planned) and not best_full:
        rel, i, hits, window = planned
        result = PARTLY
        reason = (f"Page {passages[i]['page']} mentions {', '.join(hits)}, but only as a plan, intention or "
                  "training topic - not as something already done.")
    elif best_full or (best_partial and best_partial[0] >= threshold(best_partial)):
        rel, i, hits, window = best_full or best_partial
        result = PARTLY
        missing = [s for s in signal_names if s not in hits]
        reason = (f"Best evidence on page {passages[i]['page']} (relevance {rel:.2f}) shows {', '.join(hits)}"
                  + (f" but not {', '.join(missing)}." if missing else " but is only weakly relevant."))
    else:
        rel, i, hits = top_rel, None, []
        result = NOT_FOUND
        if checked:
            reason = (f"Searched {checked} candidate passages (semantic, keyword and table search; best relevance "
                      f"{top_rel:.2f}); none shows {', '.join(signal_names)} together.")
        else:
            reason = (f"No passage in the report is relevant to this criterion (best relevance {top_rel:.2f}, "
                      f"minimum {RELEVANCE_FLOOR}).")
        i = None

    confidence = _criterion_confidence(result, rel if result != NOT_FOUND else 0.0, top_rel)
    evidence = None
    if result != NOT_FOUND and i is not None:
        p = passages[i]
        evidence = {"page": p["page"], "quote": window, "text": p["text"], "context_before": p["context_before"],
                    "context_after": p["context_after"], "relevance": round(rel, 3),
                    "signals_found": hits, "is_table": bool(p.get("is_table")),
                    "table": p.get("table")}
    return {
        "id": criterion["id"], "text": criterion["text"], "essential": criterion["essential"],
        "result": result, "reason": reason, "confidence": confidence,
        "decisive": confidence["level"] == "High",
        "missing_guidance": None if result == SUPPORTED else criterion["missing"],
        "evidence": evidence, "signals_required": signal_names,
    }


def classify_disclosure(criteria_results: List[Dict]) -> Dict:
    """Status from essential criteria only; optional criteria affect coverage, never the status.

    Compliant           every essential criterion has direct supporting evidence
    Partially compliant at least one essential criterion is supported, but others are missing
    Non-compliant       no essential criterion is supported (partial or plan-only evidence is not enough)
    """
    essential = [c for c in criteria_results if c["essential"]]
    optional = [c for c in criteria_results if not c["essential"]]
    supported = [c for c in criteria_results if c["result"] == SUPPORTED]
    partly = [c for c in criteria_results if c["result"] == PARTLY]
    ess_supported = [c for c in essential if c["result"] == SUPPORTED]
    ess_partly = [c for c in essential if c["result"] == PARTLY]
    gaps = [c["text"] for c in essential if c["result"] != SUPPORTED]

    if len(ess_supported) == len(essential):
        status = STATUS_DISCLOSED
        reason = f"All {len(essential)} essential criteria have direct supporting evidence."
        missing_opt = [c["text"] for c in optional if c["result"] != SUPPORTED]
        if missing_opt:
            reason += f" Optional items not evidenced (do not affect status): {'; '.join(missing_opt)}."
    elif ess_supported:
        status = STATUS_PARTIAL
        reason = (f"{len(ess_supported)} of {len(essential)} essential criteria supported. "
                  f"Missing: {'; '.join(gaps)}.")
    else:
        status = STATUS_NOT
        reason = (f"None of the {len(essential)} essential criteria has direct supporting evidence"
                  + (f" ({len(ess_partly)} with only partial, weak or plan-only evidence)." if ess_partly else ".")
                  + f" Missing: {'; '.join(gaps)}.")

    n = len(criteria_results)
    coverage = (len(supported) + 0.5 * len(partly)) / n if n else 0.0
    levels = Counter(c["confidence"]["level"] for c in essential)
    if levels["Low"] == 0 and levels["Medium"] <= max(1, len(essential) // 3):
        level = "High" if levels["Medium"] == 0 else "Medium"
    elif levels["Low"] <= max(1, len(essential) // 3):
        level = "Medium"
    else:
        level = "Low"
    why = (f"Essential criteria confidence: {levels['High']} high, {levels['Medium']} medium, {levels['Low']} low"
           + (f" ({', '.join(c['id'] for c in essential if c['confidence']['level'] == 'Low')} need human judgement)."
              if levels["Low"] else "."))
    return {
        "status": status, "reason": reason,
        "coverage": {"supported": len(supported), "partly": len(partly), "not_found": n - len(supported) - len(partly),
                     "total": n, "essential_total": len(essential), "essential_supported": len(ess_supported),
                     "score": round(coverage, 3)},
        "confidence": {"level": level, "reason": why},
    }


def not_assessable_reason(doc: Dict) -> Optional[str]:
    text_chars = sum(len(p["text"]) for p in doc["pages"])
    share = len(doc["pages"]) / doc["total_pages"] if doc["total_pages"] else 0
    if share < MIN_TEXT_PAGE_SHARE:
        return (f"Only {len(doc['pages'])} of {doc['total_pages']} pages have extractable text "
                "(likely scanned images). Run OCR and re-analyse.")
    if text_chars < MIN_TEXT_CHARS:
        return f"The document contains too little text ({text_chars} characters) to assess."
    return None


def assess_document(doc: Dict, requirements: Dict, filename: str = "") -> Dict:
    pages = doc["pages"]
    recs = [(pillar, rec) for pillar, pdata in requirements["pillars"].items() for rec in pdata["recommendations"]]
    metadata = detect_metadata(doc, filename)
    na_reason = not_assessable_reason(doc)
    climate_mentions = sum(len(CLIMATE_RE.findall(p["text"])) for p in pages)

    passages = (build_passages(pages) + table_passages(doc.get("tables", []))) if not na_reason else []
    criteria = [cr for _, rec in recs for cr in rec["criteria"]]
    rel, _sem, lex = relevance_matrices(passages, [cr["query"] for cr in criteria]) if passages else (None, None, None)

    checklist, k = {}, 0
    for pillar, rec in recs:
        results = []
        for cr in rec["criteria"]:
            if rel is None:
                results.append({"id": cr["id"], "text": cr["text"], "essential": cr["essential"],
                                "result": STATUS_NA, "reason": na_reason, "decisive": True,
                                "confidence": {"level": "High", "basis": "the document could not be read"},
                                "missing_guidance": None, "evidence": None,
                                "signals_required": [s["name"] for s in cr["signals"]]})
            else:
                results.append(evaluate_criterion(cr, passages, rel[k], lex[k]))
            k += 1
        if na_reason:
            cls = {"status": STATUS_NA, "reason": na_reason,
                   "coverage": {"supported": 0, "partly": 0, "not_found": 0, "total": len(results),
                                "essential_total": sum(c["essential"] for c in results), "essential_supported": 0,
                                "score": None},
                   "confidence": {"level": "High", "reason": "The document could not be read."}}
        else:
            cls = classify_disclosure(results)
            if cls["status"] == STATUS_NOT and climate_mentions == 0:
                cls["reason"] = "The report contains no climate-related content."

        # Distinct evidence passages across criteria, for display and labelling tools.
        seen, evidence = set(), []
        for c in results:
            e = c["evidence"]
            if e and (e["page"], e["text"]) not in seen:
                seen.add((e["page"], e["text"]))
                evidence.append({"page": e["page"], "text": e["text"], "relevance": e["relevance"],
                                 "criteria": [c["id"]]})
            elif e:
                next(x for x in evidence if (x["page"], x["text"]) == (e["page"], e["text"]))["criteria"].append(c["id"])

        checklist[rec["id"]] = {
            "requirement_id": rec["id"], "tcfd_ref": rec.get("tcfd_ref"), "pillar": pillar,
            "title": rec["title"], "description": rec["description"],
            "requirements": [c["text"] for c in rec["criteria"]],
            **cls, "criteria": results, "evidence": evidence,
        }

    counts = Counter(r["status"] for r in checklist.values())
    assessable = [r for r in checklist.values() if r["status"] != STATUS_NA]
    points = counts[STATUS_DISCLOSED] + 0.5 * counts[STATUS_PARTIAL]
    all_criteria = [c for r in assessable for c in r["criteria"]]
    cov = ((sum(c["result"] == SUPPORTED for c in all_criteria) + 0.5 * sum(c["result"] == PARTLY for c in all_criteria))
           / len(all_criteria)) if all_criteria else None
    summary = {
        "total_requirements": len(checklist),
        "disclosed": counts[STATUS_DISCLOSED], "partially_disclosed": counts[STATUS_PARTIAL],
        "not_disclosed": counts[STATUS_NOT], "not_assessable": counts[STATUS_NA],
        "compliance_score": round(points / len(assessable) * 100, 2) if assessable else None,
        "evidence_coverage_score": round(cov * 100, 2) if cov is not None else None,
        "criteria_total": len(all_criteria),
        "criteria_supported": sum(c["result"] == SUPPORTED for c in all_criteria),
        "criteria_partly": sum(c["result"] == PARTLY for c in all_criteria),
        "criteria_missing": sum(c["result"] == NOT_FOUND for c in all_criteria),
        "pages_total": doc["total_pages"], "pages_with_text": len(pages), "passages": len(passages),
        "climate_mentions": climate_mentions, "not_assessable_reason": na_reason,
    }
    return {"summary": summary, "metadata": metadata, "compliance_checklist": checklist}
