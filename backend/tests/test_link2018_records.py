"""Link 2018 records loaded as a new source: mapping rules and the unresolved-unit / '-' honesty rules."""
import json

import pytest
from fastapi.testclient import TestClient
from helpers import EXPECTED

from app.core.config import get_settings


@pytest.fixture(scope="module")
def recs():
    p = get_settings().data_dir / "derived" / "link2018_experiments.json"
    if not p.exists():
        pytest.skip("run backend/scripts/build_link2018_records.py")
    return json.loads(p.read_text())["experiments"]


def test_mapping_rules(recs):
    assert len(recs) == 98 and len({r["experiment_id"] for r in recs}) == 98
    s1 = [r for r in recs if r["extra"]["table"] == "S1"]
    s2 = [r for r in recs if r["extra"]["table"] == "S2"]
    assert (len(s1), len(s2)) == (52, 46)
    assert all(r["gravity_level"] == "microgravity" and r["outcome_type"] == "measured" for r in s1)
    assert all(r["gravity_level"] == "1g (ground)" for r in s2)
    assert all(r["pressure_kpa"] is None and r["license"] == "CC BY 4.0" and r["doi"] == "10.1038/s41598-017-18398-4" for r in recs)
    # '-' is "tested at, no value reported": never an outcome, never interpreted as extinction
    dash = [r for r in s2 if r["outcome_type"] == "conditions_only"]
    assert len(dash) == 9 and all(r["outcome_value"] is None and r["outcome_class"] is None and any("'-'" in f for f in r["quality_flags"]) for r in dash)
    # the unresolved unit is kept as printed and flagged on every right-block S1 row
    right = [r for r in s1 if r["extra"]["block"] == "right"]
    assert right and all("mm/s" in r["outcome_unit"] and any("unresolved" in f for f in r["quality_flags"]) for r in right)
    assert all("cm/s" in r["outcome_unit"] for r in s1 if r["extra"]["block"] == "left")
    # colour only from the caption: B black, C clear, anything else "not stated"
    assert {r["material_variant"] for r in s1 if r["extra"]["sample_no"][0] == "B"} == {"rod, black"}
    assert {r["material_variant"] for r in s1 if r["extra"]["sample_no"][0] == "C"} == {"rod, clear"}
    assert all("not stated" in r["material_variant"] for r in s1 if r["extra"]["sample_no"][0] not in "BC")
    # spot values (hand-read from the PDF)
    b13a1 = next(r for r in recs if r["experiment_id"] == "LINK2018-S1-B13a-1")
    assert (b13a1["oxygen_pct"], b13a1["airflow_cm_s"], b13a1["outcome_value"], b13a1["characteristic_size_mm"]) == (20.7, 1.64, 5.23, 12.7)


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded with extras")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); s.mock = False; old = s.anthropic_api_key; s.anthropic_api_key = None
    from app.main import app
    yield TestClient(app)
    s.mock, s.anthropic_api_key = True, old


def test_loaded_and_citable(live):
    d = live.get("/api/experiments/LINK2018-S1-B13a-1").json()
    assert d["source_url"] == "https://doi.org/10.1038/s41598-017-18398-4" and d["record"]["gravity_bucket"] == "microgravity"
    assert d["card_text"].startswith("PMMA (acrylic) (rod, black) solid burn test; microgravity;")
    assert live.get("/api/materials/pmma").json()["material"]["variants"]
    pm = live.get("/api/materials/pmma").json()["material"]
    assert "10.1038/s41598-017-18398-4" in pm["dois"] and any(v["variant"] == "rod, clear" for v in pm["variants"])


def test_pmma_1g_request_now_has_published_spread_evidence(live):
    r = live.post("/api/assess", json={"material_query": "acrylic", "oxygen_pct": 18.5, "pressure_kpa": 101, "gravity": "earth"}).json()
    ids = [x["experiment_id"] for g in r["evidence_groups"] for x in g["records"]]
    assert r["verdict"] == "EVIDENCE" and any(i.startswith("LINK2018-S2") for i in ids)
