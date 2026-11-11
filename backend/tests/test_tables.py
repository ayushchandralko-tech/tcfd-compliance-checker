"""Table reconstruction from pypdf layout-mode text."""
import tables as T

LAYOUT = """
   EMISSION MANAGEMENT
Some introductory prose sentence that is long and ends with a full stop and is not a title at all.
 Parameter                         Unit                       FY 2025-26       FY 2024-25       FY 2023-24
 Total Scope 1 emissions           MT CO2 equivalent              601.8           600.52           887.73
 Total Scope 2 emissions           MT CO2 equivalent          12,240.56        13,270.24        13,995.74
 Total Scope 1 and Scope 2 emission   MT CO2 equivalent/ turnover     1.60             1.93             2.30
 intensity                            in Rs Crores
 Total Scope 3 emissions*          MT CO2 equivalent          62,520.60        17,907.95                -
* Footnote: categories covered are listed here in a long sentence that ends the table.
"""

SECTIONS = """
Energy Metrics over a Three-Year Period
 Parameter                              Unit        FY 2025-26        FY 2024-25
 FROM RENEWABLE SOURCES
 Total electricity consumption          GJ              116.69             51.09
 FROM NON-RENEWABLE SOURCES
 Total electricity consumption          GJ           62,064.79*        65,712.33
 (Purchased electricity)
"""


def test_parses_rows_units_and_columns():
    [t] = T.parse_tables(LAYOUT, page=41)
    assert t["page"] == 41
    assert t["title"] == "EMISSION MANAGEMENT"
    assert t["columns"] == ["FY 2025-26", "FY 2024-25", "FY 2023-24"]
    labels = [r["label"] for r in t["rows"]]
    assert labels[0] == "Total Scope 1 emissions"
    assert t["rows"][0]["unit"] == "MT CO2 equivalent"
    assert t["rows"][0]["values"] == ["601.8", "600.52", "887.73"]


def test_wrapped_labels_and_units_are_joined():
    [t] = T.parse_tables(LAYOUT, page=41)
    row = t["rows"][2]
    assert row["label"] == "Total Scope 1 and Scope 2 emission intensity"
    assert row["unit"] == "MT CO2 equivalent/ turnover in Rs Crores"


def test_missing_values_are_kept_and_skipped_in_text():
    [t] = T.parse_tables(LAYOUT, page=41)
    scope3 = t["rows"][3]
    assert scope3["values"][-1] == "-"
    text = T.row_text(scope3, t["columns"])
    assert "FY 2023-24" not in text and "FY 2025-26: 62,520.60" in text


def test_section_rows_and_continuations():
    [t] = T.parse_tables(SECTIONS, page=37)
    assert t["title"] == "Energy Metrics over a Three-Year Period"
    assert [r["section"] for r in t["rows"]] == ["From Renewable Sources", "From Non-Renewable Sources"]
    assert t["rows"][1]["label"].endswith("(Purchased electricity)")
    assert "From Non-Renewable Sources: Total electricity consumption" in T.table_to_text(t)


def test_prose_is_not_a_table():
    assert T.parse_tables("Just a paragraph about climate in 2023 and 2024.\nAnother line.", page=1) == []
    assert not T.page_may_have_table("A short page without numbers.")
