"""All 15 endpoints. Phase 0: MOCK=1 serves docs/examples/*.json; otherwise 501 until the phase that implements it."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import api as M
from app.services import assess as assess_svc, catalog, demo, health as health_svc

router = APIRouter(prefix="/api")
ERR = {404: {"model": M.ErrorResponse}, 422: {"model": M.ErrorResponse}}


def example(name: str) -> dict[str, Any]:
    p = get_settings().docs_dir / "examples" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def MOCK() -> bool:
    return get_settings().mock


def serve(name: str, phase: str):
    if get_settings().mock:
        return example(name)
    raise ApiError(501, "not_implemented", f"Implemented in {phase}. Run with MOCK=1 for example responses.")


@router.get("/health", response_model=M.HealthResponse)
def health():
    h = health_svc.check(get_settings())
    ok = h["mock"] or h["db"].get("connected")
    return M.HealthResponse(status="ok" if ok else "degraded", **h)


@router.get("/presets", response_model=M.PresetsResponse, responses=ERR)
def presets():
    return example("presets") if MOCK() else catalog.presets()


@router.get("/materials/search", response_model=M.MaterialSearchResponse, responses=ERR)
def materials_search(q: str = Query(min_length=1)):
    if not MOCK():
        return catalog.search(q)
    r = example("materials_search")
    if q.lower() not in {a.lower() for a in r["matches"][0]["material"]["aliases"]} | {"pmma", "acrylic"}:
        return example("materials_search_empty") | {"query": q}
    return r | {"query": q}


@router.get("/materials/{material_id}", response_model=M.MaterialDetailResponse, responses=ERR)
def material(material_id: str):
    if not MOCK():
        return catalog.material_detail(material_id)
    if material_id != "pmma":
        raise ApiError(404, "not_found", f"Unknown material_id '{material_id}'", {"material_id": material_id})
    return example("material_detail")


@router.get("/materials/{material_id}/evidence", response_model=M.MaterialEvidenceResponse, responses=ERR)
def material_evidence(material_id: str, gravity: str | None = None, evidence_type: str | None = None):
    if not MOCK():
        return catalog.material_evidence(material_id, gravity, evidence_type)
    if material_id != "pmma":
        raise ApiError(404, "not_found", f"Unknown material_id '{material_id}'", {"material_id": material_id})
    return example("material_evidence")


@router.post("/assess", response_model=M.AssessResponse, responses=ERR)
def assess(req: M.AssessRequest):
    if not MOCK():
        return assess_svc.run(req)
    q = req.material_query.lower()
    known = q in {"pmma", "acrylic", "أكريليك", "pet", "sibal"}
    if not known:
        return example("assess_unknown_material" if req.unknown_material_props else "assess_unknown_empty")
    if req.gravity in ("moon", "mars"):
        return example("assess_no_direct_moon")
    if q == "pet":
        return example("assess_no_direct_1g_only")
    if q == "sibal":
        return example("assess_sibal_iss")
    return example("assess_evidence")


@router.get("/coverage/{material_id}", response_model=M.CoverageResponse, responses=ERR)
def coverage(material_id: str):
    return serve("coverage", "Phase 5")


@router.get("/next-experiments", response_model=M.NextExperimentsResponse, responses=ERR)
def next_experiments(preset: str | None = None):
    return serve("next_experiments", "Phase 5")


@router.get("/validation", response_model=M.ValidationResponse, responses=ERR)
def validation():
    return serve("validation", "Phase 5")


@router.get("/admin/labels/queue", response_model=M.LabelQueueResponse, responses=ERR)
def labels_queue():
    return serve("labels_queue", "Phase 5")


@router.post("/admin/labels", response_model=M.LabelOut, responses=ERR)
def labels_save(body: M.LabelIn):
    return serve("label_saved", "Phase 5")


@router.get("/demo-scenarios", response_model=M.DemoScenariosResponse)
def demo_scenarios():
    return example("demo_scenarios") if MOCK() else demo.scenarios()


@router.get("/about", response_model=M.AboutResponse)
def about():
    return example("about") if MOCK() else catalog.about()


@router.get("/experiments/{experiment_id}", response_model=M.ExperimentDetailResponse, responses=ERR)
def experiment(experiment_id: str):
    if not MOCK():
        return catalog.experiment(experiment_id)
    if experiment_id != "WSTF-013":
        raise ApiError(404, "not_found", f"Unknown experiment_id '{experiment_id}'", {"experiment_id": experiment_id})
    return example("experiment_detail")
