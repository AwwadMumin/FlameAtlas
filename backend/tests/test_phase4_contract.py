"""Phase 4: the 4 demo flows return complete, contract-valid responses; error format; CORS; OpenAPI; Postman."""
import json

import pytest
from helpers import EXPECTED
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.api import AssessResponse, DemoScenariosResponse, VERDICT_META, Verdict
from app.services.records import to_record


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


def test_demo_scenarios_cover_the_four_flows(live):
    d = DemoScenariosResponse.model_validate(live.get("/api/demo-scenarios").json())
    assert [s.id for s in d.scenarios] == ["pmma_iss", "sibal_iss", "pet_exploration", "unknown_mars"]


@pytest.mark.parametrize("sid,verdict", [("pmma_iss", "EVIDENCE"), ("sibal_iss", "EVIDENCE"),
                                         ("pet_exploration", "NO_DIRECT_EVIDENCE"), ("unknown_mars", "NO_DIRECT_EVIDENCE")])
def test_demo_flow_complete_and_contract_valid(live, sid, verdict):
    req = next(s for s in live.get("/api/demo-scenarios").json()["scenarios"] if s["id"] == sid)["request"]
    r = live.post("/api/assess", json=req)
    assert r.status_code == 200
    d = AssessResponse.model_validate(r.json())            # schema test
    assert d.verdict.value == verdict
    meta = VERDICT_META[d.verdict]
    assert d.verdict_label == meta["label"] and d.verdict_tier == meta["tier"] and d.verdict_reason and d.summary_text
    assert d.summary_source in ("template", "llm_checked") and d.matched_tolerances.text
    assert d.requested["oxygen_pct"] is not None and d.requested["pressure_kpa"] is not None   # preset resolved
    if d.verdict != Verdict.EVIDENCE:
        assert d.empty_state_message
    if d.verdict == Verdict.EVIDENCE:
        assert d.evidence_groups and all(rec.source_url and rec.display_text for g in d.evidence_groups for rec in g.records)
    if d.material:                                          # chart-ready: exactly one requested point
        assert sum(p.is_requested_point for p in d.scatter_points) == 1 and len(d.scatter_points) > 1
        assert d.nearest_evidence or d.evidence_groups
    else:
        assert d.estimate and d.estimate.not_a_microgravity_limit and d.estimate.value == 29.5


def test_every_record_has_a_source_link():
    for e in json.loads((get_settings().data_dir / "experiments.json").read_text()):
        u = to_record(e).source_url
        assert u and u.startswith("http"), e["experiment_id"]


def test_errors_use_standard_format(live):
    for r in (live.post("/api/assess", json={"material_query": "   "}),
              live.post("/api/assess", json={"material_query": "pmma", "gravity": "venus"}),
              live.post("/api/assess", json={"material_query": "pmma", "preset_id": "nope"}),
              live.post("/api/assess", content="not json", headers={"content-type": "application/json"}),
              live.get("/api/materials/search")):
        assert r.status_code == 422 and set(r.json()["error"]) == {"code", "message", "details"}, r.text
    for url in ("/api/materials/zzz", "/api/materials/zzz/evidence", "/api/experiments/zzz", "/api/nothing"):
        r = live.get(url)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", url


def test_cors_preflight_and_origin_list(live):
    r = live.options("/api/assess", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                             "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"


def test_openapi_and_docs(live):
    spec = live.get("/openapi.json").json()
    assert len(spec["paths"]) == 17 and "AssessResponse" in spec["components"]["schemas"]   # 14 paths; /api/admin/labels is the POST
    assert live.get("/docs").status_code == 200


def test_postman_collection_matches_api():
    col = json.loads((get_settings().docs_dir / "postman_collection.json").read_text())
    names = " ".join(i["name"] for i in col["item"])
    for needle in ("/api/health", "/api/assess — ISS cabin", "/api/validation", "/api/admin/labels", "/api/next-experiments", "/api/coverage"):
        assert needle in names, needle
    assert col["variable"][0]["key"] == "baseUrl"
