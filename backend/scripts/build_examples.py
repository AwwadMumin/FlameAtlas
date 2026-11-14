"""Generate docs/examples/*.json from the REAL data files (no invented numbers).

Every value in an example is copied from data/*.json or computed from them with the inputs shown.
Run:  python backend/scripts/build_examples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.models import api as M  # noqa: E402
from app.services.records import EVIDENCE_TYPE_LABELS, to_record  # noqa: E402

S = Settings()
D = ROOT / "data"
OUT = ROOT / "docs" / "examples"
OUT.mkdir(parents=True, exist_ok=True)

MATS = json.loads((D / "materials.json").read_text())["materials"]
EXPS = json.loads((D / "experiments.json").read_text())
CARDS = {c["experiment_id"]: c for c in json.loads((D / "evidence_cards.json").read_text())}
K = json.loads((D / "flame_in_freefall_knowledge.json").read_text())
G5 = next(g for g in K["gap_fill"] if g["id"] == "G5")
PSI_TO_KPA = 6.894757
FIND = {f["id"]: f for f in K["guide_findings"]["findings"]}
INV = {i["accession"]: i for i in K["investigations"]}
MAT = {m["material_id"]: m for m in MATS}
BUCKET_OF = {"orbit": "microgravity", "microgravity": "microgravity", "earth": "1g", "1g": "1g", "moon": None, "mars": None}
TOL = M.Tolerances(o2_pct=S.tol_o2_pct, pressure_kpa=S.tol_pressure_kpa,
                   text=f"matched within ±{S.tol_o2_pct}% O2 and ±{S.tol_pressure_kpa:g} kPa (pressure only when known)")


def dump(name: str, obj) -> None:
    data = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", name)


def card(mid: str) -> M.MaterialCard:
    m = MAT[mid]
    return M.MaterialCard(
        material_id=mid, name_en=m["name_en"], name_ar=m.get("name_ar"), kind=m.get("kind"),
        chemical_family=m.get("chemical_family"), aliases=m.get("aliases", []),
        variants=[M.MaterialVariant(variant=v["variant"], n_records=v["n_records"], inferred="not named" in v["variant"])
                  for v in m.get("variants", [])],
        oxygen_pct_range=m.get("oxygen_pct_range"), pressure_kpa_range=m.get("pressure_kpa_range"),
        moc_pct_range_1g=m.get("moc_pct_range_1g"), uloi_pct_range_1g=m.get("uloi_pct_range_1g"),
        gravity_levels=m.get("gravity_levels", []), has_microgravity_evidence=m["has_microgravity_evidence"],
        has_1g_evidence=m["has_1g_evidence"], cross_gravity_group=m.get("cross_gravity_group"),
        warnings=m.get("warnings", []), dois=m.get("dois", []))


def has_outcome(e) -> bool:
    return e["outcome_type"] != "conditions_only"


def in_tol(e, o2, p) -> bool:
    if e["oxygen_pct"] is None or o2 is None or abs(e["oxygen_pct"] - o2) > S.tol_o2_pct:
        return False
    if p is not None and e["pressure_kpa"] is not None and abs(e["pressure_kpa"] - p) > S.tol_pressure_kpa:
        return False
    return True


def dist(e, o2, p, flow=None) -> float:
    d = 0.0
    if e["oxygen_pct"] is not None and o2 is not None:
        d += S.w_o2 * abs(e["oxygen_pct"] - o2) / 100
    if e["pressure_kpa"] is not None and p is not None:
        d += S.w_pressure * abs(e["pressure_kpa"] - p) / 101.325
    return d


def groups_for(rows, o2, p, n=3):
    by: dict[str, list] = {}
    for e in rows:
        by.setdefault(e["evidence_type"], []).append(e)
    out = []
    for et, rs in by.items():
        rs = sorted(rs, key=lambda e: dist(e, o2, p))
        out.append(M.EvidenceGroup(evidence_type=et, label=EVIDENCE_TYPE_LABELS[et], total_in_group=len(rs),
                                   records=[to_record(r, distance=round(dist(r, o2, p), 4)) for r in rs[:n]]))
    return out


def findings_for(rows) -> list[M.Finding]:
    ids = sorted({f for r in rows for f in (r["finding_ids"] or [])})[:4]
    return [M.Finding(id=i, claim=FIND[i]["claim"], page=FIND[i].get("page"), section=FIND[i].get("section"),
                      safety_area=FIND[i].get("safety_area")) for i in ids]


def inv_cards(rows) -> list[M.InvestigationCard]:
    out, seen = [], set()
    for r in rows:
        a = r.get("psi_id")
        if a and a in INV and a not in seen:
            seen.add(a); i = INV[a]
            out.append(M.InvestigationCard(accession=a, acronym=i.get("acronym"), title=i["title"], doi=i.get("doi"),
                                           objective=i.get("objective"), hypothesis=i.get("hypothesis"),
                                           landing_page=r.get("psi_url")))
    return out[:3]


def scatter(mid, o2, p, bucket_req) -> list[M.ScatterPoint]:
    pts = [M.ScatterPoint(o2=e["oxygen_pct"], pressure_kpa=e["pressure_kpa"], gravity="microgravity" if e["gravity_level"] == "microgravity" else "1g",
                          outcome=e["outcome_class"] or e["outcome_type"], experiment_id=e["experiment_id"])
           for e in EXPS if e["material_id"] == mid and e["flammability_relevant"] and e["oxygen_pct"] is not None]
    pts.append(M.ScatterPoint(o2=o2, pressure_kpa=p, gravity="requested", outcome=None, is_requested_point=True))
    return pts


def earth_vs_space(mid, o2, p) -> M.EarthVsSpace:
    g1 = [e for e in EXPS if e["material_id"] == mid and e["evidence_type"] == "flammability_limit_1g_MOC_ULOI"]
    ug = [e for e in EXPS if e["material_id"] == mid and e["gravity_level"] == "microgravity" and e["flammability_relevant"] and has_outcome(e)]
    if not g1:
        return M.EarthVsSpace(available=False, correction_model_message="Correction model not configured",
                              empty_state_message="No 1g MOC/ULOI baseline in the data for this material.")
    mocs = [{"experiment_id": e["experiment_id"], "moc_pct": e["outcome_value"], "uloi_pct": e["uloi_pct"], "pressure_kpa": e["pressure_kpa"],
             "variant": e["material_variant"], "source_url": to_record(e).source_url} for e in g1]
    ug_sorted = sorted(ug, key=lambda e: dist(e, o2, p))[:3]
    return M.EarthVsSpace(
        available=True,
        baseline_1g=M.OneGBaseline(records=[to_record(e) for e in g1[:4]], moc_values=mocs[:6]),
        microgravity_evidence=[to_record(e) for e in ug_sorted],
        one_g_not_conservative=None,
        banner=None,
        comparison_text=("Whether the 1g test is conservative here is undetermined until BASS notes are human-labelled "
                         "(see /api/validation)."),
        correction_model_status="not_configured", correction_model_message="Correction model not configured")


def assess(req: M.AssessRequest, mid: str | None) -> M.AssessResponse:
    bucket = BUCKET_OF[req.gravity]
    o2, p = req.oxygen_pct, req.pressure_kpa
    requested = req.model_dump(mode="json")
    if mid is None:
        raise ValueError
    rows = [e for e in EXPS if e["material_id"] == mid and e["flammability_relevant"]]
    pool = [e for e in rows if bucket and (e["gravity_level"] == "microgravity") == (bucket == "microgravity")]
    hits = [e for e in pool if has_outcome(e) and in_tol(e, o2, p)]
    m = card(mid)
    nearest = []
    for b in ("microgravity", "1g"):
        c = [e for e in rows if has_outcome(e) and ((e["gravity_level"] == "microgravity") == (b == "microgravity"))]
        if c:
            e = min(c, key=lambda e: dist(e, o2, p))
            nearest.append(M.NearestEvidence(
                gravity_bucket=b, record=to_record(e),
                delta_o2_pct=None if e["oxygen_pct"] is None or o2 is None else round(e["oxygen_pct"] - o2, 2),
                delta_pressure_kpa=None if e["pressure_kpa"] is None or p is None else round(e["pressure_kpa"] - p, 2),
                note="Nearest tested record at this gravity bucket; shown for context, not as a prediction."))
    if bucket and hits:
        v = M.Verdict.EVIDENCE
        reason = (f"{len(hits)} record(s) with an outcome for {m.name_en} at the same gravity bucket "
                  f"{TOL.text}.")
        shown = hits
    elif bucket is None:
        v = M.Verdict.NO_DIRECT_EVIDENCE
        reason = (f"Gravity '{req.gravity}' is outside the data domain (only microgravity and 1g were tested). "
                  "No interpolation between 0 g and 1 g is made. Nearest microgravity and 1g evidence shown.")
        shown = []
    else:
        v = M.Verdict.NO_DIRECT_EVIDENCE
        reason = (f"No record with an outcome for {m.name_en} at {bucket} {TOL.text}." +
                  ("" if m.has_microgravity_evidence or bucket != "microgravity" else
                   f" {m.name_en} has 1g evidence only; no microgravity tests exist in the data."))
        shown = []
    meta = M.VERDICT_META[v]
    near_ids = {n_.record.experiment_id for n_ in nearest}
    ev_rows = shown or [x for x in rows if x["experiment_id"] in near_ids]
    groups = groups_for(shown, o2, p) if shown else []
    template = (f"{m.name_en}: {reason}" +
                (" Records are listed with their sources; flags are shown next to the values they affect." if shown else
                 " Only a directional statement is possible; see the nearest evidence."))
    return M.AssessResponse(
        verdict=v, verdict_label=meta["label"], verdict_tier=meta["tier"], verdict_reason=reason,
        empty_state_message=None if shown else "No tested data for this material at these conditions. Nearest evidence is shown instead.",
        material=m, material_resolved_as=m.material_id, requested=requested, matched_tolerances=TOL,
        evidence_groups=groups, earth_vs_space=earth_vs_space(mid, o2, p), estimate=None, nearest_evidence=nearest,
        findings=findings_for(ev_rows), investigations=inv_cards(ev_rows), scatter_points=scatter(mid, o2, p, bucket),
        summary_text=template, summary_source="template", warnings=m.warnings,
        gaps=[M.GapCell(material_id=mid, o2_pct=o2, pressure_kpa=p, gravity=req.gravity,
                        suggested_test="Suggested test (not a result)", reason="No tested record at this point.")] if not shown else [])


def unknown(req: M.AssessRequest) -> M.AssessResponse:
    pr = req.unknown_material_props
    meta = M.VERDICT_META[M.Verdict.NO_DIRECT_EVIDENCE]
    est = None
    warns = ["Material not found in the NASA data set."]
    if pr and pr.char_yield_pct is not None:
        val = round(17.5 + 0.40 * pr.char_yield_pct, 1)
        est = M.Estimate(kind="van_krevelen_loi_1g", label="LOI (downward, 1g) estimate — Van Krevelen, not tested",
                         value=val, unit="% O2", inputs={"char_yield_pct": pr.char_yield_pct},
                         equation="LOI = 17.5 + 0.40 × CR", citation="Van Krevelen correlation (as specified by the team brief)",
                         not_a_microgravity_limit=True)
        warns.append("This is a 1g LOI estimate, not a microgravity flammability limit.")
    reason = ("Material is not in the data. Microgravity verdict is always 'no direct evidence' for unknown materials "
              "unless a correction model is configured and the input is inside its valid range (not configured).")
    return M.AssessResponse(
        verdict=M.Verdict.NO_DIRECT_EVIDENCE, verdict_label=meta["label"], verdict_tier=meta["tier"], verdict_reason=reason,
        empty_state_message="Unknown material. Optionally provide polymer family, char yield (%), known LOI (with test standard) and thickness.",
        material=None, material_resolved_as=None, requested=req.model_dump(mode="json"), matched_tolerances=TOL,
        evidence_groups=[], earth_vs_space=None, estimate=est, nearest_evidence=[], summary_text=(
            f"Unknown material. Van Krevelen 1g LOI estimate from char yield {pr.char_yield_pct}%: {est.value}% O2 (not tested; not a microgravity limit)."
            if est else "Unknown material: no data and no properties supplied."),
        summary_source="template", warnings=warns, gaps=[])


def main() -> None:
    # presets
    presets = [M.Preset(id=p["id"], name=p["name"], pressure_psia=p["pressure_psia"],
                        pressure_kpa=round(p["pressure_psia"] * PSI_TO_KPA, 2), o2_pct=p["o2_pct"],
                        gravity=p["gravity"], source=p["source"]) for p in G5["presets"]]
    lv = [M.GravityLevel(key=k, g=g, bucket={"orbit": "microgravity", "earth": "1g"}.get(k, "none"),
                         has_direct_data=k in ("orbit", "earth"),
                         note=None if k in ("orbit", "earth") else "No direct data: nearest µg and 1g evidence only. " +
                         ("Mars 0.38 g is general knowledge; cite a NASA source if shown." if k == "mars" else ""))
          for k, g in G5["gravity_levels_g"].items()]
    dump("presets", M.PresetsResponse(presets=presets, gravity_levels=lv))

    pm = card("pmma")
    dump("materials_search", M.MaterialSearchResponse(query="acrylic", matches=[M.MaterialMatch(material=pm, score=1.0, match_type="exact")]))
    dump("materials_search_empty", M.MaterialSearchResponse(query="unobtainium", matches=[],
         empty_state_message="No material matches 'unobtainium'. You can still run an assessment for an unknown material."))
    stats = {"records_total": sum(e["material_id"] == "pmma" for e in EXPS),
             "records_microgravity": sum(e["material_id"] == "pmma" and e["gravity_level"] == "microgravity" for e in EXPS),
             "records_1g": sum(e["material_id"] == "pmma" and e["gravity_level"] != "microgravity" for e in EXPS)}
    dump("material_detail", M.MaterialDetailResponse(material=pm, stats=stats, warnings=pm.warnings))
    rows = [e for e in EXPS if e["material_id"] == "pmma" and e["flammability_relevant"]]
    dump("material_evidence", M.MaterialEvidenceResponse(material_id="pmma", groups=groups_for(rows, None, None, 2)))

    A = M.AssessRequest
    dump("assess_evidence", assess(A(material_query="acrylic", preset_id="iss", oxygen_pct=21, pressure_kpa=101.3, gravity="orbit", question="will it self-extinguish?"), "pmma"))
    dump("assess_no_direct_1g_only", assess(A(material_query="PET", oxygen_pct=21, pressure_kpa=101.3, gravity="orbit"), "pet"))
    dump("assess_no_direct_moon", assess(A(material_query="acrylic", preset_id="exploration", oxygen_pct=34, pressure_kpa=round(8.2 * PSI_TO_KPA, 2), gravity="moon"), "pmma"))
    dump("assess_unknown_material", unknown(A(material_query="Zorbium-7", oxygen_pct=30, pressure_kpa=70.3, gravity="mars",
                                               unknown_material_props={"char_yield_pct": 30})))
    dump("assess_unknown_empty", unknown(A(material_query="Zorbium-7", gravity="mars")))
    dump("assess_model_estimate_SHAPE_ONLY", {
        "_note": "Shape only. No correction model is configured, so MODEL_ESTIMATE cannot be produced and no values are shown.",
        "verdict": "MODEL_ESTIMATE", "verdict_label": M.VERDICT_META[M.Verdict.MODEL_ESTIMATE]["label"], "verdict_tier": "amber",
        "estimate": {"kind": "model_estimate", "value": "<from configured model>", "error": "<LOO MAE>", "citation": "<correction_models.yaml>"}})

    dump("coverage", M.CoverageResponse(material_id="pmma", o2_axis=[], pressure_axis=["<60", "60-80", "80-95", ">95"], grids={},
         preset_overlays=[], empty_state_message="Populated in Phase 5 (shape defined here)."))
    dump("next_experiments", M.NextExperimentsResponse(preset="exploration", suggestions=[],
         empty_state_message="Populated in Phase 5 (shape defined here)."))
    bass = [e for e in EXPS if e["source_investigation"].startswith("BASS") and e["flame_behavior_notes"]][:2]
    dump("labels_queue", M.LabelQueueResponse(total=len(bass), items=[M.LabelQueueItem(
        experiment_id=e["experiment_id"], material_id=e["material_id"], oxygen_pct=e["oxygen_pct"], pressure_kpa=e["pressure_kpa"],
        flame_behavior_notes=e["flame_behavior_notes"], suggested_label=None, status="unlabelled") for e in bass]))
    dump("label_saved", M.LabelOut(experiment_id=bass[0]["experiment_id"], label="unclear", quote=bass[0]["flame_behavior_notes"][:40],
                                   labelled_by="team-member", status="confirmed"))
    dump("validation", M.ValidationResponse(labels_confirmed=0, labels_total_needed=len(bass), old_method_test={}, saffire_pairs=[],
         correction_model={"status": "not_configured", "message": "Correction model not configured"},
         caveats=["No confirmed human labels yet; counts appear after labelling."],
         empty_state_message="No confirmed labels yet. Label BASS notes via /api/admin/labels."))
    dump("health", M.HealthResponse(status="ok", mock=True, db={"connected": False, "note": "MOCK=1"}, vector_index={"name": "evidence_vector", "queryable": None},
         embedding_model={"name": S.embed_model, "dims": S.embed_dims}))
    ex = next(e for e in EXPS if e["experiment_id"] == "WSTF-013")
    dump("experiment_detail", M.ExperimentDetailResponse(record=to_record(ex), card_text=CARDS[ex["experiment_id"]]["text"],
         source_url=to_record(ex).source_url, extra=ex["extra"]))
    dump("about", M.AboutResponse(
        investigations=[M.InvestigationCard(accession=i["accession"], acronym=i.get("acronym"), title=i["title"], doi=i.get("doi"),
                                            objective=i.get("objective"), hypothesis=i.get("hypothesis")) for i in K["investigations"]],
        provenance={"built_from": json.loads((D / "materials.json").read_text())["metadata"]["built_from"],
                    "note": json.loads((D / "materials.json").read_text())["metadata"]["note"]},
        licenses=sorted({e["license"] for e in EXPS if e["license"]}), incidents=K["incidents"], earth_benefits=K["earth_benefits"]))
    dump("error_404", M.ErrorResponse(error=M.ErrorBody(code="not_found", message="Unknown material_id 'xyz'", details={"material_id": "xyz"})))
    dump("error_422", M.ErrorResponse(error=M.ErrorBody(code="validation_error", message="Invalid request body",
         details=[{"loc": ["body", "oxygen_pct"], "msg": "Input should be less than or equal to 100"}])))
    dump("demo_scenarios", M.DemoScenariosResponse(scenarios=[
        M.DemoScenario(id="pmma_iss", title="ISS cabin — PMMA", description="Acrylic at 21% O2 in orbit.", request=A(material_query="acrylic", preset_id="iss", oxygen_pct=21, pressure_kpa=101.3, gravity="orbit")),
        M.DemoScenario(id="sibal_iss", title="ISS cabin — SIBAL", description="Cotton-fiberglass blend in orbit.", request=A(material_query="SIBAL", preset_id="iss", oxygen_pct=21, pressure_kpa=101.3, gravity="orbit")),
        M.DemoScenario(id="pet_exploration", title="Lunar habitat 34% O2 — PET", description="PET at the exploration atmosphere.", request=A(material_query="PET", preset_id="exploration", oxygen_pct=34, pressure_kpa=round(8.2 * PSI_TO_KPA, 2), gravity="moon")),
        M.DemoScenario(id="unknown_mars", title="Unknown material — Mars", description="Material not in the data, char yield 30%.", request=A(material_query="Zorbium-7", gravity="mars", unknown_material_props={"char_yield_pct": 30}))]))


if __name__ == "__main__":
    main()
