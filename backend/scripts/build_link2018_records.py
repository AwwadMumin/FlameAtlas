"""Convert data/derived/link2018_S1_S2.json (parse_link2018.py) into records in the experiments.json schema:
data/derived/link2018_experiments.json. Pure mapping; nothing is inferred beyond the table caption (B = black, C = clear).

  python backend/scripts/build_link2018_records.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DOI = "10.1038/s41598-017-18398-4"
SRC = "Link 2018 (Sci Rep 8:120), ISS BASS-II vs ground PMMA rods"
PDF = "data/raw/nature/Link2018_SciRep8-120_MOESM1_supplementary.pdf"
FLAG_UNIT = ("Table S1 right-hand column header prints the spread rate in mm/s while the left-hand header prints cm/s; the unit is unresolved "
             "(probable typo). The value is shown exactly as printed, unconverted.")
FLAG_P = "Sample prefix 'P' is not explained in the Table S1 caption (it defines B = black and C = clear PMMA only); colour not stated."
FLAG_DASH = "'-' in Table S2: no value reported in the source. It is not interpreted as extinction or as no spread."
FLAG_P_STATED = "Pressure is not stated in the table."


def variant(sample):
    return {"B": "rod, black", "C": "rod, clear"}.get(sample[0] if sample else "", "rod (colour not stated in table)")


def main() -> int:
    d = json.loads((DATA / "derived" / "link2018_S1_S2.json").read_text(encoding="utf-8"))
    counters: dict[tuple, int] = {}
    out = []
    for r in d["rows"]:
        t, block = r["table"], r["block"]
        counters[(t, block)] = counters.get((t, block), 0) + 1
        k = counters[(t, block)]
        s1 = t == "S1"
        eid = f"LINK2018-S1-{r['sample_no']}-{r['step']}" if s1 else f"LINK2018-S2-{block[0].upper()}{k:02d}"
        flags = [FLAG_P_STATED]
        if s1 and block == "right":
            flags.append(FLAG_UNIT)
        if s1 and r["sample_no"][0] not in "BC":
            flags.append(FLAG_P)
        if r["no_value"]:
            flags.append(FLAG_DASH)
        unit = r["spread_rate_unit_printed"] + " (as printed)"
        dcm = r["diameter_cm"]
        out.append({
            "experiment_id": eid, "source_investigation": SRC, "psi_id": None, "doi": DOI,
            "gravity_level": "microgravity" if s1 else "1g (ground)",
            "platform": "International Space Station (BASS-II flight data)" if s1 else "Ground, normal gravity",
            "fuel_material": f"PMMA rod, d = {dcm} cm" + (f" (sample {r['sample_no']})" if s1 else ", black"),
            "material_class": "solid", "configuration": f"PMMA rod flame spread; rod diameter {dcm} cm", "ignition_method": None,
            "oxygen_pct": r["o2_pct"], "pressure_kpa": None, "airflow_cm_s": r["flow_cm_s"], "airflow_note": "Vg as printed in the table",
            "diluent": None, "characteristic_size_mm": round(dcm * 10, 3), "temperature_c": None, "smoke_signal_mg_m3": None,
            "outcome_type": "conditions_only" if r["no_value"] else "measured",
            "outcome_variable": None if r["no_value"] else "flame_spread_rate",
            "outcome_value": None if r["no_value"] else r["spread_rate_x1e3"], "outcome_unit": None if r["no_value"] else unit,
            "outcome_class": None, "flame_behavior_notes": None, "value_type": "published supplementary table (peer-reviewed paper)",
            "source_ref": r["source_ref"], "source_record_id": eid, "quality_flags": flags, "uloi_pct": None, "psi_url": None,
            "oxygen_basis": f"XO2 (%) as printed in Table {t}", "outcome_class_original": None, "split_from": None,
            "extra": {"table": t, "block": block, "sample_no": r["sample_no"], "step": r["step"], "duration_s": r["duration_s"], "diameter_cm": dcm,
                      "uncertainty_pct": r["uncertainty_pct"], "table_caption_note": None if s1 else "black PMMA rods; average of at least 3 repeating tests; steady spread for at least 5 min or 4 cm"},
            "corrections": None, "material_id": "pmma", "material_variant": variant(r["sample_no"]) if s1 else "rod, black",
            "evidence_type": "solid_burn_test", "flammability_relevant": True, "pair_id": None, "cross_gravity_group": "XG-pmma", "finding_ids": [],
            "license": "CC BY 4.0", "source_file": PDF, "source_row": len(out) + 1})
    assert len({e["experiment_id"] for e in out}) == len(out) == 98, "ids must be unique; expected 52 + 46 rows"
    (DATA / "derived" / "link2018_experiments.json").write_text(json.dumps(
        {"source": "Link, Huang, Fernandez-Pello, Olson, Ferkul (2018), Sci Rep 8:120, Supplemental Material Tables S1/S2", "doi": DOI, "license": "CC BY 4.0 (attribution required)",
         "experiments": out}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(out)} records to data/derived/link2018_experiments.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
