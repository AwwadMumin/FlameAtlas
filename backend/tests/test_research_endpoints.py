"""Frontend adapter endpoints: /api/experiments, /api/compare (deterministic comparability), /api/ask (guarded retrieval)."""
import pytest
from fastapi.testclient import TestClient
from helpers import EXPECTED

from app.core.config import get_settings
from app.services import summary


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); old = (s.mock, s.anthropic_api_key); s.mock = False; s.anthropic_api_key = None
    from app.main import app
    yield TestClient(app)
    s.mock, s.anthropic_api_key = old


def cmp(live, ids):
    r = live.post("/api/compare", json={"experiment_ids": ids})
    assert r.status_code == 200, r.text
    return r.json()


def test_experiments_list_shape_and_filters(live):
    d = live.get("/api/experiments?limit=2000").json()
    assert d["total"] == EXPECTED["experiments"] == d["returned"]
    e = next(x for x in d["experiments"] if x["id"] == "WSTF-013")
    assert e["gravity"] == "Earth gravity (1g)" and e["source_id"] == "WSTF-013" and e["source_url"].startswith("https://ntrs") and e["oxygen"] is None
    assert all(x["source_id"] == x["id"] for x in d["experiments"])
    p = live.get("/api/experiments?material=pmma&gravity=orbit&include_smoke=false").json()
    assert p["total"] > 0 and all(x["material_id"] == "pmma" and x["gravity"] == "Microgravity" for x in p["experiments"])
    assert live.get("/api/experiments?gravity=moon").json()["total"] == 0
    assert live.get("/api/experiments?q=LINK2018-S2-L0").json()["total"] >= 9


def test_compare_same_quantity_and_differences(live):
    d = cmp(live, ["WSTF-013", "WSTF-044"])
    assert d["reference_id"] == "WSTF-013" and d["summary_source"] == "template"
    it = {i["experiment_id"]: i for i in d["items"]}
    assert it["WSTF-044"]["comparable"] is True and any("5.0%" in x and "19.0% vs 14.0%" in x for x in it["WSTF-044"]["differences"])
    ids = {l["id"] for l in d["limitations"]}
    assert "LIM-procedure" in ids and "LIM-o2" in ids and d["methodology"] and len(d["sources"]) == 2
    assert all(s["url"] for s in d["sources"]) and d["generated_at"]


def test_compare_refuses_to_mix_quantities_units_and_non_outcomes(live):
    d = cmp(live, ["WSTF-013", "LINK2018-S2-L01", "BASS2-001", "WSTF-044"])
    it = {i["experiment_id"]: i for i in d["items"]}
    assert not it["LINK2018-S2-L01"]["comparable"] and "different quantities" in it["LINK2018-S2-L01"]["reason"]
    assert not it["BASS2-001"]["comparable"] and "tested at" in it["BASS2-001"]["reason"] and it["BASS2-001"]["differences"] == []
    assert it["WSTF-044"]["comparable"] and "1 of 3" in d["summary"]


def test_compare_flags_unit_mismatch_and_cross_gravity(live):
    d = cmp(live, ["LINK2018-S1-B9-1", "LINK2018-S2-L01"])
    it = d["items"][1]
    assert it["comparable"] is True and any(l["id"] == "LIM-gravity" for l in d["limitations"]) and any(l["category"] == "interpretation" for l in d["limitations"])
    assert "x10^-3 cm/s" in it["reason"]            # unit shown exactly as printed, never converted
    from app.services import store
    from app.services.research import _hard_block
    a = store.get_db().experiments.find_one({"experiment_id": "LINK2018-S1-B9-1"}, {"_id": 0}); b = dict(a, experiment_id="X", outcome_unit="mm/s")
    assert "different units" in _hard_block(a, b) and "no conversion" in _hard_block(a, b)


def test_compare_loi_and_moc_never_mixed():
    from app.services.research import _hard_block
    base = {"flammability_relevant": True, "outcome_type": "threshold", "material_id": "pmma", "outcome_value": 1.0}
    r = _hard_block(dict(base, experiment_id="A", outcome_variable="LOI", outcome_unit="% O2"), dict(base, experiment_id="B", outcome_variable="MOC", outcome_unit="% O2"))
    assert "never mixed" in r
    s = _hard_block(dict(base, experiment_id="A", outcome_variable="MOC", outcome_unit="% O2", flammability_relevant=False), dict(base, experiment_id="B", outcome_variable="MOC", outcome_unit="% O2"))
    assert "smoke" in s


def test_compare_errors(live):
    assert live.post("/api/compare", json={"experiment_ids": ["WSTF-013"]}).status_code == 422
    r = live.post("/api/compare", json={"experiment_ids": ["WSTF-013", "NOPE"]})
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message", "details"}
    assert live.post("/api/compare", json={"experiment_ids": ["WSTF-013", "WSTF-013"]}).status_code == 422


def test_ask_retrieval_and_conditions(live):
    d = live.post("/api/ask", json={"question": "How does PMMA behave at 18.5% oxygen in microgravity?"}).json()
    assert d["answer_source"] == "template" and d["records"] and all(r["material_id"] == "pmma" and r["gravity_bucket"] == "microgravity" for r in d["records"])
    assert {c["source_id"] for c in d["citations"]} == {r["experiment_id"] for r in d["records"]} and all(c["url"] for c in d["citations"])
    d = live.post("/api/ask", json={"question": "flame spread of acrylic on earth at 21% oxygen"}).json()
    assert all(r["gravity_bucket"] == "1g" for r in d["records"])


def test_ask_no_match_and_moon(live):
    d = live.post("/api/ask", json={"question": "tell me about zorbium"}).json()
    assert d["records"] == [] and d["answer"].startswith("No direct evidence") and d["citations"] == []
    d = live.post("/api/ask", json={"question": "what is the capital of France"}).json()
    assert d["records"] == []
    d = live.post("/api/ask", json={"question": "how does acrylic burn on the moon", "experiment_ids": ["WSTF-013"]}).json()
    assert d["answer"].startswith("No direct evidence for Moon or Mars") and "Moon or Mars" in d["limitations"]
    assert live.post("/api/ask", json={"question": "hi"}).status_code == 422
    assert live.post("/api/ask", json={"question": "anything", "experiment_ids": ["NOPE"]}).status_code == 404


def test_llm_guard_rejects_invented_numbers_and_falls_back(live, monkeypatch):
    s = get_settings(); s.anthropic_api_key = "test-key"
    try:
        monkeypatch.setattr(summary, "complete", lambda system, user: "WSTF-013 shows MOC 23.4% O2.")        # 23.4 is in no record
        d = cmp(live, ["WSTF-013", "WSTF-044"])
        assert d["summary_source"] == "template" and "23.4" in d["summary_fallback_reason"]
        a = live.post("/api/ask", json={"question": "acrylic limit", "experiment_ids": ["WSTF-013"]}).json()
        assert a["answer_source"] == "template" and "23.4" in a["answer_fallback_reason"]
        monkeypatch.setattr(summary, "complete", lambda system, user: "WSTF-013 reports MOC = 19.0 % O2 and WSTF-044 reports 14.0 % O2; the O2 differs by 5.0 % and the test procedures differ.")
        d = cmp(live, ["WSTF-013", "WSTF-044"])
        assert d["summary_source"] == "llm_checked" and d["summary_fallback_reason"] is None
    finally:
        s.anthropic_api_key = None


def test_ask_uses_record_list_when_llm_has_nothing_to_add(live, monkeypatch):
    s = get_settings(); s.anthropic_api_key = "test-key"
    try:
        monkeypatch.setattr(summary, "complete", lambda system, user: "not available in the retrieved records")
        a = live.post("/api/ask", json={"question": "acrylic limit", "experiment_ids": ["WSTF-013"]}).json()
        assert a["answer_source"] == "template" and "WSTF-013" in a["answer"] and "found nothing to add" in a["answer_fallback_reason"]
    finally:
        s.anthropic_api_key = None
