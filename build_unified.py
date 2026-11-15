"""Build ONE dataset: data/atlas_dataset.json (+ .csv) and data/excluded.csv.

    python build_unified.py

Sources, all from NASA PSI or NASA reports:
  - data/records.json: 148 runs extracted by our code from NASA's raw files (BASS PSI-26 workbook,
    Saffire-I/II/III PSI-98/99/100 tables). Each carries a quote verified word for word.
  - data/team_ibrahim/master_all_records.csv: built by our team member from NASA reports:
    BASS-II (PSI-25, NASA/TM-20210011385 appendix and Table 7.1), ACME BRE (PSI-20, dissertation Table 3.1),
    ACME CFI-G (PSI-159). Each row cites its table or report.

Rules
  - One record per test. Where both sources cover the same test (PSI-26, PSI-98/99/100), we keep the record
    extracted from NASA's raw file (measured O2, quote-verified) and list the other in excluded.csv with the reason.
  - Nothing is filled in by guessing. Assumed values are flagged (pressure_assumed, o2_assumed).
  - Every record says how its outcome label was obtained (evidence) and how much weight a model gives it.
  - Physics groups are kept apart: real_solid, emulated_solid (BRE gas burner), gas_flame (CFI-G).
"""
import csv
import json
from pathlib import Path

import flame_atlas as fa

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TEAM = DATA / "team_ibrahim"

PSI_URL = "https://psi.nasa.gov/physci/repo/data/investigations/{}"
OUR_KEEP = {"PSI-26", "PSI-98", "PSI-99", "PSI-100"}          # we hold NASA's raw files for these
INV_NAME = {"PSI-25": "BASS-II", "PSI-20": "ACME BRE", "PSI-159": "ACME CFI-G"}
GROUP = {"solid_fuel": "real_solid", "emulated_solid_burner": "emulated_solid", "gaseous_fuel_flame": "gas_flame"}
REPORT = {"PSI-25": "NASA BASS-II Summary Report, NASA/TM-20210011385",
          "PSI-20": "ACME BRE dissertation, Table 3.1",
          "PSI-159": "NASA ACME CFI-G test records (PSI-159)"}


def fnum(v):
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def family_from_ibrahim(r):
    cls = (r["material_class"] or "").lower()
    geo = (r["geometry"] or "").lower()
    if cls == "pmma":
        return {"sphere": "PMMA sphere", "rod": "PMMA rod"}.get(geo, "PMMA (sheet / slab)")
    if cls == "sibal":
        return "SIBAL (cotton-fiberglass fabric)"
    if cls == "nomex":
        return "Nomex fabric"
    if cls == "wax":
        return "Wax (candle / slab)"
    if cls == "silicone":
        return "Silicone"
    return None


def main():
    records, sources = fa.load()
    ours, rejected = fa.verify_all(records, sources, show=False)
    assert not rejected, "verify the 148 records first"
    out, excluded = [], []

    for r in ours:
        label_w = None if r.get("sustained") is None else (1.0 if r.get("outcome_method") == "table" else 0.9)
        out.append({
            "id": r["id"], "psi": r["source_id"], "investigation": r["investigation"], "group": "real_solid",
            "material": r["material"], "material_family": r.get("material_family"), "gravity": r["gravity"],
            "o2_percent": r.get("o2_percent"), "o2_assumed": False,
            "pressure_kpa": r.get("pressure_kpa"), "pressure_assumed": False,
            "flow_cms": r.get("flow_cms"), "flow_direction": r.get("flow_direction") or None,
            "sustained": r.get("sustained"), "spread_mm_s": r.get("spread_mm_s"),
            "outcome_text": r.get("outcome_text"),
            "evidence": "quote_verified",
            "label_method": "NASA table" if r.get("outcome_method") == "table" else "crew-note rule (89.5% held-out)",
            "weight": label_w, "quote": r["quote"], "source": f"NASA PSI {r['source_id']} raw file",
            "url": PSI_URL.format(r["source_id"]), "issues": r.get("issues", []),
        })

    with open(TEAM / "master_all_records.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        psi = r["psi_id"]
        if psi in OUR_KEEP:
            excluded.append({"source": "team_ibrahim", "row": r["record_id"], "psi": psi, "test": r["test_id"],
                             "reason": "same test already extracted from NASA's raw file with a verified quote"})
            continue
        oc = r["outcome_class"]
        sustained = True if oc == "sustained" else False if oc in ("not_sustained", "no_ignition") else None
        p_bar = fnum(r["pressure_bar"])
        assumed_p = (r["pressure_source"] or "").startswith("assumed")
        lq = r["label_quality"]
        out.append({
            "id": f"{psi}_{r['test_id']}", "psi": psi, "investigation": INV_NAME.get(psi, r["investigation"]),
            "group": GROUP.get(r["model_group"], r["model_group"]),
            "material": r["material_or_fuel"],
            "material_family": family_from_ibrahim(r) if r["model_group"] == "solid_fuel" else None,
            "gravity": "micro" if r["gravity"] == "microgravity" else "earth",
            "o2_percent": fnum(r["O2_pct"]), "o2_assumed": False,
            "pressure_kpa": None if (p_bar is None or assumed_p) else round(p_bar * 100.0, 2),
            "pressure_assumed": assumed_p,
            "flow_cms": fnum(r["flow_cm_s"]), "flow_direction": r["flow_direction"] or None,
            "sustained": sustained, "spread_mm_s": fnum(r["spread_rate_mm_s"]),
            "outcome_text": r["outcome_detail"] or oc,
            "outcome_class": oc,
            "evidence": {"measured": "report_table", "explicit_table": "report_table",
                         "derived_text": "report_text_rule"}.get(lq, "no_label"),
            "label_method": {"measured": "NASA report table (measured end point)", "explicit_table": "NASA report table",
                             "derived_text": "report comment, keyword rule"}.get(lq, "no outcome in source"),
            "weight": fnum(r["sample_weight"]) or None if sustained is not None else None,
            "quote": None, "source": REPORT.get(psi, psi), "url": PSI_URL.format(psi),
            "hc_kJ_g": fnum(r["hc_kJ_g"]), "fuel_mass_flux_g_m2s": fnum(r["fuel_mass_flux_g_m2s"]),
            "issues": [x for x in [r["notes"].strip()] if x],
        })

    (DATA / "atlas_dataset.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    keys = ["id", "psi", "investigation", "group", "material", "material_family", "gravity", "o2_percent",
            "pressure_kpa", "pressure_assumed", "flow_cms", "flow_direction", "sustained", "evidence",
            "label_method", "weight", "source", "quote"]
    with open(DATA / "atlas_dataset.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    with open(DATA / "excluded.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source", "row", "psi", "test", "reason"])
        w.writeheader()
        w.writerows(excluded)

    from collections import Counter
    print(f"atlas_dataset: {len(out)} records, excluded {len(excluded)} duplicates")
    print(" by investigation:", dict(Counter(r["investigation"] for r in out)))
    print(" by group:", dict(Counter(r["group"] for r in out)))
    print(" by evidence:", dict(Counter(r["evidence"] for r in out)))
    print(" labelled real solids (microgravity):",
          sum(1 for r in out if r["group"] == "real_solid" and r["gravity"] == "micro" and r["sustained"] is not None))


if __name__ == "__main__":
    main()
