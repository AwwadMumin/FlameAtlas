"""1g baseline: standard Test 1 procedure vs other configurations (Hirsch et al. 2011)."""
import json

import pytest
from helpers import EXPECTED
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.earth_to_space import procedure


@pytest.mark.parametrize("cfg,expected", [
    ("upward burning; Chemical igniter", "standard"),
    ("upward burning; Extruded, chemical igniter", "standard"),
    ("upward burning; Standard mounting", "standard"),
    ("upward burning; 2.5-in. wide, standard mounting", "standard"),
    ("upward burning; Hot-wire", "non_standard"),
    ("upward burning; Cast, hot-wire", "non_standard"),
    ("upward burning; Exposed edge", "non_standard"),
    ("upward burning; At least 1-in. burn (hot-wire)", "non_standard"),
    ("upward burning; At least 2-in. burn (hot-wire)", "non_standard"),
    ("upward burning; 1/8-in. dia rod", "not_stated"),      # says nothing about igniter/mounting: never assumed standard
    ("upward burning; 4 mil", "not_stated"),
    (None, "not_stated"),
])
def test_procedure_classification(cfg, expected):
    assert procedure({"configuration": cfg}) == expected


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); s.mock = False; old = s.anthropic_api_key; s.anthropic_api_key = None
    from app.main import app
    yield TestClient(app)
    s.mock, s.anthropic_api_key = True, old


def post(c, **kw):
    r = c.post("/api/assess", json={"material_query": "acrylic", "oxygen_pct": 21, "pressure_kpa": 101, "gravity": "orbit"} | kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_no_hot_wire_row_is_ever_standard(live):
    from app.services import store
    rows = list(store.get_db().experiments.find({"evidence_type": "flammability_limit_1g_MOC_ULOI"}, {"_id": 0}))
    assert len(rows) == 59
    for e in rows:
        cfg = (e["configuration"] or "").lower()
        if "hot-wire" in cfg or "exposed edge" in cfg or "at least" in cfg:
            assert procedure(e) == "non_standard", e["experiment_id"]


def test_pmma_baseline_separates_standard_from_other_configurations(live):
    e = post(live)["earth_vs_space"]
    assert e["baseline_1g"]["standard_moc_values"] == [19.0, 19.0]
    assert "standard NASA-STD-6001 Test 1 procedure = 19.0% O2" in e["comparison_text"] and "14.0% O2" in e["comparison_text"]
    by = {m["experiment_id"]: m["procedure"] for m in e["baseline_1g"]["moc_values"]}
    assert by["WSTF-044"] == "non_standard" and by["WSTF-013"] == "standard" and by["WSTF-050"] == "not_stated"
    assert all("configuration" in m for m in e["baseline_1g"]["moc_values"]) and e["baseline_1g"]["procedure_note"]


def test_banner_uses_standard_procedure_comparator(live, tmp_path):
    from app.services import evidence as ev
    s = get_settings(); old = s.derived_dir
    rows = ev.material_rows("pmma")
    cand = next(e for e in rows if e["source_investigation"] == "BASS" and e["flame_behavior_notes"] and 16.5 <= e["oxygen_pct"] < 19.0)   # above 14.0, below standard 19.0
    try:
        s.derived_dir = tmp_path
        (tmp_path / "outcome_labels.json").write_text(json.dumps([{"experiment_id": cand["experiment_id"], "label": "sustained_burn", "quote": "q", "labelled_by": "t", "status": "confirmed"}]))
        e = post(live)["earth_vs_space"]
        assert e["one_g_not_conservative"] is True and "standard-procedure 1g MOC of 19.0% O2" in e["banner"]
    finally:
        s.derived_dir = old


def test_validation_counts_standard_comparator_separately():
    from app.services.validation import old_method_test
    def moc(i, v, cfg):
        return {"experiment_id": i, "evidence_type": "flammability_limit_1g_MOC_ULOI", "outcome_variable": "MOC", "outcome_value": v, "pressure_kpa": 101.35, "configuration": cfg,
                "gravity_level": "1g (ground)", "material_variant": "v", "source_ref": "r", "doi": None, "source_file": "https://x"}
    def ug(i, o2):
        return {"experiment_id": i, "gravity_level": "microgravity", "oxygen_pct": o2, "pressure_kpa": 100.0, "evidence_type": "solid_burn_test", "source_ref": "r", "doi": "d", "source_file": "f"}
    rows = [moc("S", 19.0, "upward burning; Chemical igniter"), moc("H", 14.0, "upward burning; Cast, hot-wire"), ug("a", 16.0), ug("b", 20.0)]
    lab = lambda l: {"label": l, "quote": "q", "labelled_by": "t", "status": "confirmed"}  # noqa: E731
    o = old_method_test({"a": lab("sustained_burn"), "b": lab("no_ignition")}, {"x": rows})
    assert o["n_burn_below_standard_moc"] == 1 and o["n_nonburn_above_standard_moc"] == 1      # 16 < 19 and 20 > 19 (standard)
    assert o["n_burn_below_moc"] == 0 and o["n_burn_below_moc_variant_dependent"] == 1          # 16 is above the hot-wire 14: configuration-dependent only
    assert "STANDARD Test 1 procedure" in o["definition"]
