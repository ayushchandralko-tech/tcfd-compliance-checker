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
# These use the sentence-embedding model (downloaded on first use, ~90 MB).

STATUSES = STATUSES | {"Not assessable"}
CRITERION_RESULTS = {"Supported", "Partly supported", "Not found", "Not assessable"}


def test_assess_returns_criterion_level_checklist(client, sample_pdf):
    res = upload(client, "/tcfd/assess", sample_pdf, name="acme_tcfd_2024.pdf")
    assert res.status_code == 200
    body = res.json()
    checklist = body["compliance_checklist"]
    assert list(checklist) == EXPECTED_IDS
    s = body["summary"]
    assert s["pages_with_text"] == 5 and s["not_assessable"] == 0
    assert s["disclosed"] + s["partially_disclosed"] + s["not_disclosed"] == 11
    expected = round((s["disclosed"] + 0.5 * s["partially_disclosed"]) / 11 * 100, 2)
    assert s["compliance_score"] == expected
    assert 0 <= s["evidence_coverage_score"] <= 100
    assert s["criteria_total"] == s["criteria_supported"] + s["criteria_partly"] + s["criteria_missing"]
    for item in checklist.values():
        assert item["status"] in STATUSES and item["reason"]
        assert item["confidence"]["level"] in {"High", "Medium", "Low"}
        assert len(item["criteria"]) == item["coverage"]["total"]
        for c in item["criteria"]:
            assert c["result"] in CRITERION_RESULTS and c["reason"]
            if c["result"] != "Supported":
                assert c["missing_guidance"]
            if c["evidence"]:
                assert 1 <= c["evidence"]["page"] <= 5 and 0 <= c["evidence"]["relevance"] <= 1


def test_assess_finds_criterion_evidence_on_the_right_pages(client, sample_pdf):
    body = upload(client, "/tcfd/assess", sample_pdf).json()
    crit = {c["id"]: c for r in body["compliance_checklist"].values() for c in r["criteria"]}
    assert crit["G.1.a"]["result"] == "Supported" and crit["G.1.a"]["evidence"]["page"] == 2
    assert crit["M.2.a"]["result"] == "Supported" and crit["M.2.a"]["evidence"]["page"] == 4
    assert crit["M.3.a"]["result"] == "Supported"
    assert crit["S.3.a"]["result"] == "Not found"  # no scenario analysis in the sample
    assert body["compliance_checklist"]["S.3"]["status"] == "Not disclosed"


def test_assess_detects_company_and_year(client, sample_pdf):
    meta = upload(client, "/tcfd/assess", sample_pdf, name="report.pdf").json()["metadata"]
    assert meta["company"] == "Acme Energy plc"
    assert meta["reporting_year"] == "2024"


def test_short_document_is_not_assessable(client, make_pdf_bytes):
    pdf = make_pdf_bytes([["Our cafeteria introduced new menu options this year."]])
    body = upload(client, "/tcfd/assess", pdf).json()
    assert body["summary"]["not_assessable"] == 11
    assert body["summary"]["compliance_score"] is None
    assert all(r["status"] == "Not assessable" for r in body["compliance_checklist"].values())


def test_pdf_without_text_is_not_assessable_not_rejected(client, make_pdf_bytes):
    res = upload(client, "/tcfd/assess", make_pdf_bytes([[], []]))
    assert res.status_code == 200
    assert res.json()["summary"]["not_assessable"] == 11


@pytest.mark.parametrize("content,status", [
    (b"", 400),
    (b"this is not a pdf", 400),
])
def test_assess_rejects_bad_files(client, content, status):
    assert upload(client, "/tcfd/assess", content).status_code == status


# --------------------------------------------------------------------------- labelling

def test_labeling_task_includes_pages_and_hash(client, sample_pdf):
    body = upload(client, "/tcfd/labeling-task?top_k=2", sample_pdf).json()
    assert len(body["tasks"]) == 11
    assert len(body["pages"]) == 5
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


# --------------------------------------------------------------------------- exports

def test_save_export(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "EXPORTS_DIR", tmp_path / "exports")
    res = client.post("/tcfd/exports", json={"filename": "../TCFD Assessment.html", "content": "<html></html>"})
    assert res.status_code == 200
    saved = tmp_path / "exports" / "TCFD_Assessment.html"
    assert saved.read_text(encoding="utf-8") == "<html></html>"
    assert res.json()["relative_path"] == "exports/TCFD_Assessment.html"


@pytest.mark.parametrize("payload", [
    {"filename": "report.exe", "content": "x"},
    {"filename": "report.html", "content": ""},
    {"filename": "report.html"},
])
def test_save_export_validates(client, payload):
    assert client.post("/tcfd/exports", json=payload).status_code == 400
