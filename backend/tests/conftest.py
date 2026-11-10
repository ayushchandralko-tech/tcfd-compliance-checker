import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Fast by default: keyword/TF-IDF scoring only. Tests that need the trained
# passage models load them explicitly (marked "slow").
os.environ.setdefault("TCFD_PASSAGE_MODELS", "none")


def make_pdf(pages):
    """Build a minimal text PDF. `pages` is a list of pages, each a list of text lines."""
    objects = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = len(objects) + 1 + 2 * len(pages)  # reserved id for the Pages object
    page_ids = []
    for lines in pages:
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops += [f"({safe}) Tj", "T*"]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (pages_id, font, content)))
    kids = " ".join(f"{i} 0 R" for i in page_ids).encode()
    assert add(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)


SAMPLE_REPORT = [
    [  # page 1: governance
        "Climate governance. The Board of Directors oversees climate-related risks and opportunities.",
        "The Sustainability Committee of the board reviews climate risk quarterly and monitors progress",
        "against our net zero targets. The Chief Risk Officer is accountable for climate risk management",
        "and reports to the executive committee monthly.",
    ],
    [  # page 2: unrelated
        "Our cafeteria introduced new menu options and the staff football team won the regional cup.",
        "Employee volunteering hours increased compared with last year.",
    ],
    [  # page 3: emissions and targets
        "Greenhouse gas emissions. Scope 1 emissions were 12,000 tCO2e and Scope 2 emissions (market-based)",
        "were 8,000 tCO2e. Scope 3 emissions were 150,000 tCO2e, calculated using the GHG Protocol.",
        "We target a 50% reduction in Scope 1 and 2 emissions by 2030 from a 2019 baseline and net zero",
        "by 2050, validated by the Science Based Targets initiative (SBTi). Progress: 32% achieved.",
    ],
]


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf(SAMPLE_REPORT)


@pytest.fixture
def make_pdf_bytes():
    return make_pdf
