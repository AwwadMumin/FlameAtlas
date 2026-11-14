"""Read-only catalog endpoints: presets, material detail/evidence, experiment detail, about."""
from __future__ import annotations

import json

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import api as M
from app.services import evidence as ev, materials, store
from app.services.assess import PSI_TO_KPA, _findings, _investigations
from app.services.records import gravity_bucket, to_record


def presets() -> M.PresetsResponse:
    g5 = next(g for g in store.knowledge()["gap_fill"] if g["id"] == "G5")
    ps = [M.Preset(id=p["id"], name=p["name"], pressure_psia=p["pressure_psia"], pressure_kpa=round(p["pressure_psia"] * PSI_TO_KPA, 2),
                   o2_pct=p["o2_pct"], gravity=p["gravity"], source=p["source"]) for p in g5["presets"]]
    lv = [M.GravityLevel(key=k, g=g, bucket={"orbit": "microgravity", "earth": "1g"}.get(k, "none"), has_direct_data=k in ("orbit", "earth"),
                         note=None if k in ("orbit", "earth") else "No direct data: nearest µg and 1g evidence only. "
                         + ("Mars 0.38 g is general knowledge; cite a NASA source if shown." if k == "mars" else ""))
          for k, g in g5["gravity_levels_g"].items()]
    return M.PresetsResponse(presets=ps, gravity_levels=lv)


def search(q: str) -> M.MaterialSearchResponse:
    ms = materials.search(q)
    return M.MaterialSearchResponse(query=q, matches=ms, empty_state_message=None if ms else
                                    f"No material matches '{q}'. You can still run an assessment for an unknown material.")


def _material(mid: str) -> dict:
    m = store.materials().get(mid)
    if not m:
        raise ApiError(404, "not_found", f"Unknown material_id '{mid}'", {"material_id": mid})
    return m


def material_detail(mid: str) -> M.MaterialDetailResponse:
    m = _material(mid)
    db = store.get_db()
    stats = {"records_total": db.experiments.count_documents({"material_id": mid}),
             "records_microgravity": db.experiments.count_documents({"material_id": mid, "gravity_level": "microgravity"}),
             "records_1g": db.experiments.count_documents({"material_id": mid, "gravity_level": {"$ne": "microgravity"}}),
             "records_smoke_only": db.experiments.count_documents({"material_id": mid, "flammability_relevant": False}),
             "records_with_outcome": db.experiments.count_documents(
                 {"material_id": mid, "flammability_relevant": True, "outcome_type": {"$ne": "conditions_only"}})}
    card = materials.to_card(m)
    return M.MaterialDetailResponse(material=card, stats=stats, warnings=card.warnings)


def material_evidence(mid: str, gravity: str | None, evidence_type: str | None) -> M.MaterialEvidenceResponse:
    _material(mid)
    if gravity and gravity not in ev.GRAVITY_BUCKET:
        raise ApiError(422, "validation_error", f"Unknown gravity '{gravity}'", {"allowed": list(ev.GRAVITY_BUCKET)})
    rows = ev.material_rows(mid)
    b = ev.GRAVITY_BUCKET.get(gravity) if gravity else None
    if gravity and b is None:
        return M.MaterialEvidenceResponse(material_id=mid, groups=[],
                                          empty_state_message=f"No direct data for gravity '{gravity}' (only microgravity and 1g).")
    if b:
        rows = [e for e in rows if gravity_bucket(e["gravity_level"]) == b]
    if evidence_type:
        rows = [e for e in rows if e["evidence_type"] == evidence_type]
    groups = ev.group(rows, None, None, None)
    for g in groups:  # full listing endpoint: no per-group cap
        g.records = [to_record(e) for e in sorted((x for x in rows if x["evidence_type"] == g.evidence_type), key=lambda x: x["experiment_id"])]
    smoke = [to_record(e) for e in ev.smoke_rows(mid, 100)] if not evidence_type else []
    return M.MaterialEvidenceResponse(material_id=mid, groups=groups, smoke_detection=smoke,
                                      empty_state_message=None if groups or smoke else "No records match these filters.")


def experiment(eid: str) -> M.ExperimentDetailResponse:
    db = store.get_db()
    e = db.experiments.find_one({"experiment_id": eid}, {"_id": 0})
    if not e:
        raise ApiError(404, "not_found", f"Unknown experiment_id '{eid}'", {"experiment_id": eid})
    c = db.evidence_cards.find_one({"experiment_id": eid}, {"_id": 0, "text": 1})
    rec = to_record(e)
    inv = _investigations([e], 1)
    return M.ExperimentDetailResponse(record=rec, card_text=c["text"] if c else None, source_url=rec.source_url,
                                      findings=_findings([e], 10), investigation=inv[0] if inv else None, extra=e.get("extra"),
                                      smoke_only=e.get("flammability_relevant") is False)


def about() -> M.AboutResponse:
    k = store.knowledge()
    meta = json.loads((get_settings().data_dir / "materials.json").read_text(encoding="utf-8"))["metadata"]
    invs = [M.InvestigationCard(accession=i["accession"], acronym=i.get("acronym"), title=i["title"], doi=i.get("doi"),
                                objective=i.get("objective"), hypothesis=i.get("hypothesis")) for i in k["investigations"]]
    lic = sorted(x for x in store.get_db().experiments.distinct("license") if x)
    return M.AboutResponse(investigations=invs, provenance={"built_from": meta["built_from"], "note": meta["note"], "version": meta["version"]},
                           licenses=lic, incidents=k["incidents"], earth_benefits=k["earth_benefits"])
