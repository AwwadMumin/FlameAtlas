"""Unknown material flow. Phase 2 stub (empty state only); Van Krevelen + family neighbours land in Phase 3."""
from __future__ import annotations

from app.models.api import AssessRequest, AssessResponse, Tolerances, Verdict, VERDICT_META


def assess(req: AssessRequest, requested: dict, tol: Tolerances) -> AssessResponse:
    meta = VERDICT_META[Verdict.NO_DIRECT_EVIDENCE]
    return AssessResponse(
        verdict=Verdict.NO_DIRECT_EVIDENCE, verdict_label=meta["label"], verdict_tier=meta["tier"],
        verdict_reason="Material is not in the data. The microgravity verdict for unknown materials is always 'no direct evidence' unless a correction model is configured and the input is inside its valid range.",
        empty_state_message="Unknown material. Optionally provide polymer family, char yield (%), known LOI (with test standard) and thickness.",
        material=None, requested=requested, matched_tolerances=tol, evidence_groups=[], summary_text="Unknown material: no data for this material.",
        summary_source="template", warnings=["Material not found in the NASA data set."])
