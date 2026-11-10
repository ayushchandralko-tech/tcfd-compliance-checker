import json

import pytest
from fastapi.testclient import TestClient

import tcfd_api_server as server

EXPECTED_IDS = ["G.1", "G.2", "S.1", "S.2", "S.3", "R.1", "R.2", "R.3", "M.1", "M.2", "M.3"]
STATUSES = {"Disclosed", "Partially disclosed", "Not disclosed"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "LABELS_DIR", tmp_path / "labels")
    with TestClient(server.app) as c:
        yield c


def upload(client, url, content, name="report.pdf"):
    return client.post(url, files={"file": (name, content, "application/pdf")})


# --------------------------------------------------------------------------- basics

def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy"
    assert body["requirements"] == 11


def test_requirements_are_the_11_official_disclosures(client):
    reqs = client.get("/tcfd/requirements").json()
    ids = [r["id"] for p in reqs["pillars"].values() for r in p["recommendations"]]
    assert ids == EXPECTED_IDS
    for p in reqs["pillars"].values():
        for r in p["recommendations"]:
            assert r["keywords"] and r["requirements"] and r["tcfd_ref"]


# --------------------------------------------------------------------------- assess

def test_assess_returns_full_checklist(client, sample_pdf):
    res = upload(client, "/tcfd/assess", sample_pdf)
    assert res.status_code == 200
    body = res.json()
    checklist = body["compliance_checklist"]
    assert list(checklist) == EXPECTED_IDS
    s = body["summary"]
    assert s["pages_with_text"] == 3
    assert s["disclosed"] + s["partially_disclosed"] + s["not_disclosed"] == 11
    expected_score = round((s["disclosed"] + 0.5 * s["partially_disclosed"]) / 11 * 100, 2)
    assert s["compliance_score"] == expected_score
    for item in checklist.values():
        assert item["status"] in STATUSES
        assert 0 <= item["confidence"] <= 1
        assert all(1 <= e["page"] <= 3 for e in item["evidence"])


def test_assess_finds_evidence_on_the_right_pages(client, sample_pdf):
    checklist = upload(client, "/tcfd/assess", sample_pdf).json()["compliance_checklist"]
    assert checklist["M.2"]["evidence"][0]["page"] == 3
    assert checklist["G.1"]["evidence"][0]["page"] == 1
    assert checklist["M.2"]["status"] != "Not disclosed"
    assert "scope 1" in checklist["M.2"]["matched_keywords"]


def test_assess_irrelevant_report_scores_low(client, make_pdf_bytes):
    pdf = make_pdf_bytes([["Our cafeteria introduced new menu options this year."],
                          ["The staff football team won the regional cup."]])
    body = upload(client, "/tcfd/assess", pdf).json()
    assert body["summary"]["not_disclosed"] == 11
    assert body["summary"]["compliance_score"] == 0


@pytest.mark.parametrize("content,status", [
    (b"", 400),
    (b"this is not a pdf", 400),
])
def test_assess_rejects_bad_files(client, content, status):
    assert upload(client, "/tcfd/assess", content).status_code == status


def test_assess_rejects_pdf_without_text(client, make_pdf_bytes):
    res = upload(client, "/tcfd/assess", make_pdf_bytes([[]]))
    assert res.status_code == 422


# --------------------------------------------------------------------------- labelling

def test_labeling_task_includes_pages_and_hash(client, sample_pdf):
    body = upload(client, "/tcfd/labeling-task?top_k=2", sample_pdf).json()
    assert len(body["tasks"]) == 11
    assert len(body["pages"]) == 3
    assert len(body["metadata"]["sha256"]) == 64
    assert all(len(t["evidence_chunks"]) <= 2 and t["label"] is None for t in body["tasks"])


def test_save_get_and_list_labels(client, sample_pdf):
    meta = upload(client, "/tcfd/labeling-task", sample_pdf).json()["metadata"]
    payload = {"metadata": meta, "labels": {
        "G.1": {"label": "Disclosed", "evidence_pages": [1], "notes": "board committee"},
        "M.2": {"label": "Partially disclosed", "source": "ai_draft", "rationale": "draft"},
    }}
    res = client.post("/tcfd/labels", json=payload)
    assert res.status_code == 200
    saved = res.json()
    assert saved["labelled"] == 2
    assert saved["unconfirmed_drafts"] == ["M.2"]
    assert len(saved["missing"]) == 9

    rec = client.get(f"/tcfd/labels/{meta['sha256']}").json()
    assert rec["labels"]["G.1"] == {"label": "Disclosed", "source": "human", "evidence_pages": [1],
                                    "notes": "board committee"}
    assert rec["labels"]["M.2"]["source"] == "ai_draft"

    listing = client.get("/tcfd/labels").json()["labels"]
    assert listing == [{"file": "report.json", "source_file": "report.pdf", "labelled": 2, "unconfirmed_drafts": 1}]


@pytest.mark.parametrize("labels", [
    {"X.9": {"label": "Disclosed"}},
    {"G.1": {"label": "Mostly disclosed"}},
    {},
])
def test_save_labels_validates(client, labels):
    res = client.post("/tcfd/labels", json={"metadata": {"source_file": "r.pdf"}, "labels": labels})
    assert res.status_code == 400


def test_save_labels_sanitises_filename(client):
    payload = {"metadata": {"source_file": "../../evil name.pdf"}, "labels": {"G.1": {"label": "Disclosed"}}}
    saved = client.post("/tcfd/labels", json=payload).json()["saved_to"]
    assert ".." not in saved.replace("\\", "/").split("/")[-1]
    assert saved.endswith("evil_name.json")


def test_unknown_report_labels_404(client):
    assert client.get("/tcfd/labels/" + "0" * 64).status_code == 404
