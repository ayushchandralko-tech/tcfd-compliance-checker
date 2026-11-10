import pytest

import tcfd_api_server as server


def test_chunk_pages_keeps_page_numbers_and_overlaps():
    text = " ".join(f"word{i}" for i in range(600))
    chunks = server.chunk_pages([{"page": 7, "text": text}], chunk_size=900, overlap=150)
    assert len(chunks) > 1
    assert all(c["page"] == 7 for c in chunks)
    assert all(len(c["text"]) <= 900 for c in chunks)
    # consecutive chunks overlap and never split a word
    assert chunks[0]["text"].split()[-1] in chunks[1]["text"]
    assert all(not c["text"].startswith(" ") for c in chunks)


def test_chunk_pages_drops_tiny_fragments():
    assert server.chunk_pages([{"page": 1, "text": "Page 3"}]) == []


def test_keyword_hits_is_case_insensitive():
    assert server.keyword_hits("Scope 1 and SCOPE 2 emissions", ["scope 1", "scope 2", "scope 3"]) == ["scope 1", "scope 2"]


def rec(keywords):
    return {"keywords": keywords}


def test_score_thresholds():
    keywords = ["board", "oversight", "committee", "climate"]
    strong = [{"text": "The board committee has oversight of climate risk.", "similarity": 0.3}]
    weak = [{"text": "The board met.", "similarity": 0.05}]
    assert server.score_requirement(rec(keywords), strong)["status"] == "Disclosed"
    assert server.score_requirement(rec(keywords), weak)["status"] == "Not disclosed"
    assert server.score_requirement(rec(keywords), [])["status"] == "Not disclosed"


def test_score_penalises_evidence_without_climate_terms():
    keywords = ["board", "oversight", "committee", "risk"]
    with_climate = [{"text": "Board committee oversight of climate risk.", "similarity": 0.2}]
    without = [{"text": "Board committee oversight of credit risk.", "similarity": 0.2}]
    a = server.score_requirement(rec(keywords), with_climate)["confidence"]
    b = server.score_requirement(rec(keywords), without)["confidence"]
    assert b == pytest.approx(a / 2, abs=0.01)


def test_model_support_is_blended_when_available():
    keywords = ["scope 1", "emissions"]
    base = [{"text": "Scope 1 emissions fell.", "similarity": 0.25}]
    low = server.score_requirement(rec(keywords), [{**base[0], "model_score": 0.0}])
    high = server.score_requirement(rec(keywords), [{**base[0], "model_score": 0.95}])
    assert high["model_support"] == 1.0 and low["model_support"] == 0.0
    assert high["confidence"] > low["confidence"]


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
