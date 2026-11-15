"""Phase 3: Earth vs Space, correction module (not configured + configured path with TEST-ONLY coefficients), unknown material."""
import json

import pytest
from helpers import EXPECTED
import yaml
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services import correction


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); s.mock = False
    from app.main import app
    yield TestClient(app)
    s.mock = True


def post(c, **kw):
    r = c.post("/api/assess", json={"material_query": "acrylic", "oxygen_pct": 21, "pressure_kpa": 101, "gravity": "orbit"} | kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_pmma_side_by_side_and_not_configured(live):
    d = post(live)
    e = d["earth_vs_space"]
    assert e["available"] and e["baseline_1g"]["moc_values"] and e["microgravity_evidence"]
    assert all(m["experiment_id"].startswith("WSTF") and m["source_url"].startswith("https://ntrs") for m in e["baseline_1g"]["moc_values"])
    assert e["correction_model_status"] == "not_configured" and e["correction_model_message"] == "Correction model not configured"
    assert e["one_g_not_conservative"] is None and e["banner"] is None          # no human labels yet
    assert "MOC" in e["baseline_1g"]["test_note"] and "LOI" in e["baseline_1g"]["test_note"]


def test_unknown_char_yield_30(live):
    d = post(live, material_query="Zorbium-7", gravity="mars", unknown_material_props={"char_yield_pct": 30})
    assert d["verdict"] == "NO_DIRECT_EVIDENCE" and d["material"] is None
    e = d["estimate"]
    assert e["value"] == 29.5 and e["kind"] == "van_krevelen_loi_1g" and e["not_a_microgravity_limit"]
    assert e["label"] == "LOI (downward, 1g) estimate — Van Krevelen, not tested"
    assert "29.5" in d["summary_text"]


def test_unknown_family_neighbours_and_loi_not_mixed(live):
    d = post(live, material_query="Zorbium-7", unknown_material_props={"polymer_family": "polyester", "known_loi_pct": 22, "known_loi_standard": "ASTM D2863"})
    assert d["nearest_evidence"] and all(n["record"]["material_id"] == "pet" for n in d["nearest_evidence"])
    assert d["verdict"] == "NO_DIRECT_EVIDENCE" and "not compared" in d["summary_text"]
    d = post(live, material_query="Zorbium-7", unknown_material_props={"known_loi_pct": 22})
    assert any("without a test standard" in w for w in d["warnings"])


def test_unknown_without_props_is_empty_state(live):
    d = post(live, material_query="Zorbium-7")
    assert d["estimate"] is None and d["empty_state_message"] and d["verdict"] == "NO_DIRECT_EVIDENCE"


def test_banner_only_from_confirmed_labels(live, tmp_path):
    from app.services import evidence as ev
    from helpers import put_labels, temp_derived
    rows = ev.material_rows("pmma")
    mocs = [e["outcome_value"] for e in rows if e.get("outcome_variable") == "MOC"]
    cand = [e for e in rows if e["gravity_level"] == "microgravity" and e.get("oxygen_pct") is not None and e["oxygen_pct"] < min(mocs)]
    assert cand, "need a PMMA µg record below the lowest MOC for this test"
    eid = cand[0]["experiment_id"]
    with temp_derived():
        put_labels([{"experiment_id": eid, "label": "sustained_burn", "quote": "q", "labelled_by": "t", "status": "suggested"}])
        assert post(live)["earth_vs_space"]["banner"] is None                       # suggestions never count
        from app.services import store
        store.get_db()[get_settings().labels_collection].update_one({"_id": eid}, {"$set": {"status": "confirmed"}})
        e = post(live)["earth_vs_space"]
        assert e["one_g_not_conservative"] is True and "NOT conservative" in e["banner"] and len(e["banner_sources"]) == 2


def _fake_model(tmp_path, with_error):
    """TEST-ONLY made-up coefficients, never shipped."""
    y = {"models": [{"id": "test", "status": "configured", "citation": "TEST ONLY", "page": "0", "equation": "O2 = moc - a*flow",
                     "formula": "moc_1g_pct - a * airflow_cm_s", "inputs": ["moc_1g_pct", "airflow_cm_s"], "coefficients": {"a": 0.1},
                     "valid_range": {"moc_1g_pct": [0, 100], "airflow_cm_s": [0, 50]}}]}
    p = tmp_path / "m.yaml"; p.write_text(yaml.safe_dump(y))
    if with_error:
        from helpers import put_validation
        put_validation({"correction_model": {"mae_pct_o2": 1.0}})
    return p, None


def test_shipped_model_is_not_configured():
    st, msg = correction.status()
    assert st == "not_configured" and msg == "Correction model not configured"
    assert not any(m.get("coefficients") for m in yaml.safe_load(get_settings().correction_models_path.read_text())["models"])


def test_configured_model_paths(live, tmp_path):
    from helpers import temp_derived
    s = get_settings(); old = s.correction_models_path
    with temp_derived():
      try:
        p, d = _fake_model(tmp_path, with_error=False)
        s.correction_models_path = p
        r = post(live, material_query="PMMA", oxygen_pct=3, gravity="orbit", airflow_cm_s=10)
        assert r["verdict"] == "NO_DIRECT_EVIDENCE" and any("error has not been measured" in w for w in r["warnings"])  # no error -> no estimate
        p, d = _fake_model(tmp_path, with_error=True)
        s.correction_models_path = p
        r = post(live, material_query="PMMA", oxygen_pct=3, gravity="orbit", airflow_cm_s=10)
        assert r["verdict"] == "MODEL_ESTIMATE" and r["verdict_tier"] == "amber" and r["estimate"]["error"] == 1.0
        assert r["estimate"]["label"] == "Model estimate — not tested"
        r = post(live, material_query="PMMA", oxygen_pct=3, gravity="orbit", airflow_cm_s=999)   # outside valid_range
        assert r["verdict"] == "NO_DIRECT_EVIDENCE" and r["estimate"] is None and any("outside the model's valid range" in w for w in r["warnings"])
        r = post(live, material_query="PMMA", oxygen_pct=3, gravity="moon", airflow_cm_s=10)    # moon never gets an estimate
        assert r["verdict"] == "NO_DIRECT_EVIDENCE"
        r = post(live, material_query="Zorbium-7", gravity="orbit", airflow_cm_s=10, unknown_material_props={"char_yield_pct": 30})
        assert r["verdict"] == "NO_DIRECT_EVIDENCE"                                           # unknown: no 1g MOC input
      finally:
        s.correction_models_path = old


def test_formula_evaluator_is_safe():
    with pytest.raises(ValueError):
        correction._eval(__import__("ast").parse("__import__('os').system('x')", mode="eval"), {})
