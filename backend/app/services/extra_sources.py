"""Extra data sources merged into the base data set at load time (the base data/*.json inputs are never modified).

Current extra source: Link et al. 2018 supplementary Tables S1/S2 (data/derived/link2018_experiments.json, built by scripts/build_link2018_records.py).
Each extra source is a JSON file {"source", "license", "experiments": [<records in the experiments.json schema>]}.
"""
from __future__ import annotations

import json
from pathlib import Path

EXTRA_FILES = ["link2018_experiments.json"]


def extras(data_dir: Path) -> list[dict]:
    out: list[dict] = []
    for name in EXTRA_FILES:
        p = Path(data_dir) / "derived" / name
        if p.exists():
            out += json.loads(p.read_text(encoding="utf-8"))["experiments"]
    return out


def expected_counts(data_dir: Path) -> dict[str, int]:
    d = Path(data_dir)
    base = json.loads((d / "experiments.json").read_text(encoding="utf-8"))
    n_mat = len(json.loads((d / "materials.json").read_text(encoding="utf-8"))["materials"])
    n = len(base) + len(extras(d))
    return {"materials": n_mat, "experiments": n, "cards": n}


def make_card(e: dict, material_name: str) -> dict:
    cond = [f"O2 {e['oxygen_pct']}%"] if e.get("oxygen_pct") is not None else []
    if e.get("airflow_cm_s") is not None:
        cond.append(f"airflow {e['airflow_cm_s']} cm/s")
    if e.get("characteristic_size_mm") is not None:
        cond.append(f"rod diameter {e['characteristic_size_mm']} mm")
    if e["outcome_type"] == "measured":
        outcome = f"{e['outcome_variable']} = {e['outcome_value']} {e['outcome_unit']}"
    else:
        outcome = "no value reported in the source table ('-')"
    text = (f"{material_name} ({e['material_variant']}) solid burn test; {e['gravity_level']}; {e['source_investigation']}. "
            f"Conditions: {', '.join(cond) or 'not recorded'}. Outcome: {outcome}. Source: {e['source_ref']}, doi:{e['doi']}.")
    return {"card_id": f"card-{e['experiment_id']}", "experiment_id": e["experiment_id"], "material_id": e["material_id"], "evidence_type": e["evidence_type"],
            "gravity_level": e["gravity_level"], "flammability_relevant": e["flammability_relevant"], "source_investigation": e["source_investigation"],
            "doi": e["doi"], "finding_ids": e.get("finding_ids", []), "pair_id": e.get("pair_id"), "text": text}


def patch_materials(materials: list[dict], extra: list[dict]) -> None:
    """Add the extra records' variants and DOIs to the in-DB material docs (counts only; ranges already cover them or are left as in the input)."""
    by = {m["material_id"]: m for m in materials}
    for e in extra:
        m = by[e["material_id"]]
        v = next((x for x in m["variants"] if x["variant"] == e["material_variant"]), None)
        if v is None:
            v = {"variant": e["material_variant"], "raw_names": [], "n_records": 0}
            m["variants"].append(v)
        v["n_records"] += 1
        if e["fuel_material"] not in v["raw_names"]:
            v["raw_names"].append(e["fuel_material"])
        if e.get("doi") and e["doi"] not in m.get("dois", []):
            m.setdefault("dois", []).append(e["doi"])
