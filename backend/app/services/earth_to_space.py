"""Earth -> Space lens: 1g MOC/ULOI baseline next to microgravity evidence, red banner when 1g is not conservative."""
from __future__ import annotations

from app.core.config import get_settings
from app.models.api import EarthVsSpace, OneGBaseline
from app.services import correction, labels
from app.services.evidence import distance, has_outcome
from app.services.records import gravity_bucket, to_record


def _moc_rows(rows: list[dict]) -> list[dict]:
    return [e for e in rows if e["evidence_type"] == "flammability_limit_1g_MOC_ULOI" and e.get("outcome_variable") == "MOC"
            and e.get("outcome_value") is not None]


def _compatible(ug: dict, moc: dict) -> bool:
    tol = get_settings().tol_pressure_kpa
    a, b = ug.get("pressure_kpa"), moc.get("pressure_kpa")
    return a is None or b is None or abs(a - b) <= tol


def non_conservative_cases(rows: list[dict]) -> tuple[list[dict], int]:
    """µg records with a CONFIRMED human label 'sustained_burn' whose O2 is below the lowest pressure-compatible 1g MOC.
    Returns (cases, n_confirmed_sustained_ug)."""
    conf = labels.confirmed()
    mocs = _moc_rows(rows)
    burns = [e for e in rows if gravity_bucket(e["gravity_level"]) == "microgravity" and e.get("oxygen_pct") is not None
             and conf.get(e["experiment_id"], {}).get("label") == "sustained_burn"]
    cases = []
    for e in burns:
        comp = [m for m in mocs if _compatible(e, m)]
        if comp:
            low = min(comp, key=lambda m: m["outcome_value"])
            if e["oxygen_pct"] < low["outcome_value"]:
                cases.append({"ug": e, "moc": low, "pressure_known": e.get("pressure_kpa") is not None})
    return cases, len(burns)


def build(rows: list[dict], o2, p, flow) -> EarthVsSpace:
    st, msg = correction.status()
    g1 = [e for e in rows if e["evidence_type"] == "flammability_limit_1g_MOC_ULOI"]
    ug = sorted((e for e in rows if gravity_bucket(e["gravity_level"]) == "microgravity" and has_outcome(e)),
                key=lambda e: distance(e, o2, p, flow))[:3]
    if not g1:
        return EarthVsSpace(available=False, correction_model_status=st, correction_model_message=msg,
                            empty_state_message="No 1g MOC/ULOI baseline in the data for this material.")
    g1 = sorted(g1, key=lambda e: distance(e, o2, p, flow))
    mocs = [{"experiment_id": e["experiment_id"], "moc_pct": e["outcome_value"], "uloi_pct": e["uloi_pct"],
             "pressure_kpa": e["pressure_kpa"], "variant": e["material_variant"], "source_url": to_record(e).source_url} for e in g1]
    cases, n_conf = non_conservative_cases(rows)
    banner, srcs, flag = None, [], None
    if cases:
        c = cases[0]
        u, m = c["ug"], c["moc"]
        banner = (f"1g test is NOT conservative here: microgravity sustained burn at {u['oxygen_pct']}% O2 ({u['experiment_id']}) "
                  f"is below the 1g MOC of {m['outcome_value']}% O2 ({m['experiment_id']}; NASA-STD-6001 Test 1, upward)."
                  + ("" if c["pressure_known"] else " Pressure of the microgravity test is not stated; MOC rows at all pressures were considered."))
        srcs, flag = [to_record(u), to_record(m)], True
    elif n_conf:
        flag = False
    comp = None
    moc_rows = _moc_rows(rows)
    if p is not None:  # compare with MOC rows at a compatible pressure when the request states one
        moc_rows = [m for m in moc_rows if m.get("pressure_kpa") is None or abs(m["pressure_kpa"] - p) <= get_settings().tol_pressure_kpa] or moc_rows
    if moc_rows and ug:
        lo, hi = min(moc_rows, key=lambda m: m["outcome_value"]), max(moc_rows, key=lambda m: m["outcome_value"])
        if lo["outcome_value"] == hi["outcome_value"]:
            moc_txt = f"1g MOC for this material = {lo['outcome_value']}% O2 ({lo['source_ref']})"
        else:
            moc_txt = (f"1g MOC for this material = {lo['outcome_value']}% O2 ({lo['experiment_id']}) to {hi['outcome_value']}% O2 "
                       f"({hi['experiment_id']}) depending on variant/pressure ({lo['source_ref']})")
        u = ug[0]
        what = u.get("outcome_class") or conf_label(u) or "observations recorded (see notes)"
        comp = (f"{moc_txt}. Microgravity tests show {what} at "
                f"{u['oxygen_pct'] if u.get('oxygen_pct') is not None else 'unstated'}% O2 ({u['source_ref']}).")
    elif not ug:
        comp = "No microgravity evidence with an outcome for this material."
    if flag is None:
        comp = (comp + " " if comp else "") + "Whether the 1g test is conservative is undetermined until microgravity outcomes are human-labelled (see /api/validation)."
    return EarthVsSpace(
        available=True, baseline_1g=OneGBaseline(records=[to_record(e) for e in g1[:4]], moc_values=mocs),
        microgravity_evidence=[to_record(e) for e in ug], one_g_not_conservative=flag, banner=banner, banner_sources=srcs,
        comparison_text=comp, correction_model_status=st, correction_model_message=msg)


def conf_label(e: dict) -> str | None:
    l = labels.confirmed().get(e["experiment_id"])
    return l["label"].replace("_", " ") if l else None
