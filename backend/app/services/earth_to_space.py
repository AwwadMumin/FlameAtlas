"""Earth -> Space lens. Phase 2 scope: 1g baseline next to µg evidence. Banner / correction model: Phase 3."""
from __future__ import annotations

from app.models.api import EarthVsSpace, OneGBaseline
from app.services.evidence import distance, has_outcome
from app.services.records import gravity_bucket, to_record


def build(rows: list[dict], o2, p, flow) -> EarthVsSpace:
    g1 = [e for e in rows if e["evidence_type"] == "flammability_limit_1g_MOC_ULOI"]
    ug = sorted((e for e in rows if gravity_bucket(e["gravity_level"]) == "microgravity" and has_outcome(e)),
                key=lambda e: distance(e, o2, p, flow))[:3]
    if not g1:
        return EarthVsSpace(available=False, correction_model_message="Correction model not configured",
                            empty_state_message="No 1g MOC/ULOI baseline in the data for this material.")
    g1 = sorted(g1, key=lambda e: distance(e, o2, p, flow))
    mocs = [{"experiment_id": e["experiment_id"], "moc_pct": e["outcome_value"], "uloi_pct": e["uloi_pct"],
             "pressure_kpa": e["pressure_kpa"], "variant": e["material_variant"], "source_url": to_record(e).source_url} for e in g1]
    return EarthVsSpace(
        available=True, baseline_1g=OneGBaseline(records=[to_record(e) for e in g1[:4]], moc_values=mocs),
        microgravity_evidence=[to_record(e) for e in ug], one_g_not_conservative=None,
        comparison_text=None if ug else "No microgravity evidence with an outcome for this material.",
        correction_model_status="not_configured", correction_model_message="Correction model not configured")
