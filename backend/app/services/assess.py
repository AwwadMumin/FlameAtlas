"""POST /api/assess orchestration (Phase 2: template summary only)."""
from __future__ import annotations

import datetime as dt
from collections import Counter

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.api import (Estimate, AssessRequest, AssessResponse, Finding, GapCell, InvestigationCard, ScatterPoint, Verdict, VERDICT_META)
from app.services import correction, earth_to_space, evidence as ev, materials, store
from app.services.records import gravity_bucket, to_record

PSI_TO_KPA = 6.894757


def _presets() -> dict[str, dict]:
    g5 = next(g for g in store.knowledge()["gap_fill"] if g["id"] == "G5")
    return {p["id"]: p for p in g5["presets"]}


def _findings(rows: list[dict], n: int = 5) -> list[Finding]:
    c = Counter(f for r in rows for f in (r.get("finding_ids") or []))
    F = store.findings()
    return [Finding(id=i, claim=F[i]["claim"], page=F[i].get("page"), section=F[i].get("section"), safety_area=F[i].get("safety_area"))
            for i, _ in c.most_common(n) if i in F]


def _investigations(rows: list[dict], n: int = 3) -> list[InvestigationCard]:
    I, out, seen = store.investigations(), [], set()
    for r in rows:
        a = r.get("psi_id")
        if a and a in I and a not in seen:
            seen.add(a)
            i = I[a]
            out.append(InvestigationCard(accession=a, acronym=i.get("acronym"), title=i["title"], doi=i.get("doi"),
                                         objective=i.get("objective"), hypothesis=i.get("hypothesis"), landing_page=r.get("psi_url")))
    return out[:n]


def _scatter(rows, o2, p) -> list[ScatterPoint]:
    pts = [ScatterPoint(o2=e["oxygen_pct"], pressure_kpa=e.get("pressure_kpa"), gravity=gravity_bucket(e["gravity_level"]),
                        outcome=e.get("outcome_class") or e.get("outcome_type"), experiment_id=e["experiment_id"])
           for e in rows if e.get("oxygen_pct") is not None]
    pts += [ScatterPoint(o2=e["outcome_value"], pressure_kpa=e.get("pressure_kpa"), gravity="1g", outcome="MOC threshold (1g, upward)",
                         experiment_id=e["experiment_id"]) for e in rows if e.get("outcome_variable") == "MOC" and e.get("outcome_value") is not None]
    pts.append(ScatterPoint(o2=o2, pressure_kpa=p, gravity="requested", outcome=None, is_requested_point=True))
    return pts


def run(req: AssessRequest) -> AssessResponse:
    from app.services import summary
    resp = summary.finalize(_assess(req), req)
    log(req, resp)
    return resp


def _assess(req: AssessRequest) -> AssessResponse:
    o2, p = req.oxygen_pct, req.pressure_kpa
    if req.preset_id:
        pr = _presets().get(req.preset_id)
        if pr is None:
            raise ApiError(422, "validation_error", f"Unknown preset_id '{req.preset_id}'", {"allowed": list(_presets())})
        if pr:
            o2 = o2 if o2 is not None else pr["o2_pct"]
            p = p if p is not None else round(pr["pressure_psia"] * PSI_TO_KPA, 2)
    flow = req.airflow_cm_s
    requested = req.model_dump(mode="json") | {"oxygen_pct": o2, "pressure_kpa": p}
    tol = ev.tolerances()
    match = materials.resolve(req.material_query)
    if match is None:
        from app.services import unknown_material
        return unknown_material.assess(req, requested, tol)

    m = match.material
    warnings = list(m.warnings)
    r = ev.retrieve(m.material_id, req.material_variant, req.gravity, o2, p, flow, req.question)
    near = ev.nearest(r.rows, o2, p, flow)
    smoke = [to_record(e) for e in ev.smoke_rows(m.material_id)]
    if req.material_variant and not r.rows:
        warnings.append(f"No records for variant '{req.material_variant}'; pick one from material.variants.")

    if o2 is None:
        v, reason = Verdict.NO_DIRECT_EVIDENCE, "No oxygen level given (oxygen_pct or preset_id), so the request cannot be matched to tested conditions."
    elif r.bucket is None:
        v = Verdict.NO_DIRECT_EVIDENCE
        reason = (f"Gravity '{req.gravity}' is outside the data domain: data exists only for microgravity and 1g, and values are never "
                  f"interpolated between them. Nearest microgravity and 1g evidence is shown.")
    elif r.matched:
        v = Verdict.EVIDENCE
        reason = f"{len(r.matched)} tested record(s) for {m.name_en} at {r.bucket}, {tol.text}."
    elif r.bucket == "microgravity" and not m.has_microgravity_evidence:
        v, reason = Verdict.NO_DIRECT_EVIDENCE, f"{m.name_en} has 1g evidence only; no microgravity tests exist in the data."
    else:
        v, reason = Verdict.NO_DIRECT_EVIDENCE, f"No tested record for {m.name_en} at {r.bucket} {tol.text}."

    est = None
    if v == Verdict.NO_DIRECT_EVIDENCE and r.bucket == "microgravity" and o2 is not None:
        mocs = earth_to_space._moc_rows(r.rows)
        moc = min(mocs, key=lambda e: ev.distance(e, o2, p, flow)) if mocs else None
        cr = correction.estimate({"moc_1g_pct": moc["outcome_value"] if moc else None, "airflow_cm_s": flow, "pressure_kpa": p,
                                  "thickness_mm": req.thickness_mm, "oxygen_pct": o2})
        if cr.status == "configured" and cr.message:
            warnings.append(cr.message)
        if cr.applicable:
            v = Verdict.MODEL_ESTIMATE
            est = Estimate(kind="model_estimate", label="Model estimate — not tested", value=cr.value, unit=cr.unit, error=cr.error,
                           error_unit=cr.error_unit, inputs={**cr.inputs, "moc_source": moc["experiment_id"] if moc else None},
                           equation=cr.model["equation"], citation=cr.model["citation"], page=cr.model["page"])
            reason = (f"No tested record at these conditions. In-domain model estimate of the microgravity limit: {cr.value}% O2 "
                      f"(± {cr.error} {cr.error_unit}); model: {cr.model['citation']}, p. {cr.model['page']}. Not tested.")
    bp = None
    if o2 is not None and r.bucket == "microgravity" and v in (Verdict.EVIDENCE, Verdict.NO_DIRECT_EVIDENCE):
        from app.services import predictor
        if v == Verdict.EVIDENCE:
            role, basis = "cross_check", "tested_here"
        else:
            has_1g = any(gravity_bucket(e["gravity_level"]) == "1g" for e in r.rows)
            role = "estimate"
            basis = (("earth_only" if has_1g else "smoke_only" if smoke else "no_research") if not m.has_microgravity_evidence else "not_tested_at_these_conditions")
        try:
            bp, why = predictor.describe(predictor.CATALOG_TO_GROUP.get(m.material_id), o2, flow, role, basis, p)
        except Exception as e:  # noqa: BLE001  (a model failure must never break the evidence answer)
            bp, why = None, f"model unavailable ({type(e).__name__})"
        if bp is None:
            warnings.append(f"No model estimate: {why}")
        elif role == "estimate":
            v = Verdict.MODEL_ESTIMATE
            lead = {"earth_only": f"{m.name_en} has Earth (1g) research only, no microgravity test.",
                    "no_research": f"No NASA research on {m.name_en} was found in the data.",
                    "smoke_only": f"{m.name_en} has only smoke/detection tests (heated, not burned) in the NASA data, and no burn test.",
                    "not_tested_at_these_conditions": f"No tested record for {m.name_en} at these conditions."}[basis]
            reason = f"{lead} {bp.statement}"
    meta = VERDICT_META[v]
    shown = r.shown if v == Verdict.EVIDENCE else []
    groups = ev.group(shown, o2, p, flow, r.sims)
    ctx = shown or [e for e in r.rows if e["experiment_id"] in {x.record.experiment_id for x in near}]
    summary = template_summary(m.name_en, v, reason, groups, near)
    gaps = [] if v == Verdict.EVIDENCE else [GapCell(material_id=m.material_id, o2_pct=o2, pressure_kpa=p, gravity=req.gravity,
            suggested_test="Suggested test (not a result)", reason="No tested record at this point.")]
    resp = AssessResponse(
        verdict=v, verdict_label=meta["label"], verdict_tier=meta["tier"], verdict_reason=reason,
        empty_state_message=None if v == Verdict.EVIDENCE else "No tested data for this material at these conditions. Nearest evidence is shown instead.",
        material=m, material_resolved_as=f"{match.match_type} match ({match.score})", requested=requested, matched_tolerances=tol,
        evidence_groups=groups, smoke_detection=smoke, earth_vs_space=earth_to_space.build(r.rows, o2, p, flow), estimate=est, burn_prediction=bp,
        nearest_evidence=near, findings=_findings(ctx), investigations=_investigations(ctx), scatter_points=_scatter(r.rows, o2, p),
        summary_text=summary, summary_source="template", warnings=warnings, gaps=gaps)
    return resp


def template_summary(name: str, v: Verdict, reason: str, groups, near) -> str:
    if v == Verdict.EVIDENCE:
        top = groups[0].records[0] if groups and groups[0].records else None
        s = f"{name}: EVIDENCE. {reason}"
        if top:
            s += f" Closest record {top.experiment_id}: {top.display_text} Source: {top.source_ref}."
        return s
    s = f"{name}: {'MODEL ESTIMATE (not tested)' if v == Verdict.MODEL_ESTIMATE else 'NO DIRECT EVIDENCE'}. {reason}"
    if near:
        n = near[0]
        s += f" Nearest {n.gravity_bucket} record {n.record.experiment_id}: {n.record.display_text} Source: {n.record.source_ref}."
    return s


def log(req: AssessRequest, resp: AssessResponse) -> None:
    try:
        store.get_db().queries.insert_one({"ts": dt.datetime.now(dt.timezone.utc), "input": req.model_dump(mode="json"),
                                           "verdict": resp.verdict.value, "material_id": resp.material.material_id if resp.material else None})
    except Exception:  # noqa: BLE001
        pass
