"""POST /api/assess orchestration (Phase 2: template summary only)."""
from __future__ import annotations

import datetime as dt
from collections import Counter

from app.core.config import get_settings
from app.models.api import (AssessRequest, AssessResponse, Finding, GapCell, InvestigationCard, ScatterPoint, Verdict, VERDICT_META)
from app.services import earth_to_space, evidence as ev, materials, store
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
    pts.append(ScatterPoint(o2=o2, pressure_kpa=p, gravity="requested", outcome=None, is_requested_point=True))
    return pts


def run(req: AssessRequest) -> AssessResponse:
    o2, p = req.oxygen_pct, req.pressure_kpa
    if req.preset_id:
        pr = _presets().get(req.preset_id)
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
        evidence_groups=groups, smoke_detection=smoke, earth_vs_space=earth_to_space.build(r.rows, o2, p, flow), estimate=None,
        nearest_evidence=near, findings=_findings(ctx), investigations=_investigations(ctx), scatter_points=_scatter(r.rows, o2, p),
        summary_text=summary, summary_source="template", warnings=warnings, gaps=gaps)
    log(req, resp)
    return resp


def template_summary(name: str, v: Verdict, reason: str, groups, near) -> str:
    if v == Verdict.EVIDENCE:
        top = groups[0].records[0] if groups and groups[0].records else None
        s = f"{name}: EVIDENCE. {reason}"
        if top:
            s += f" Closest record {top.experiment_id}: {top.display_text} Source: {top.source_ref}."
        return s
    s = f"{name}: NO DIRECT EVIDENCE. {reason}"
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
