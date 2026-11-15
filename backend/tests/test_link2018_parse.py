"""Link 2018 supplementary tables: parser invariants + cells checked by hand against the PDF."""
import importlib.util
import os
from pathlib import Path

import pytest

pytest.importorskip("pdfplumber")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parse_link2018.py"
spec = importlib.util.spec_from_file_location("parse_link2018", SCRIPT)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
if not P.PDF.exists():
    pytest.skip("raw PDF not downloaded (run backend/scripts/fetch_raw.py)", allow_module_level=True)


@pytest.fixture(scope="module")
def tables():
    import pdfplumber
    with pdfplumber.open(P.PDF) as pdf:
        s1, unit = P.parse_s1(pdf.pages[0])
        s2 = P.parse_s2(pdf.pages[1])
    return s1, unit, s2


def test_counts(tables):
    s1, unit, s2 = tables
    assert len(s1) == 52 and len({r["sample_no"] for r in s1}) == 19      # 52 microgravity rows (knowledge pack G4)
    assert len(s2) == 46 and sum(r["no_value"] for r in s2) == 9


def test_printed_unit_difference_is_kept_not_resolved(tables):
    _, unit, _ = tables
    assert unit == {"left": "cm/s", "right": "mm/s"}                       # header typo or real difference: unresolved, flagged downstream
    s1 = tables[0]
    assert {r["spread_rate_unit_printed"] for r in s1} == {"x10^-3 cm/s", "x10^-3 mm/s"}


def steps(s1, name):
    return [(r["flow_cm_s"], r["duration_s"], r["spread_rate_x1e3"]) for r in s1 if r["sample_no"] == name]


def test_s1_hand_checked_cells(tables):
    s1 = tables[0]
    b13a = [r for r in s1 if r["sample_no"] == "B13a"]
    assert {r["diameter_cm"] for r in b13a} == {1.27} and {r["o2_pct"] for r in b13a} == {20.7}
    assert steps(s1, "B13a") == [(1.64, 184, 5.23), (1.54, 232, 5.27), (1.43, 239, 4.63), (1.38, 238, 4.69)]
    assert steps(s1, "B6") == [(2.00, 90, 10.00), (1.87, 121, 9.74), (1.73, 93, 8.32)]
    assert {(r["diameter_cm"], r["o2_pct"]) for r in s1 if r["sample_no"] == "B6"} == {(0.64, 18.9)}
    assert steps(s1, "P17") == [(1.01, 123, 4.12), (0.82, 187, 4.78), (0.41, 65, 2.26)]
    # shared O2 label: B15 and B14 both sit under the single 18.4 % label
    assert {r["o2_pct"] for r in s1 if r["sample_no"] in ("B15", "B14")} == {18.4}


def cell(s2, d, o2, vg):
    r = [x for x in s2 if x["diameter_cm"] == d and x["o2_pct"] == o2 and x["flow_cm_s"] == vg]
    assert len(r) >= 1
    return r[0]


def test_s2_hand_checked_cells(tables):
    s2 = tables[2]
    c = cell(s2, 1.27, 20.9, 25)
    assert (c["spread_rate_x1e3"], c["uncertainty_pct"]) == (7.81, 0.2)
    c = cell(s2, 1.27, 20.9, 2)
    assert (c["spread_rate_x1e3"], c["uncertainty_pct"]) == (9.07, 2.5)
    c = cell(s2, 0.32, 17.5, 2)
    assert (c["spread_rate_x1e3"], c["uncertainty_pct"]) == (3.88, 0.5)
    c = cell(s2, 0.32, 17.0, 2)
    assert c["no_value"] and c["spread_rate_x1e3"] is None
    assert all(r["gravity"] == "1g" for r in s2) and {r["diameter_cm"] for r in s2} == {1.27, 0.95, 0.64, 0.32}
