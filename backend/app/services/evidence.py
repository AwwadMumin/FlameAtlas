"""Hybrid evidence retrieval: structured filter -> condition-distance rank -> optional vector search -> merge -> coverage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.models.api import EvidenceGroup, NearestEvidence, Tolerances
from app.services import store
from app.services.records import EVIDENCE_TYPE_LABELS, gravity_bucket, to_record

GRAVITY_BUCKET = {"orbit": "microgravity", "microgravity": "microgravity", "earth": "1g", "1g": "1g", "moon": None, "mars": None}


def tolerances() -> Tolerances:
    s = get_settings()
    return Tolerances(o2_pct=s.tol_o2_pct, pressure_kpa=s.tol_pressure_kpa,
                      text=f"matched within ±{s.tol_o2_pct:g}% O2 and ±{s.tol_pressure_kpa:g} kPa (pressure compared only when the record states it)")


def has_outcome(e: dict) -> bool:
    return e.get("outcome_type") != "conditions_only"


def o2_coord(e: dict) -> float | None:
    """O2 coordinate of a record. 1g MOC thresholds carry the O2 in outcome_value (their oxygen_pct is null)."""
    if e.get("oxygen_pct") is not None:
        return e["oxygen_pct"]
    if e.get("outcome_variable") == "MOC" and e.get("outcome_value") is not None:
        return e["outcome_value"]
    return None


def distance(e: dict, o2: float | None, p: float | None, flow: float | None) -> float:
    """Weighted normalised distance. A missing value on either side gets the full penalty (no bonus), never dropped."""
    s, sp = get_settings(), store.field_spans()
    d = 0.0
    for w, a, b, span in ((s.w_o2, o2_coord(e), o2, sp["oxygen_pct"]), (s.w_pressure, e.get("pressure_kpa"), p, sp["pressure_kpa"]),
                          (s.w_airflow, e.get("airflow_cm_s"), flow, sp["airflow_cm_s"])):
        d += w * (min(abs(a - b) / span, 1.0) if a is not None and b is not None else 1.0)
    return round(d, 4)


def in_tolerance(e: dict, o2: float | None, p: float | None) -> bool:
    s = get_settings()
    c = o2_coord(e)
    if o2 is None or c is None or abs(c - o2) > s.tol_o2_pct:
        return False
    if p is not None and e.get("pressure_kpa") is not None and abs(e["pressure_kpa"] - p) > s.tol_pressure_kpa:
        return False
    return True


def material_rows(material_id: str, variant: str | None = None) -> list[dict]:
    q: dict[str, Any] = {"material_id": material_id, "flammability_relevant": True}
    if variant:
        q["material_variant"] = variant
    return list(store.get_db().experiments.find(q, {"_id": 0}))


def smoke_rows(material_id: str, limit: int = 6) -> list[dict]:
    return list(store.get_db().experiments.find({"material_id": material_id, "flammability_relevant": False}, {"_id": 0}).limit(limit))


def vector_hits(material_id: str, question: str, limit: int = 8) -> dict[str, float]:
    """experiment_id -> similarity, only >= threshold. Pre-filtered on material and flammability_relevant."""
    s = get_settings()
    from app.services.embeddings import embed
    res = store.get_db().evidence_cards.aggregate([{"$vectorSearch": {
        "index": "evidence_vector", "path": "embedding", "queryVector": embed([question])[0], "numCandidates": 100, "limit": limit,
        "filter": {"material_id": material_id, "flammability_relevant": True}}},
        {"$project": {"experiment_id": 1, "score": {"$meta": "vectorSearchScore"}}}])
    return {r["experiment_id"]: float(r["score"]) for r in res if r["score"] >= s.similarity_threshold}


def group(rows: list[dict], o2, p, flow, sims: dict[str, float] | None = None) -> list[EvidenceGroup]:
    n = get_settings().top_n_per_group
    by: dict[str, list[dict]] = {}
    for e in rows:
        by.setdefault(e["evidence_type"], []).append(e)
    out = []
    for et, rs in by.items():
        rs = sorted(rs, key=lambda e: distance(e, o2, p, flow))
        out.append(EvidenceGroup(
            evidence_type=et, label=EVIDENCE_TYPE_LABELS.get(et, et), total_in_group=len(rs),
            records=[to_record(r, distance=distance(r, o2, p, flow),
                               similarity=round(sims[r["experiment_id"]], 3) if sims and r["experiment_id"] in sims else None) for r in rs[:n]]))
    return sorted(out, key=lambda g: -g.total_in_group)


def nearest(rows: list[dict], o2, p, flow, per_bucket: int = 2) -> list[NearestEvidence]:
    out = []
    for b in ("microgravity", "1g"):
        c = sorted((e for e in rows if has_outcome(e) and gravity_bucket(e["gravity_level"]) == b), key=lambda e: distance(e, o2, p, flow))
        for e in c[:per_bucket]:
            co = o2_coord(e)
            out.append(NearestEvidence(
                gravity_bucket=b, record=to_record(e, distance=distance(e, o2, p, flow)),
                delta_o2_pct=None if co is None or o2 is None else round(co - o2, 2),
                delta_pressure_kpa=None if e.get("pressure_kpa") is None or p is None else round(e["pressure_kpa"] - p, 2),
                note="Nearest tested record at this gravity bucket; context only, not a prediction."
                     + (" (1g MOC threshold: O2 coordinate = the MOC value)" if e.get("outcome_variable") == "MOC" else "")))
    return out


@dataclass
class Retrieval:
    bucket: str | None
    rows: list[dict]
    matched: list[dict] = field(default_factory=list)   # EVIDENCE-qualifying records (same bucket, outcome, within tolerance)
    shown: list[dict] = field(default_factory=list)     # what the groups display
    sims: dict[str, float] = field(default_factory=dict)


def retrieve(material_id: str, variant: str | None, gravity: str, o2, p, flow, question: str | None) -> Retrieval:
    bucket = GRAVITY_BUCKET[gravity]
    rows = material_rows(material_id, variant)
    r = Retrieval(bucket=bucket, rows=rows)
    if bucket is None:
        return r
    same = [e for e in rows if gravity_bucket(e["gravity_level"]) == bucket]
    r.matched = [e for e in same if has_outcome(e) and in_tolerance(e, o2, p)]
    shown = {e["experiment_id"]: e for e in same if in_tolerance(e, o2, p)}  # outcome rows and "tested at" rows near the point
    if question and question.strip():
        try:
            r.sims = vector_hits(material_id, question.strip())
            byid = {e["experiment_id"]: e for e in same}
            for eid in r.sims:
                if eid in byid:
                    shown.setdefault(eid, byid[eid])  # de-dup by experiment_id
        except Exception:  # noqa: BLE001  (vector search unavailable -> structured evidence only)
            r.sims = {}
    r.shown = list(shown.values())
    return r
