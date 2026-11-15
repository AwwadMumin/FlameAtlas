"""Burn-outcome model: three cases (tested / no research / Earth-only), range rule, labels, honesty of the validation numbers."""
import pytest
from helpers import EXPECTED
from fastapi.testclient import TestClient

pymongo = pytest.importorskip("pymongo")
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    get_settings().mock = False
    from app.main import app
    yield TestClient(app)
    get_settings().mock = True


def post(c, **kw):
    r = c.post("/api/assess", json={"material_query": "acrylic", "oxygen_pct": 21, "pressure_kpa": 101, "gravity": "orbit"} | kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_tested_material_keeps_evidence_and_gets_a_cross_check(live):
    d = post(live)
    assert d["verdict"] == "EVIDENCE" and d["evidence_groups"]
    b = d["burn_prediction"]
    assert b["role"] == "cross_check" and b["basis"] == "tested_here" and b["label"] == "Model estimate — not tested"


def test_earth_only_material_is_estimated(live):
    d = post(live, material_query="PET")
    b = d["burn_prediction"]
    assert d["verdict"] == "MODEL_ESTIMATE" and d["verdict_tier"] == "amber" and b["basis"] == "earth_only" and b["material_group"] is None
    assert 0 <= b["interval_95"][0] <= b["probability_sustained"] <= b["interval_95"][1] <= 1
    assert d["nearest_evidence"] and all(n["gravity_bucket"] == "1g" for n in d["nearest_evidence"])   # 1g stays separate, as context


def test_unknown_material_has_a_wider_interval_than_a_known_one(live):
    unk = post(live, material_query="Zorbium-7")["burn_prediction"]
    known = post(live)["burn_prediction"]
    assert unk["basis"] == "no_research" and unk["material_group"] is None and known["material_group"] == "PMMA"
    assert (unk["interval_95"][1] - unk["interval_95"][0]) > 2 * (known["interval_95"][1] - known["interval_95"][0])


def test_model_never_predicts_outside_its_range_and_never_for_moon_mars_or_1g(live):
    d = post(live, material_query="PET", oxygen_pct=30)
    assert d["verdict"] == "NO_DIRECT_EVIDENCE" and d["burn_prediction"] is None and any("outside" in w and "trained on" in w for w in d["warnings"])
    d = post(live, material_query="PET", airflow_cm_s=500)
    assert d["verdict"] == "NO_DIRECT_EVIDENCE" and d["burn_prediction"] is None
    for g in ("moon", "mars"):
        d = post(live, material_query="PET", gravity=g)
        assert d["burn_prediction"] is None and d["verdict"] == "NO_DIRECT_EVIDENCE", g
    for g in ("earth", "1g"):                       # 1g keeps its own evidence; the microgravity model is never applied to it
        assert post(live, material_query="PET", gravity=g)["burn_prediction"] is None, g


def test_only_allowed_label_methods_train_the_model(live):
    b = post(live)["burn_prediction"]
    s = get_settings()
    assert set(b["trained_on"]["by_label_method"]) <= set(s.model_label_methods)
    assert not any("keyword" in k for k in b["trained_on"]["by_label_method"])
    assert b["trained_on"]["n_runs"] == sum(b["trained_on"]["by_label_method"].values()) == 136


def test_validation_is_reported_as_measured(live):
    v = post(live)["burn_prediction"]["validation"]
    assert v["method"] == "leave-one-investigation-out" and v["pooled_n"] == 136
    assert v["beats_baseline"] == (v["model_brier"] < v["baseline_brier"])
    assert ("did better" in v["statement"]) == v["beats_baseline"]
    assert {i["investigation"] for i in v["per_investigation"]} >= {"BASS", "BASS-II"}


def test_deterministic_and_airflow_assumption_is_disclosed(live):
    a, b = post(live, material_query="PET"), post(live, material_query="PET")
    assert a["burn_prediction"]["probability_sustained"] == b["burn_prediction"]["probability_sustained"]
    assert "averaged" in a["burn_prediction"]["airflow_assumption"]
    assert post(live, material_query="PET", airflow_cm_s=10)["burn_prediction"]["airflow_assumption"] is None


def test_summary_never_states_a_number_outside_the_context(live):
    d = post(live, material_query="PET")
    pct = round(d["burn_prediction"]["probability_sustained"] * 100)
    assert f"{pct}%" in d["summary_text"] and "not tested" in d["summary_text"].lower()
