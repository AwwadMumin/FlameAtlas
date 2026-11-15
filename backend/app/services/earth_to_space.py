"""Earth -> Space lens: 1g MOC/ULOI baseline next to microgravity evidence, red banner when 1g is not conservative."""
from __future__ import annotations

import re

from app.core.config import get_settings
from app.models.api import EarthVsSpace, OneGBaseline
from app.services import correction, labels
from app.services.evidence import distance, has_outcome
from app.services.records import gravity_bucket, to_record


# Standard NASA-STD-6001 Test 1 procedure, as stated by Hirsch et al. 2011 (NTRS 20110008636): "Tests with chemical igniters were standard", the Test 1
# burn-length criterion (6 in.) is used except in the pass/fail-criteria study (Table 6: 1-in/2-in rows), and "standard mounting" vs "exposed edge" (Table 5).
# A row is 'standard' only if its configuration SAYS so; rows that say nothing are 'not_stated', never assumed standard.
_NON_STD = re.compile(r"hot[- ]?wire|exposed edge|at least [12]-in|\b[12]-in\.? burn", re.I)
_STD = re.compile(r"chemical igniter|standard mounting", re.I)
PROCEDURE_NOTE = ("'standard' = configuration states chemical igniter or standard mounting with the 6-in burn criterion (Hirsch et al. 2011); "
                  "hot-wire, exposed-edge and 1-in/2-in burn-length rows are non-standard variations; rows that state nothing are 'not_stated'.")


def procedure(e: dict) -> str:
    cfg = e.get("configuration") or ""
    if _NON_STD.search(cfg):
        return "non_standard"
    return "standard" if _STD.search(cfg) else "not_stated"


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
        std = [m for m in mocs if procedure(m) == "standard" and _compatible(e, m)]
        comp = std or [m for m in mocs if _compatible(e, m)]
        if comp:
            low = min(comp, key=lambda m: m["outcome_value"])
            if e["oxygen_pct"] < low["outcome_value"]:
                cases.append({"ug": e, "moc": low, "pressure_known": e.get("pressure_kpa") is not None, "comparator": "standard" if std else "all_configurations"})
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
             "pressure_kpa": e["pressure_kpa"], "variant": e["material_variant"], "configuration": e.get("configuration"), "procedure": procedure(e),
             "source_url": to_record(e).source_url} for e in g1]
    cases, n_conf = non_conservative_cases(rows)
    banner, srcs, flag = None, [], None
    if cases:
        c = cases[0]
        u, m = c["ug"], c["moc"]
        which = ("standard-procedure" if c["comparator"] == "standard" else "lowest (no row states the standard procedure)")
        banner = (f"1g test is NOT conservative here: microgravity sustained burn at {u['oxygen_pct']}% O2 ({u['experiment_id']}) "
                  f"is below the {which} 1g MOC of {m['outcome_value']}% O2 ({m['experiment_id']}; NASA-STD-6001 Test 1, upward)."
                  + ("" if c["pressure_known"] else " Pressure of the microgravity test is not stated; MOC rows at all pressures were considered."))
        srcs, flag = [to_record(u), to_record(m)], True
    elif n_conf:
        flag = False
    comp = None
    moc_rows = _moc_rows(rows)
    if p is not None:  # compare with MOC rows at a compatible pressure when the request states one
        moc_rows = [m for m in moc_rows if m.get("pressure_kpa") is None or abs(m["pressure_kpa"] - p) <= get_settings().tol_pressure_kpa] or moc_rows
    std_rows = [m for m in moc_rows if procedure(m) == "standard"]
    if moc_rows and ug:
        def rng(rs):
            lo, hi = min(rs, key=lambda m: m["outcome_value"]), max(rs, key=lambda m: m["outcome_value"])
            return lo, hi, (f"{lo['outcome_value']}% O2 ({lo['experiment_id']})" if lo["outcome_value"] == hi["outcome_value"]
                            else f"{lo['outcome_value']}% O2 ({lo['experiment_id']}) to {hi['outcome_value']}% O2 ({hi['experiment_id']})")
        lo_all, hi_all, txt_all = rng(moc_rows)
        if std_rows:
            _, _, txt_std = rng(std_rows)
            moc_txt = (f"1g MOC with the standard NASA-STD-6001 Test 1 procedure = {txt_std} ({std_rows[0]['source_ref']}). "
                       f"Across all test configurations in that paper (hot-wire, cast/extruded, geometry, burn-length criterion) it is {txt_all}")
        else:
            moc_txt = (f"No 1g row states the standard Test 1 procedure for this material; across the configurations in the data the 1g MOC is {txt_all} "
                       f"({lo_all['source_ref']})")
        u = ug[0]
        what = (u.get("outcome_class") or conf_label(u)
                or (f"{u['outcome_variable']} = {u['outcome_value']} {u.get('outcome_unit') or ''}".strip() if u.get("outcome_value") is not None else None)
                or "observations recorded (see notes)")
        comp = (f"{moc_txt}. Microgravity tests show {what} at "
                f"{u['oxygen_pct'] if u.get('oxygen_pct') is not None else 'unstated'}% O2 ({u['source_ref']}).")
    elif not ug:
        comp = "No microgravity evidence with an outcome for this material."
    if flag is None:
        comp = (comp + " " if comp else "") + "Whether the 1g test is conservative is undetermined until microgravity outcomes are human-labelled (see /api/validation)."
    return EarthVsSpace(
        available=True, baseline_1g=OneGBaseline(records=[to_record(e) for e in g1[:4]], moc_values=mocs, procedure_note=PROCEDURE_NOTE,
                                 standard_moc_values=[m["outcome_value"] for m in _moc_rows(g1) if procedure(m) == "standard"]),
        microgravity_evidence=[to_record(e) for e in ug], one_g_not_conservative=flag, banner=banner, banner_sources=srcs,
        comparison_text=comp, correction_model_status=st, correction_model_message=msg)


def conf_label(e: dict) -> str | None:
    l = labels.confirmed().get(e["experiment_id"])
    return l["label"].replace("_", " ") if l else None
