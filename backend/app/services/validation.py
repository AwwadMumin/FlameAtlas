"""Validation & error report (5.5): how wrong is "trust the 1g test"? Built only from human-CONFIRMED labels."""
from __future__ import annotations

import json
import statistics
from typing import Any

from app.core.config import get_settings
from app.models.api import ValidationResponse
from app.services import correction, labels, store
from app.services.earth_to_space import _compatible, _moc_rows, procedure
from app.services.records import gravity_bucket, source_url, to_record

BURN = {"sustained_burn"}
NON_BURN = {"no_ignition", "brief_then_self_extinguished"}   # extinguished_by_flow_or_N2 / hardware_issue / unclear are NOT counted either way
DEFINITION = ("A microgravity (µg) record under-predicts hazard when a confirmed 'sustained_burn' happened at an O2 below the 1g MOC (NASA-STD-6001 Test 1, upward). "
              "STRICT = below the LOWEST pressure-compatible MOC row (below every 1g result). VARIANT-DEPENDENT = below the highest but not the lowest row: the 1g result "
              "depends on the TEST CONFIGURATION (ignition mode, burn-length criterion, geometry, cast vs extruded; Hirsch et al. 2011), so this is reported separately and never blended into the strict count. The opposite error is a µg non-burn "
              "('no_ignition' or 'brief_then_self_extinguished') above the 1g MOC (strict = above the HIGHEST row). Pressure-compatible = within the configured tolerance, "
              "or either pressure not stated. A third count compares only with rows whose configuration states the STANDARD Test 1 procedure (chemical igniter / standard mounting, "
              "6-in criterion): that is what a standard 1g test would have concluded. MOC (upward) is never converted to or compared as LOI (downward).")


def _by_material() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in store.get_db().experiments.find({"flammability_relevant": True}, {"_id": 0}):
        if e["material_id"]:
            out.setdefault(e["material_id"], []).append(e)
    return out


def old_method_test(conf: dict[str, dict], by_mat: dict[str, list[dict]]) -> dict[str, Any]:
    """Two strengths, never blended:
    strict   = O2 is beyond EVERY pressure-compatible MOC row (unambiguous disagreement with the 1g test);
    variant_dependent = O2 is beyond at least one, but not every, MOC row (depends on which variant/pressure the 1g test used)."""
    cases, per = [], []
    for mid, rows in sorted(by_mat.items()):
        mocs = _moc_rows(rows)
        lab = [e for e in rows if gravity_bucket(e["gravity_level"]) == "microgravity" and e["experiment_id"] in conf and e.get("oxygen_pct") is not None]
        if not mocs or not lab:
            continue
        c = {"n_evaluated": 0, "burn_below_moc_strict": 0, "burn_below_moc_variant_dependent": 0, "nonburn_above_moc_strict": 0,
             "nonburn_above_moc_variant_dependent": 0, "burn_below_standard_moc": 0, "nonburn_above_standard_moc": 0, "other": 0}
        for e in lab:
            comp = [m for m in mocs if _compatible(e, m)]
            if not comp:
                continue
            c["n_evaluated"] += 1
            lo, hi = min(comp, key=lambda m: m["outcome_value"]), max(comp, key=lambda m: m["outcome_value"])
            l, o2 = conf[e["experiment_id"]], e["oxygen_pct"]
            std = [m for m in comp if procedure(m) == "standard"]
            if std and l["label"] in BURN and o2 < min(m["outcome_value"] for m in std):
                c["burn_below_standard_moc"] += 1
            if std and l["label"] in NON_BURN and o2 > max(m["outcome_value"] for m in std):
                c["nonburn_above_standard_moc"] += 1
            hit = None
            if l["label"] in BURN and o2 < hi["outcome_value"]:
                hit = ("burn_below_moc", "strict" if o2 < lo["outcome_value"] else "variant_dependent", lo if o2 < lo["outcome_value"] else hi)
            elif l["label"] in NON_BURN and o2 > lo["outcome_value"]:
                hit = ("nonburn_above_moc", "strict" if o2 > hi["outcome_value"] else "variant_dependent", hi if o2 > hi["outcome_value"] else lo)
            if not hit:
                c["other"] += 1
                continue
            kind, strength, m = hit
            c[f"{kind}_{strength}"] += 1
            cases.append({"material_id": mid, "case": kind, "strength": strength, "experiment_id": e["experiment_id"], "label": l["label"], "oxygen_pct": o2,
                          "pressure_kpa": e.get("pressure_kpa"), "quote": l["quote"], "labelled_by": l["labelled_by"], "moc_experiment_id": m["experiment_id"],
                          "moc_pct": m["outcome_value"], "moc_pressure_kpa": m.get("pressure_kpa"), "moc_range_pct": [lo["outcome_value"], hi["outcome_value"]],
                          "moc_variant": m.get("material_variant"), "ug_source_ref": e["source_ref"], "ug_source_url": source_url(e),
                          "moc_source_ref": m["source_ref"], "moc_source_url": source_url(m)})
        per.append({"material_id": mid, **c})
    tot = lambda k: sum(p[k] for p in per)  # noqa: E731
    return {"definition": DEFINITION, "materials_evaluated": [p["material_id"] for p in per], "per_material": per, "n_evaluated": tot("n_evaluated"),
            "n_burn_below_moc": tot("burn_below_moc_strict"), "n_burn_below_moc_variant_dependent": tot("burn_below_moc_variant_dependent"),
            "n_nonburn_above_moc": tot("nonburn_above_moc_strict"), "n_nonburn_above_moc_variant_dependent": tot("nonburn_above_moc_variant_dependent"),
            "n_burn_below_standard_moc": tot("burn_below_standard_moc"), "n_nonburn_above_standard_moc": tot("nonburn_above_standard_moc"),
            "cases": cases}


def saffire_pairs() -> list[dict]:
    pairs: dict[str, dict[str, Any]] = {}
    for e in store.get_db().experiments.find({"pair_id": {"$ne": None}}, {"_id": 0}):
        pairs.setdefault(e["pair_id"], {})["microgravity" if e["gravity_level"] == "microgravity" else "one_g"] = e
    out = []
    for pid, d in sorted(pairs.items()):
        if "microgravity" in d and "one_g" in d:
            ug, g1 = d["microgravity"], d["one_g"]
            out.append({"pair_id": pid, "material_id": ug["material_id"], "microgravity": to_record(ug).model_dump(), "one_g": to_record(g1).model_dump(),
                        "note": "Same sample tested in microgravity and 1g (Saffire-II comparison columns). Conditions of the 1g test are not always stated; values are shown as given."})
    return out


def correction_check(conf: dict[str, dict], by_mat: dict[str, list[dict]]) -> dict[str, Any]:
    """Prediction error of the configured model on usable pairs. Usable pair = a material with a 1g MOC and >=1 confirmed µg 'sustained_burn'
    with known O2 and airflow; observed value = LOWEST O2 of those burns (an upper bound of the true limit). The paper's coefficients are
    fixed (nothing is refit), so leave-one-out = the residual of each held-out pair."""
    st, msg = correction.status()
    if st != "configured":
        return {"status": "not_configured", "message": msg, "n_pairs": 0, "mae_pct_o2": None, "max_error_pct_o2": None, "pairs": []}
    pairs = []
    for mid, rows in by_mat.items():
        mocs = _moc_rows(rows)
        burns = [e for e in rows if gravity_bucket(e["gravity_level"]) == "microgravity" and conf.get(e["experiment_id"], {}).get("label") == "sustained_burn"
                 and e.get("oxygen_pct") is not None and e.get("airflow_cm_s") is not None]
        if not mocs or not burns:
            continue
        obs = min(burns, key=lambda e: e["oxygen_pct"])
        comp = [m for m in mocs if _compatible(obs, m)] or mocs
        moc = min(comp, key=lambda m: abs(m["outcome_value"] - obs["oxygen_pct"]))
        r = correction.estimate({"moc_1g_pct": moc["outcome_value"], "airflow_cm_s": obs["airflow_cm_s"], "pressure_kpa": obs.get("pressure_kpa"),
                                 "thickness_mm": None, "oxygen_pct": obs["oxygen_pct"]}, require_error=False)
        if r.applicable:
            pairs.append({"material_id": mid, "observed_pct_o2": obs["oxygen_pct"], "predicted_pct_o2": r.value, "error_pct_o2": round(r.value - obs["oxygen_pct"], 2),
                          "observed_experiment_id": obs["experiment_id"], "moc_experiment_id": moc["experiment_id"]})
    errs = [abs(p["error_pct_o2"]) for p in pairs]
    out = {"status": "configured", "n_pairs": len(pairs), "pairs": pairs, "mae_pct_o2": round(statistics.mean(errs), 2) if errs else None,
           "max_error_pct_o2": round(max(errs), 2) if errs else None, "method": "held-out residual with fixed paper coefficients (nothing refit)"}
    if 0 < len(pairs) < 5:
        out["note"] = f"n = {len(pairs)} pairs is small; treat MAE and max error as indicative only."
    return out


def compute() -> ValidationResponse:
    conf = labels.confirmed()
    by_mat = _by_material()
    needed = len(labels.labelable())
    old = old_method_test(conf, by_mat)
    caveats = [
        "Outcome labels are human judgements of verbatim crew notes (BASS, PSI-26 as-run workbook); suggestions from keyword rules are excluded.",
        "Only materials with both a 1g MOC (WSTF) and confirmed µg labels are evaluated. In the current data these can only be PMMA and PEI (BASS crew notes exist for PMMA, wax, SIBAL, Nomex, PEI; wax, SIBAL and Nomex have no 1g MOC), so the evaluated set is small and not a random sample.",
        "1g MOC (NASA-STD-6001 Test 1, upward) and LOI (downward, ASTM D2863) are different quantities and are never compared.",
        "µg records without a stated pressure are compared with MOC rows at all pressures.",
        f"{len(conf)} of {needed} labelable records are confirmed.",
    ]
    return ValidationResponse(
        labels_confirmed=len(conf), labels_total_needed=needed, old_method_test=old, saffire_pairs=saffire_pairs(),
        correction_model=correction_check(conf, by_mat), caveats=caveats,
        empty_state_message=None if conf else "No confirmed labels yet. Label BASS crew notes via /api/admin/labels (or scripts/import_labels.py) to produce the old-method error counts. Saffire pairs are shown regardless.")


def markdown(v: ValidationResponse) -> str:
    o, c = v.old_method_test, v.correction_model
    L = ["# Mission Lens — validation report", "",
         f"Confirmed human labels: **{v.labels_confirmed}** of {v.labels_total_needed} labelable BASS records.", ""]
    if v.empty_state_message:
        L += [f"> {v.empty_state_message}", ""]
    L += ["## 1. Test of the old method (\"trust the 1g test\")", "", o["definition"], ""]
    if o["n_evaluated"] or o["per_material"]:
        L += [f"- µg records evaluated: **{o['n_evaluated']}** across {len(o['per_material'])} material(s): {', '.join(o['materials_evaluated'])}",
              f"- Sustained burn below EVERY 1g MOC row (strict): **{o['n_burn_below_moc']}**; below some rows only (variant-dependent): **{o['n_burn_below_moc_variant_dependent']}**",
              f"- Sustained burn below the STANDARD-procedure 1g MOC (what a standard Test 1 would conclude): **{o['n_burn_below_standard_moc']}**; non-burn above it: **{o['n_nonburn_above_standard_moc']}**",
              f"- Non-burn above EVERY 1g MOC row (strict): **{o['n_nonburn_above_moc']}**; above some rows only (variant-dependent): **{o['n_nonburn_above_moc_variant_dependent']}**", "",
              "| material | evaluated | burn < MOC strict | burn < MOC variant-dep. | non-burn > MOC strict | non-burn > MOC variant-dep. | other |", "|---|---|---|---|---|---|---|"]
        L += [f"| {p['material_id']} | {p['n_evaluated']} | {p['burn_below_moc_strict']} | {p['burn_below_moc_variant_dependent']} | {p['nonburn_above_moc_strict']} | "
              f"{p['nonburn_above_moc_variant_dependent']} | {p['other']} |" for p in o["per_material"]]
        L += ["", "### Cases", ""]
        for k in o["cases"]:
            press = "" if k["pressure_kpa"] is None else ", " + str(k["pressure_kpa"]) + " kPa"
            L.append(f"- **{k['experiment_id']}** ({k['material_id']}, {k['label']}, {k['strength'].replace('_', '-')}) at {k['oxygen_pct']}% O2{press} vs 1g MOC "
                     f"{k['moc_pct']}% ({k['moc_experiment_id']}; all compatible MOC rows {k['moc_range_pct'][0]}-{k['moc_range_pct'][1]}%). Quote: \"{k['quote']}\" — labelled by {k['labelled_by']}. "
                     f"Sources: [{k['ug_source_ref']}]({k['ug_source_url']}); [{k['moc_source_ref']}]({k['moc_source_url']})")
    else:
        L.append("_No material has both a 1g MOC and a confirmed µg label yet._")
    L += ["", "## 2. Saffire-II pairs (same sample, µg vs 1g)", "", "| pair | material | microgravity | 1g |", "|---|---|---|---|"]
    for p in v.saffire_pairs:
        L.append(f"| {p['pair_id']} | {p['material_id']} | {p['microgravity']['display_text']} | {p['one_g']['display_text']} |")
    L += ["", f"{len(v.saffire_pairs)} pair(s). Source of each row: see `source_ref` in the API.", "", "## 3. Correction model", ""]
    if c["status"] == "not_configured":
        L.append(f"{c['message']}. No error figures are reported because no model is configured.")
    else:
        L.append(f"Pairs: **{c['n_pairs']}**; MAE: **{c['mae_pct_o2']}** % O2; max error: **{c['max_error_pct_o2']}** % O2. {c.get('note', '')}")
    L += ["", "## Caveats", ""] + [f"- {x}" for x in v.caveats]
    return "\n".join(L) + "\n"


def write_files() -> ValidationResponse:
    """Store the result in the database (collection `derived_docs`, _id 'validation'); also export validation.json / .md next to the data when the folder is writable."""
    v = compute()
    out = v.model_dump(mode="json")
    out["correction_model"] = v.correction_model   # correction.measured_error() reads mae_pct_o2 from here
    md = markdown(v)
    s = get_settings()
    store.get_db()[s.derived_collection].replace_one({"_id": "validation"}, {"_id": "validation", "data": out, "report_md": md}, upsert=True)
    try:
        s.derived_dir.mkdir(parents=True, exist_ok=True)
        (s.derived_dir / "validation.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (s.derived_dir / "validation_report.md").write_text(md, encoding="utf-8")
    except OSError:
        pass   # read-only file system (cloud host): the database copy is the source of truth
    return v
