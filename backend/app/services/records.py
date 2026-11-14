"""Turn raw experiment rows into UI-ready EvidenceRecord objects. Uses only fields present in the row."""
from __future__ import annotations

from typing import Any

from app.models.api import EvidenceRecord

EVIDENCE_TYPE_LABELS = {
    "solid_burn_test": "Solid burn tests",
    "large_scale_burn_test": "Large-scale burn tests (Saffire)",
    "flammability_limit_1g_MOC_ULOI": "1g flammability limits (MOC / ULOI, NASA-STD-6001 Test 1, upward)",
    "droplet_combustion": "Droplet combustion",
    "gas_flame_test": "Gas flame tests",
    "smoke_particle_size": "Smoke / detection (not burn evidence)",
    "test_matrix_summary": "Test matrix summaries",
}


def gravity_bucket(gravity_level: str) -> str:
    return "microgravity" if gravity_level == "microgravity" else "1g"


def source_url(rec: dict[str, Any]) -> str | None:
    if rec.get("doi"):
        return f"https://doi.org/{rec['doi']}"
    sf = rec.get("source_file") or ""
    return sf if sf.startswith("http") else None  # WSTF records: NTRS URL


def display_kind(rec: dict[str, Any]) -> str:
    if rec.get("flammability_relevant") is False:
        return "smoke"
    t = rec.get("outcome_type")
    return {"conditions_only": "tested_at", "observation_text": "observation", "threshold": "threshold",
            "count": "count"}.get(t, "result")


def _fmt(v: Any) -> str:
    return "not available" if v is None else str(v)


def display_text(rec: dict[str, Any]) -> str:
    kind = display_kind(rec)
    cond = []
    if rec.get("oxygen_pct") is not None:
        cond.append(f"O2 {rec['oxygen_pct']}%" + (f" ({rec['oxygen_basis']})" if rec.get("oxygen_basis") else ""))
    if rec.get("pressure_kpa") is not None:
        cond.append(f"{rec['pressure_kpa']} kPa")
    if rec.get("airflow_cm_s") is not None:
        cond.append(f"flow {rec['airflow_cm_s']} cm/s")
    c = ", ".join(cond) or "conditions not recorded"
    name = rec.get("fuel_material") or "material not named"
    if kind == "tested_at":
        return f"Tested at: {name}; {c}. Outcome not recorded in source."
    if kind == "smoke":
        return f"Smoke/detection test (heated, not burned): {name}; {c}."
    if kind == "threshold":
        s = f"{rec.get('outcome_variable')} = {_fmt(rec.get('outcome_value'))} {rec.get('outcome_unit') or ''}".strip()
        u = f"; ULOI = {rec['uloi_pct']} % O2" if rec.get("uloi_pct") is not None else ""
        return f"{s}{u} (1g, upward, NASA-STD-6001 Test 1) — {name}; {c}."
    if kind == "observation":
        return f"Observation: {name}; {c}. See verbatim notes."
    val = rec.get("outcome_value")
    s = f"{rec.get('outcome_variable') or 'outcome'} = {_fmt(val)}"
    if rec.get("outcome_unit") and val is not None:
        s += f" [{rec['outcome_unit']}]"
    if rec.get("outcome_class"):
        s += f"; class: {rec['outcome_class']}"
    if val is None and rec.get("flame_behavior_notes"):
        s += f" (verbatim note: \"{rec['flame_behavior_notes']}\")"
    return f"{s} — {name}; {c}."


def to_record(rec: dict[str, Any], **extra: Any) -> EvidenceRecord:
    d = {k: rec.get(k) for k in EvidenceRecord.model_fields if k in rec}
    d["quality_flags"] = rec.get("quality_flags") or []
    d["finding_ids"] = rec.get("finding_ids") or []
    d["gravity_bucket"] = gravity_bucket(rec["gravity_level"])
    d["source_url"] = source_url(rec)
    d["display_kind"] = display_kind(rec)
    d["display_text"] = display_text(rec)
    if rec.get("evidence_type") == "flammability_limit_1g_MOC_ULOI":
        d["test_family"] = "NASA_STD_6001_T1_upward"
    d.update(extra)
    return EvidenceRecord(**d)
