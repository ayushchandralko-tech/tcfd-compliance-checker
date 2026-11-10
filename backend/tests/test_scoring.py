"""Unit tests for the criterion-level assessment logic (no embedding model needed)."""
import json

import numpy as np
import pytest

import assessment as A
import tcfd_api_server as server

REQ = json.loads((server.REQUIREMENTS_PATH).read_text(encoding="utf-8"))


def criterion(cid):
    for p in REQ["pillars"].values():
        for r in p["recommendations"]:
            for c in r["criteria"]:
                if c["id"] == cid:
                    return c
    raise KeyError(cid)


def passage(text, page=1, before="", after=""):
    return {"page": page, "text": text, "context_before": before, "context_after": after}


# --------------------------------------------------------------------------- knowledge base

def test_every_disclosure_has_criteria_with_signals_and_guidance():
    recs = [r for p in REQ["pillars"].values() for r in p["recommendations"]]
    assert len(recs) == 11
    for r in recs:
        assert r["criteria"], r["id"]
        assert any(c["essential"] for c in r["criteria"]), r["id"]
        for c in r["criteria"]:
            assert c["query"] and c["missing"] and c["signals"]
            assert c["id"].startswith(r["id"] + ".")


# --------------------------------------------------------------------------- passages

def test_passages_are_complete_sentences_with_context():
    text = " ".join(f"Sentence number {i} talks about climate governance at length." for i in range(40))
    ps = A.build_passages([{"page": 4, "text": text}])
    assert len(ps) > 2
    assert all(p["page"] == 4 for p in ps)
    assert all(p["text"].endswith(".") and len(p["text"]) <= A.PASSAGE_MAX for p in ps)
    assert ps[0]["context_before"] == "" and ps[0]["context_after"].startswith("Sentence number")
    assert ps[1]["context_before"].endswith(".")


def test_running_headers_are_stripped():
    bodies = ["Board oversight is described.", "Scenario analysis results.", "Emissions fell this year.",
              "Targets were set.", "Risk management is integrated.", "Metrics are reported."]
    pages = [{"page": i, "text": f"TASK FORCE ON CLIMATE-RELATED FINANCIAL DISCLOSURES REPORT 2023 {i} {b}"}
             for i, b in enumerate(bodies, start=1)] + [{"page": 7, "text": "A page without the header."}]
    out = A.strip_running_headers(pages)
    assert out[0]["text"] == "Board oversight is described."
    assert out[-1]["text"] == "A page without the header."


def test_overlong_sentences_are_cut_on_word_boundaries():
    ps = A.build_passages([{"page": 1, "text": "word " * 600}])
    assert all(len(p["text"]) <= A.PASSAGE_MAX for p in ps)
    assert all(not p["text"].endswith("wor") for p in ps)


# --------------------------------------------------------------------------- criterion evaluation

def test_supported_when_all_signals_cooccur_in_a_relevant_passage():
    c = criterion("G.1.a")
    ps = [passage("The Audit and Risk Committee of the Board receives quarterly reports on climate risk.", page=9)]
    r = A.evaluate_criterion(c, ps, np.array([0.7]))
    assert r["result"] == A.SUPPORTED
    assert r["evidence"]["page"] == 9 and r["evidence"]["relevance"] == 0.7
    assert set(r["evidence"]["signals_found"]) == {"board body", "frequency", "climate"}
    assert r["missing_guidance"] is None and r["decisive"]


def test_partly_supported_names_the_missing_signal():
    c = criterion("G.1.a")
    ps = [passage("The Board of Directors oversees climate-related risks.")]  # no frequency
    r = A.evaluate_criterion(c, ps, np.array([0.6]))
    assert r["result"] == A.PARTLY
    assert "frequency" in r["reason"]
    assert r["missing_guidance"] == c["missing"]


def test_not_found_when_nothing_relevant():
    c = criterion("S.3.b")
    ps = [passage("Our cafeteria introduced new menu options.")]
    r = A.evaluate_criterion(c, ps, np.array([0.1]))
    assert r["result"] == A.NOT_FOUND and r["evidence"] is None and r["decisive"]


def test_signals_must_cooccur_within_a_few_sentences():
    c = criterion("G.1.a")
    far_apart = passage("The Board of Directors approved the accounts. " + "Other matters were noted. " * 4
                        + "Quarterly updates on climate were given to staff.")
    r = A.evaluate_criterion(c, [far_apart], np.array([0.6]))
    assert r["result"] == A.PARTLY


def test_plans_and_training_are_not_evidence():
    c = criterion("S.3.a")
    plan = passage("The Bank will evaluate the feasibility of NGFS climate scenario analysis next year.")
    training = passage("Training programmes covered climate risk and NGFS scenarios.")
    for p in (plan, training):
        r = A.evaluate_criterion(c, [p], np.array([0.6]))
        assert r["result"] == A.PARTLY
        assert "plan or training" in r["reason"]
    done = passage("We ran scenario analysis using the NGFS Net Zero 2050 and Current Policies scenarios.")
    assert A.evaluate_criterion(c, [done], np.array([0.6]))["result"] == A.SUPPORTED


def test_searches_beyond_the_top_passage():
    c = criterion("M.2.a")
    ps = [passage("Emissions are an important topic for us."),  # most relevant but no values
          passage("Scope 1 emissions were 601 tCO2e and Scope 2 emissions were 12,240 tCO2e.", page=41)]
    r = A.evaluate_criterion(c, ps, np.array([0.7, 0.55]))
    assert r["result"] == A.SUPPORTED and r["evidence"]["page"] == 41


# --------------------------------------------------------------------------- classification

def res(result, essential=True, decisive=True):
    return {"id": "X", "text": "t", "essential": essential, "result": result, "decisive": decisive}


@pytest.mark.parametrize("results,status", [
    ([res(A.SUPPORTED), res(A.SUPPORTED), res(A.NOT_FOUND, essential=False)], A.STATUS_DISCLOSED),
    ([res(A.SUPPORTED), res(A.NOT_FOUND)], A.STATUS_PARTIAL),
    ([res(A.PARTLY), res(A.NOT_FOUND)], A.STATUS_PARTIAL),
    ([res(A.NOT_FOUND), res(A.NOT_FOUND)], A.STATUS_NOT),
])
def test_classification_rules(results, status):
    assert A.classify_disclosure(results)["status"] == status


def test_coverage_and_confidence_are_separate_measures():
    out = A.classify_disclosure([res(A.SUPPORTED), res(A.PARTLY, decisive=False), res(A.NOT_FOUND)])
    assert out["coverage"]["score"] == pytest.approx(0.5)
    assert out["coverage"]["supported"] == 1 and out["coverage"]["partly"] == 1
    assert out["confidence"]["level"] == "Medium"
    low = A.classify_disclosure([res(A.PARTLY, decisive=False)] * 3)
    assert low["confidence"]["level"] == "Low"


def test_not_assessable_for_scanned_or_tiny_documents():
    scanned = {"pages": [{"page": 1, "text": "x" * 3000}], "total_pages": 10}
    tiny = {"pages": [{"page": 1, "text": "Short note."}], "total_pages": 1}
    ok = {"pages": [{"page": 1, "text": "x" * 3000}], "total_pages": 1}
    assert "OCR" in A.not_assessable_reason(scanned)
    assert "too little text" in A.not_assessable_reason(tiny)
    assert A.not_assessable_reason(ok) is None


# --------------------------------------------------------------------------- metadata

def test_detects_company_and_year():
    doc = {"pages": [{"page": 1, "text": "Acme Energy plc Climate-related Financial Disclosures 2024. "
                                         "Acme Energy plc serves customers. Acme Energy plc reports. "
                                         "In 2023 we started; this report covers 2024."}],
           "total_pages": 1, "pdf_metadata": {}}
    m = A.detect_metadata(doc, "acme_tcfd_2024.pdf")
    assert m["company"] == "Acme Energy plc"
    assert m["reporting_year"] == "2024"


def test_detects_fiscal_year_ranges():
    doc = {"pages": [{"page": 1, "text": "Sustainability Report 2025-26"}], "total_pages": 1,
           "pdf_metadata": {"title": "Integrated Annual Report 2025-26"}}
    assert A.detect_metadata(doc)["reporting_year"] == "2025-26"
    assert A.year_range("2025-26") == [2025, 2026]
    assert A.year_range("2023") == [2023]
    assert A.year_range("abc") == []


def test_metadata_ignores_generic_pdf_author():
    doc = {"pages": [{"page": 1, "text": "Report 2022"}], "total_pages": 1,
           "pdf_metadata": {"author": "Adobe InDesign"}}
    assert A.detect_metadata(doc)["company"] is None


# --------------------------------------------------------------------------- legacy experimental models

@pytest.mark.slow
def test_trained_passage_models_rank_relevant_text():
    model_dir = server.BASE_DIR / "models" / "tcfd_external"
    if not (model_dir / "pillar_model.pkl").exists():
        pytest.skip("trained passage models not present; run train_external.py")
    server.state["requirements"] = server.load_requirements()
    server.load_passage_models(model_dir)
    try:
        recs = [(p, r["id"]) for p, r in server.iter_requirements(server.state["requirements"])]
        texts = ["Scope 1 and Scope 2 greenhouse gas emissions were 20,000 tCO2e under the GHG Protocol.",
                 "The board's audit and risk committee oversees climate-related risks quarterly."]
        scores = server.passage_model_scores(texts, recs)
        ids = [r for _, r in recs]
        assert scores.shape == (2, 11)
        assert ids[scores[0].argmax()].startswith("M.")
        assert ids[scores[1].argmax()].startswith("G.")
    finally:
        server.load_passage_models(None)
