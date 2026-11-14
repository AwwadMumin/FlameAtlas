"""Phase 0: every example validates against its Pydantic model; MOCK endpoints respond; errors use the standard format."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import api as M

from app.core.config import get_settings

EX = get_settings().docs_dir / "examples"
client = TestClient(app)

MODEL_FOR = {
    "presets": M.PresetsResponse, "materials_search": M.MaterialSearchResponse, "materials_search_empty": M.MaterialSearchResponse,
    "material_detail": M.MaterialDetailResponse, "material_evidence": M.MaterialEvidenceResponse,
    "assess_evidence": M.AssessResponse, "assess_sibal_iss": M.AssessResponse, "assess_no_direct_1g_only": M.AssessResponse, "assess_no_direct_moon": M.AssessResponse,
    "assess_unknown_material": M.AssessResponse, "assess_unknown_empty": M.AssessResponse,
    "coverage": M.CoverageResponse, "next_experiments": M.NextExperimentsResponse, "labels_queue": M.LabelQueueResponse,
    "label_saved": M.LabelOut, "validation": M.ValidationResponse, "health": M.HealthResponse,
    "experiment_detail": M.ExperimentDetailResponse, "about": M.AboutResponse, "error_404": M.ErrorResponse,
    "error_422": M.ErrorResponse, "demo_scenarios": M.DemoScenariosResponse,
}


@pytest.mark.parametrize("name", sorted(MODEL_FOR))
def test_example_matches_model(name):
    MODEL_FOR[name].model_validate(json.loads((EX / f"{name}.json").read_text()))


def test_all_examples_covered():
    names = {p.stem for p in EX.glob("*.json")}
    assert names - set(MODEL_FOR) == {"assess_model_estimate_SHAPE_ONLY"}


GETS = ["/api/health", "/api/presets", "/api/materials/search?q=acrylic", "/api/materials/pmma",
        "/api/materials/pmma/evidence", "/api/coverage/pmma", "/api/next-experiments?preset=iss", "/api/validation",
        "/api/admin/labels/queue", "/api/demo-scenarios", "/api/about", "/api/experiments/WSTF-013"]


@pytest.mark.parametrize("url", GETS)
def test_get_ok(url):
    assert client.get(url).status_code == 200


def test_assess_tiers():
    base = {"material_query": "acrylic", "oxygen_pct": 21, "pressure_kpa": 101.3, "gravity": "orbit"}
    assert client.post("/api/assess", json=base).json()["verdict"] == "EVIDENCE"
    assert client.post("/api/assess", json=base | {"gravity": "moon"}).json()["verdict"] == "NO_DIRECT_EVIDENCE"
    assert client.post("/api/assess", json=base | {"material_query": "PET"}).json()["verdict"] == "NO_DIRECT_EVIDENCE"
    r = client.post("/api/assess", json=base | {"material_query": "Zorbium", "gravity": "mars", "unknown_material_props": {"char_yield_pct": 30}}).json()
    assert r["verdict"] == "NO_DIRECT_EVIDENCE" and r["estimate"]["value"] == 29.5 and r["estimate"]["not_a_microgravity_limit"]


def test_error_format_404_and_422():
    r = client.get("/api/materials/nope")
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message", "details"}
    r = client.post("/api/assess", json={"material_query": "x", "oxygen_pct": 500})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_cors_header():
    r = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "*"


def test_no_numbers_invented_in_examples():
    """Every record in the assess example exists verbatim in experiments.json."""
    data = {e["experiment_id"]: e for e in json.loads((get_settings().data_dir / "experiments.json").read_text())}
    d = json.loads((EX / "assess_evidence.json").read_text())
    for g in d["evidence_groups"]:
        for rec in g["records"]:
            src = data[rec["experiment_id"]]
            for k in ("oxygen_pct", "pressure_kpa", "airflow_cm_s", "outcome_value", "doi"):
                assert rec[k] == src[k]
