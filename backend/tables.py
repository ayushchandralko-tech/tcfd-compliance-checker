"""
Table extraction from PDF pages, without extra dependencies.

pypdf's layout mode keeps the horizontal position of text, so table columns come out
separated by runs of spaces. This module rebuilds tables from that text:

    Parameter                 Unit                 FY 2025-26   FY 2024-25
    Total Scope 1 emissions   MT CO2 equivalent    601.8        600.52

becomes {"title": ..., "columns": ["FY 2025-26", "FY 2024-25"], "rows": [
    {"section": "", "label": "Total Scope 1 emissions", "unit": "MT CO2 equivalent",
     "values": ["601.8", "600.52"]}]}

and a linear text form used for retrieval:
    "Total Scope 1 emissions (MT CO2 equivalent): FY 2025-26 601.8; FY 2024-25 600.52"

Handles wrapped row labels / units (continuation lines), section rows ("FROM RENEWABLE
SOURCES"), footnote markers (*, **) and missing values ("-").
"""

import logging
import re
from typing import Dict, List, Optional

# Layout mode warns on every page with rotated text (common in designed reports); the warning is
# expected and only means those text fragments are skipped.
logging.getLogger("pypdf._text_extraction._layout_mode._fixed_width_page").setLevel(logging.ERROR)

CELL_SPLIT = re.compile(r"\s{2,}")
PERIOD = re.compile(r"^(?:FY\s?)?(?:20\d\d|\d{2})(?:\s?[-–/]\s?(?:20)?\d{2})?$|^Q[1-4]\s?(?:FY)?\s?\d{2,4}$", re.I)
VALUE = re.compile(r"^(?:[-–]|n\.?a\.?|nil|[-–]?\(?[₹$€£]?\s?\d[\d,]*(?:\.\d+)?\)?\s?%?)\**$", re.I)
NUMBER = re.compile(r"\d")
UNIT_HEADERS = {"unit", "units", "uom", "unit of measurement"}


def page_may_have_table(text: str) -> bool:
    """Cheap filter on plain text: enough numbers and a period-like column header."""
    return len(re.findall(r"\d[\d,.]*", text)) >= 12 and bool(re.search(r"\bFY\s?\d{2}|\b20\d\d\b", text))


def _cells(line: str) -> List[str]:
    return [c.strip() for c in CELL_SPLIT.split(line.strip()) if c.strip()]


def _is_header(cells: List[str]) -> Optional[Dict]:
    periods = [i for i, c in enumerate(cells) if PERIOD.match(c)]
    if len(cells) >= 3 and len(periods) >= 2 and periods == list(range(periods[0], periods[0] + len(periods))):
        unit_col = next((i for i, c in enumerate(cells) if c.lower() in UNIT_HEADERS), None)
        return {"periods": [cells[i] for i in periods], "first_period": periods[0], "unit_col": unit_col}
    return None


def _split_row(cells: List[str], n_periods: int, has_unit: bool):
    """Return (label, unit, values) or None if the line is not a data row."""
    values = []
    rest = list(cells)
    while rest and len(values) < n_periods and VALUE.match(rest[-1]):
        values.insert(0, rest.pop())
    if not values or not rest:
        return None
    label = rest[0]
    unit = " ".join(rest[1:]) if has_unit else ""
    if not has_unit and len(rest) > 1:
        label = " ".join(rest)
    values = [""] * (n_periods - len(values)) + values
    return label, unit, values


def parse_tables(layout_text: str, page: int) -> List[Dict]:
    lines = [l for l in layout_text.splitlines() if l.strip()]
    tables, i = [], 0
    while i < len(lines):
        header = _is_header(_cells(lines[i]))
        if not header:
            i += 1
            continue
        # Title: the nearest short heading-like line in the 8 lines above the header
        # (no sentence-ending full stop, not part of another table).
        title = ""
        for back in range(i - 1, max(-1, i - 9), -1):
            cand = lines[back].strip()
            if 3 < len(cand) <= 80 and not cand.endswith((".", ",", ";")) and not _is_header(_cells(cand)) \
                    and len(_cells(lines[back])) == 1:
                title = cand
                break
        n = len(header["periods"])
        has_unit = header["unit_col"] is not None
        rows: List[Dict] = []
        section = ""
        j = i + 1
        while j < len(lines):
            raw = lines[j]
            cells = _cells(raw)
            row = _split_row(cells, n, has_unit) if len(cells) >= 2 else None
            if row and NUMBER.search(" ".join(row[2])):
                label, unit, values = row
                rows.append({"section": section, "label": label, "unit": unit, "values": values})
            elif len(cells) == 1 and cells[0].isupper() and len(cells[0]) < 70 and not NUMBER.search(cells[0]):
                section = cells[0].title()
            elif (rows and len(cells) <= 2 and not any(VALUE.match(c) for c in cells)
                  and len(raw.strip()) < 90 and raw.startswith(" ")):
                # wrapped continuation of the previous row's label (and unit)
                prev = rows[-1]
                if len(cells) == 2 and has_unit:
                    prev["label"] += " " + cells[0]
                    prev["unit"] = (prev["unit"] + " " + cells[1]).strip()
                elif has_unit and raw.startswith(" " * 20):
                    prev["unit"] = (prev["unit"] + " " + cells[0]).strip()
                else:
                    prev["label"] += " " + " ".join(cells)
            else:
                break
            j += 1
        if len(rows) >= 2:
            tables.append({"page": page, "title": title, "columns": header["periods"], "rows": rows})
        i = max(j, i + 1)
    return tables


def row_text(row: Dict, columns: List[str]) -> str:
    label = f"{row['section']}: {row['label']}" if row["section"] else row["label"]
    unit = f" ({row['unit']})" if row["unit"] else ""
    # Repeat a short unit after each value ("FY 2025-26: 601.8 MT CO2 equivalent") so a value is
    # always read together with its unit.
    per_value = f" {row['unit']}" if row["unit"] and len(row["unit"]) <= 30 else ""
    vals = "; ".join(f"{c}: {v}{per_value}" for c, v in zip(columns, row["values"]) if v and v not in "-–")
    return f"{label}{unit}: {vals}"


def table_to_text(table: Dict) -> str:
    body = ". ".join(row_text(r, table["columns"]) for r in table["rows"])
    return (f"{table['title']}. " if table["title"] else "") + body + "."


def extract_tables(reader, page_texts: Dict[int, str], max_pages: int = 400) -> List[Dict]:
    """Tables from all pages whose plain text looks tabular. `page_texts` maps page number -> plain text."""
    tables = []
    for page_no, text in list(page_texts.items())[:max_pages]:
        if not page_may_have_table(text):
            continue
        try:
            layout = reader.pages[page_no - 1].extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001
            continue
        tables.extend(parse_tables(layout, page_no))
    return tables
