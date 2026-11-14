"""Unknown material flow (5.4). Always NO_DIRECT_EVIDENCE for microgravity: no coefficients are invented."""
from __future__ import annotations

from app.core.config import get_settings
from app.models.api import AssessRequest, AssessResponse, Estimate, NearestEvidence, Tolerances, Verdict, VERDICT_META
from app.services import correction, evidence as ev, materials, store
from app.services.assess import _findings, _investigations
from app.services.records import to_record

VK_LABEL = "LOI (downward, 1g) estimate — Van Krevelen, not tested"


def family_neighbours(family: str, limit: int = 3) -> list[dict]:
    qt = materials.tokens(family)
    out = []
    for m in store.materials().values():
        names = [m.get("chemical_family") or "", m["name_en"]] + list(m.get("aliases", []))
        if qt and any(n and all(any(t == x or (len(t) >= 3 and x.startswith(t)) for x in materials.tokens(n)) for t in qt) for n in names):
            out.append(m)
    return out[:limit]


def van_krevelen(char_yield: float) -> Estimate:
    s = get_settings()
    return Estimate(kind="van_krevelen_loi_1g", label=VK_LABEL, value=round(s.vk_intercept + s.vk_slope * char_yield, 1), unit="% O2",
                    inputs={"char_yield_pct": char_yield}, equation=f"LOI = {s.vk_intercept:g} + {s.vk_slope:g} × CR",
                    citation="Van Krevelen correlation (formula supplied in the team brief; empirical, 1g downward LOI)",
                    not_a_microgravity_limit=True)


def assess(req: AssessRequest, requested: dict, tol: Tolerances) -> AssessResponse:
    pr = req.unknown_material_props
    meta = VERDICT_META[Verdict.NO_DIRECT_EVIDENCE]
    warnings = ["Material not found in the NASA data set."]
    est, near, ctx, parts = None, [], [], []
    thickness = (pr.thickness_mm if pr and pr.thickness_mm is not None else req.thickness_mm)
    if pr and pr.char_yield_pct is not None:
        est = van_krevelen(pr.char_yield_pct)
        warnings.append("The Van Krevelen value is an empirical 1g LOI estimate. It is not a microgravity flammability limit and not NASA-STD-6001 MOC.")
        parts.append(f"{VK_LABEL}: {est.value}% O2 from char yield {pr.char_yield_pct}% ({est.equation}).")
    if pr and pr.known_loi_pct is not None:
        if pr.known_loi_standard:
            parts.append(f"Supplied LOI {pr.known_loi_pct}% O2 ({pr.known_loi_standard}) is user-provided, shown as given, and not compared with NASA MOC/ULOI.")
        else:
            warnings.append("Known LOI supplied without a test standard; it is not used (LOI and MOC are different tests).")
    if thickness is not None:
        warnings.append("Thickness is recorded but no evidence or model in the data uses it for an unknown material.")
    if pr and pr.polymer_family:
        neigh = family_neighbours(pr.polymer_family)
        if not neigh:
            warnings.append(f"No known material in the data matches polymer family '{pr.polymer_family}'.")
        for m in neigh:
            rows = ev.material_rows(m["material_id"])
            for n in ev.nearest(rows, requested.get("oxygen_pct"), requested.get("pressure_kpa"), req.airflow_cm_s, per_bucket=1):
                n.note = f"Nearest evidence for similar material {m['name_en']} (same family query '{pr.polymer_family}'). Different material: context only."
                near.append(n)
            ctx += [e for e in rows if e["experiment_id"] in {x.record.experiment_id for x in near}]
    # correction model: needs a 1g MOC of THIS material, which an unknown material cannot provide (LOI != MOC)
    st, msg = correction.status()
    reason = ("Material is not in the data. The microgravity verdict for unknown materials is 'no direct evidence' unless a correction model is "
              "configured and the input is inside its valid range; "
              + ("a correction model is configured but needs a 1g MOC for this material, which is not available." if st == "configured"
                 else "the correction model is not configured."))
    summary = "Unknown material: no direct evidence. " + " ".join(parts) if parts else "Unknown material: no data and no properties supplied."
    return AssessResponse(
        verdict=Verdict.NO_DIRECT_EVIDENCE, verdict_label=meta["label"], verdict_tier=meta["tier"], verdict_reason=reason,
        empty_state_message="Unknown material. Optionally provide polymer family, char yield (%), known LOI (with test standard) and thickness.",
        material=None, requested=requested, matched_tolerances=tol, evidence_groups=[], estimate=est, nearest_evidence=near,
        findings=_findings(ctx), investigations=_investigations(ctx), summary_text=summary, summary_source="template", warnings=warnings)
