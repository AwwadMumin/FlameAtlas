"""Phase 2 acceptance (needs loaded Mongo; run with MOCK=0 via the `live` client fixture)."""
import re

import pytest
from fastapi.testclient import TestClient

pymongo = pytest.importorskip("pymongo")
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != 872:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    get_settings().mock = False
    from app.main import app
    yield TestClient(app)
    get_settings().mock = True


def post(c, **kw):
    body = {"material_query": "acrylic", "oxygen_pct": 21, "pressure_kpa": 101, "gravity": "orbit"} | kw
    r = c.post("/api/assess", json=body)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("q", ["acrylic", "أكريليك", "اكريليك", "PMMA", "Plexiglas", "pmma"])
def test_resolve_pmma(live, q):
    assert live.get(f"/api/materials/search?q={q}").json()["matches"][0]["material"]["material_id"] == "pmma"


def test_no_false_material_match(live):
    for q in ("plexi glass", "Zorbium-7", "kevlar"):
        d = post(live, material_query=q)
        assert d["material"] is None and d["verdict"] == "NO_DIRECT_EVIDENCE", q


def test_pmma_iss_is_evidence(live):
    d = post(live)
    assert d["verdict"] == "EVIDENCE" and d["verdict_tier"] == "green" and d["material"]["material_id"] == "pmma"
    assert d["evidence_groups"] and "±1.5" in d["matched_tolerances"]["text"]
    assert all(r["gravity_bucket"] == "microgravity" for g in d["evidence_groups"] for r in g["records"])


def test_pet_orbit_no_direct(live):
    d = post(live, material_query="PET")
    assert d["verdict"] == "NO_DIRECT_EVIDENCE" and "1g evidence only" in d["verdict_reason"]
    assert d["nearest_evidence"] and all(n["gravity_bucket"] == "1g" for n in d["nearest_evidence"])


@pytest.mark.parametrize("g", ["moon", "mars"])
@pytest.mark.parametrize("mat", ["acrylic", "SIBAL", "PET"])
def test_moon_mars_never_evidence(live, g, mat):
    d = post(live, material_query=mat, gravity=g, oxygen_pct=34, pressure_kpa=56.5)
    assert d["verdict"] == "NO_DIRECT_EVIDENCE" and d["evidence_groups"] == []
    assert "interpolated" in d["verdict_reason"]


def test_smoke_records_never_burn_evidence(live):
    for mat in ("silicone", "polyimide", "cotton", "ptfe", "dbp", "polyurethane_foam"):
        d = post(live, material_query=mat, oxygen_pct=21, pressure_kpa=101)
        for g in d["evidence_groups"]:
            assert g["evidence_type"] != "smoke_particle_size"
            assert all(r["flammability_relevant"] and r["display_kind"] != "smoke" for r in g["records"])
        assert all(r["display_kind"] == "smoke" for r in d["smoke_detection"])
    ev = live.get("/api/materials/polyimide/evidence").json()
    assert all(r["flammability_relevant"] for g in ev["groups"] for r in g["records"])


def test_every_record_value_maps_to_db(live):
    from app.services import store
    d = post(live)
    for g in d["evidence_groups"]:
        for r in g["records"]:
            src = store.get_db().experiments.find_one({"experiment_id": r["experiment_id"]})
            for k in ("oxygen_pct", "pressure_kpa", "airflow_cm_s", "outcome_value", "outcome_unit", "doi", "source_ref"):
                assert r[k] == src[k], (r["experiment_id"], k)
            assert r["source_url"]


def test_summary_numbers_come_from_records_or_request(live):
    d = post(live)
    allowed = " ".join(str(v) for r in (x for g in d["evidence_groups"] for x in g["records"]) for v in r.values() if v is not None)
    allowed += " " + str(d["verdict_reason"]) + str(d["requested"])
    for n in re.findall(r"\d+(?:\.\d+)?", d["summary_text"]):
        assert n in allowed, n


def test_unknown_and_error_formats(live):
    assert live.get("/api/materials/nope").status_code == 404
    assert live.get("/api/experiments/nope").json()["error"]["code"] == "not_found"
    assert live.post("/api/assess", json={"material_query": "x", "oxygen_pct": 500}).status_code == 422


def test_catalog_endpoints(live):
    assert live.get("/api/presets").json()["presets"][2]["pressure_kpa"] == pytest.approx(56.53, abs=0.01)
    assert live.get("/api/about").json()["incidents"]
    assert live.get("/api/experiments/WSTF-013").json()["source_url"].startswith("https://ntrs.nasa.gov")
    assert live.get("/api/materials/pmma").json()["stats"]["records_total"] > 0


def test_question_adds_similarity(live):
    d = post(live, question="sooty flame on a black rod")
    sims = [r["similarity"] for g in d["evidence_groups"] for r in g["records"] if r["similarity"] is not None]
    assert all(s >= get_settings().similarity_threshold for s in sims)


def test_assess_is_fast(live):
    import time
    post(live)
    t = time.time(); post(live); assert time.time() - t < 1.5
