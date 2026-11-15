"""
Build Flame Atlas records from raw NASA PSI files.

  python build_dataset.py <folder with Saffire CSVs> <PSI-26 BASS_test_matrix.xlsx>

Reads (NASA PSI, CC0):
  PSI-98  Saffire-I   Experimental table
  PSI-99  Saffire-II  Experimental table (microgravity + 1-g comparison columns)
  PSI-100 Saffire-III Experimental table
  PSI-26  BASS        BASS_test_matrix.xlsx, sheet "as run matrix" (NASA's own workbook)

Writes data/records.json, data/sources/*.txt, data/data_issues.json.

Every record carries a short quote copied from the source file. The engine
re-checks that quote word for word, so nothing here is taken on trust.
Structured columns are parsed by code. For BASS, the burn outcome is read from
the crew's free-text observations by a transparent keyword rule; every such
record is marked outcome_method="keyword" and listed for human (or LLM+quote)
review. Nothing is guessed silently: problems go to data_issues.json.
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"


def num(s):
    m = re.search(r"-?\d+(?:\.\d+)?", s or "")
    return float(m.group()) if m else None


def family(name):
    n = (name or "").lower()
    if "sibal" in n or "cotton" in n:
        return "SIBAL (cotton-fiberglass fabric)"
    if "nomex" in n:
        return "Nomex fabric"
    if "ultem" in n:
        return "Ultem sheet"
    if "silicone" in n:
        return "Silicone"
    if "wax" in n or "candle" in n or "paraffin" in n or "parrafin" in n:
        return "Wax (candle / slab)"
    if "sphere" in n:
        return "PMMA sphere"
    if "pmma" in n:
        return "PMMA (sheet / slab)"
    return None


def first_words(text, n=22):
    return " ".join(text.split()[:n])


def sentence_with(text, pattern, n=22):
    for s in re.split(r"(?<=[.!?])\s+", text):
        if re.search(pattern, s, re.I):
            return first_words(s, n)
    return first_words(text, n)


def saffire_2(path, records, issues):
    src = "PSI-99"
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8", errors="replace"))))
    last_material = None
    for r in rows[1:]:
        if not r or not re.match(r"^2-\d$", r[0].strip()):
            continue
        sid = r[0].strip()
        mat = r[1].strip()
        line = ",".join(r[:7])
        quote = first_words(line, 20)
        rec_issues = []
        if not mat:
            rec_issues.append(f"Material cell blank in NASA table; carried over from previous row ({last_material}). Confirm in PSI-99 Experimental Details.")
            mat = last_material
        thick = r[2].strip()
        if re.match(r"^0\d", thick):
            rec_issues.append(f"Thickness written as '{thick}' in NASA table; probably 0.{thick[1:]}. Not used for ranking.")
        last_material = mat
        o2 = num(r[6])
        mg_burn, mg_spread = r[11].strip(), r[12].strip()
        g1_burn, g1_spread = r[13].strip(), r[14].strip()
        parts = [mat]
        if mat == "PMMA & Nomex":
            parts = ["PMMA", "Nomex"]
        for i, m in enumerate(parts):
            if mat == "PMMA & Nomex":
                sustained = (i == 0)  # Note 2: PMMA consumed, Nomex not ignited
                note = "Note 2: The PMMA portion was completely consumed but the Nomex was not ignited."
            else:
                sustained = not mg_burn.startswith("~ 0")
                note = None
            spread = num(mg_spread) if "mm/s" in mg_spread else None
            rec = dict(id=f"{src}_{sid}" + (f"_{m}" if len(parts) > 1 else ""), source_id=src,
                       investigation="Saffire-II", material=m, material_family=family(m), gravity="micro",
                       o2_percent=o2, pressure=None, pressure_unit="kPa", flow=num(r[5]), flow_unit="cm/s",
                       flow_direction=r[10].strip(), sustained=sustained, spread_mm_s=spread,
                       outcome_text=f"micro-g burn length {mg_burn}; spread {mg_spread}" + (f"; {note}" if note else ""),
                       outcome_method="table", quote=quote, issues=rec_issues)
            records.append(rec)
            # 1-g comparison from the same NASA table (NASA ground test of the same material)
            if mat == "PMMA & Nomex":
                g_sus = (i == 0)
            else:
                g_sus = g1_burn.lower().startswith("complete") or (num(g1_burn) or 0) > 0
            g_spread = num(g1_spread) if "mm/s" in g1_spread else None
            records.append(dict(rec, id=rec["id"] + "_1g", gravity="earth", o2_percent=None, flow=None,
                                sustained=g_sus, spread_mm_s=g_spread,
                                outcome_text=f"1-g burn length {g1_burn}; spread {g1_spread}",
                                issues=rec_issues + ["1-g test conditions (O2, flow) not given in this table."]))
        if rec_issues:
            issues.append(dict(record=sid, source=src, issues=rec_issues))


def saffire_1_3(path, src, inv, records, issues):
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8", errors="replace"))))
    for r in rows:
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        sid = r.get("Sample Number", "")
        if not re.match(r"^S\d$", sid):
            continue
        line = ",".join([sid, r.get("Material", ""), r.get("Sample Thickness (cm)", r.get("Sample Thickness", ""))])
        burn = r.get("Burn Time (s)")
        o2 = num(r.get("Percent O2", ""))
        rec_issues = []
        if o2 is None:
            rec_issues.append("No O2 reported in this NASA table.")
        if not burn:
            rec_issues.append("No burn outcome reported in this NASA table; outcome left empty.")
        records.append(dict(id=f"{src}_{sid}", source_id=src, investigation=inv, material=r["Material"],
                            material_family=family(r["Material"]), gravity="micro", o2_percent=o2,
                            pressure=None, pressure_unit="kPa",
                            flow=num(r.get("Air Flow (cm/s)", r.get("Air Flow", ""))), flow_unit="cm/s",
                            flow_direction=r.get("Flow Direction", r.get("Direction", "")),
                            sustained=(True if burn and num(burn) and num(burn) > 0 else None),
                            spread_mm_s=None, outcome_text=f"burn time {burn or 'not reported'} s",
                            outcome_method="table", quote=first_words(line, 20), issues=rec_issues))
        if rec_issues:
            issues.append(dict(record=sid, source=src, issues=rec_issues))


NEG = re.compile(r"(did ?n.?t ignite|no ignition|not ignite|failed to ignite|would ?n.?t ignite|never ignited|no flame|"
                 r"died when (the )?igniter|(went|goes) out when (the )?igniter|out when igniter was retracted|"
                 r"no luck keeping|not sustained|re-?ignition attempts failed|winks out)", re.I)
IGNITER_FAIL = re.compile(r"(igniter (is )?broken|igniter broke|broke(n)? (\d )?igniter|igniter failed|no go)", re.I)
FLAME_WORDS = re.compile(r"(burn|flame|soot|blue|lit\b|spread)", re.I)


def bass_rows_from_xlsx(xlsx_path):
    """Read NASA's own PSI-26 workbook (sheet 'as run matrix'). Returns (rows, csv_text)."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["as run matrix"]
    out, buf = [], io.StringIO()
    w = csv.writer(buf)
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        vals = ["" if v is None else str(v) for v in row]
        w.writerow([i] + vals)
        if i >= 4 and len(vals) >= 30 and (vals[5] or vals[29]):
            out.append(dict(xrow=str(i), material=vals[5].strip(), air=vals[10].strip(), o2=vals[26].strip(),
                            p_atm=vals[27].strip(), obs=vals[29].strip()))
    return out, buf.getvalue()


def bass(xlsx_path, records, issues):
    src = "PSI-26"
    rows, _ = bass_rows_from_xlsx(xlsx_path)
    for row in rows:
        xrow, mat, air, p_atm, obs = row["xrow"], row["material"], row["air"], row["p_atm"], row["obs"]
        fam = family(mat)
        rec_issues = []
        if not fam:
            rec_issues.append(f"Material '{mat or 'blank'}' not recognised; excluded from ranking.")
        if not obs:
            rec_issues.append("No crew observation; outcome unknown.")
        neg = NEG.search(obs or "")
        flame = FLAME_WORDS.search(re.sub(r"(wake ign|igniter|ignition kernel)", "", obs or "", flags=re.I))
        invalid = bool(IGNITER_FAIL.search(obs or "")) and not flame
        if not obs or invalid:
            sustained = None
            if invalid:
                rec_issues.append("Crew notes describe an igniter failure with no flame: not a valid burn test.")
        else:
            sustained = False if neg else True
        quote = (sentence_with(obs, IGNITER_FAIL.pattern, 22) if invalid else
                 sentence_with(obs, NEG.pattern if neg else r"burn|flame|spread|ignit", 22)) if obs else ""
        o2v = num(row["o2"])
        p = num(p_atm)
        if p is None:
            rec_issues.append(f"Pressure '{p_atm}' not numeric.")
        records.append(dict(id=f"{src}_row{xrow}", source_id=src, investigation="BASS", material=mat or None,
                            material_family=fam, gravity="micro",
                            o2_percent=round(o2v * 100, 2) if o2v is not None else None,
                            pressure=p, pressure_unit="atm", flow=num(air), flow_unit="cm/s",
                            flow_direction="opposed" if "oppos" in mat.lower() else "",
                            sustained=sustained, spread_mm_s=None,
                            outcome_text=(obs[:240] + ("..." if len(obs) > 240 else "")),
                            outcome_method="keyword", quote=quote, issues=rec_issues))
        if rec_issues:
            issues.append(dict(record=f"row {xrow}", source=src, issues=rec_issues))


def main():
    raw = Path(sys.argv[1] if len(sys.argv) > 1 else "raw")
    (OUT / "sources").mkdir(parents=True, exist_ok=True)
    files = {
        "PSI-98": raw / "PSI-98_Experimental_table_SAFFIRE-1.csv",
        "PSI-99": raw / "PSI-99_Experimental_table_SAFFIRE-2.csv",
        "PSI-100": raw / "PSI-100_Experimental_table_SAFFIRE-3.csv",
    }
    for sid, f in files.items():
        (OUT / "sources" / f"{sid}.txt").write_text(f.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    bass_xlsx = Path(sys.argv[2]) if len(sys.argv) > 2 else raw / "BASS_test_matrix.xlsx"
    _, bass_csv = bass_rows_from_xlsx(bass_xlsx)
    (OUT / "sources" / "PSI-26.txt").write_text(bass_csv, encoding="utf-8")
    records, issues = [], []
    saffire_1_3(files["PSI-98"], "PSI-98", "Saffire-I", records, issues)
    saffire_2(files["PSI-99"], records, issues)
    saffire_1_3(files["PSI-100"], "PSI-100", "Saffire-III", records, issues)
    bass(bass_xlsx, records, issues)
    (OUT / "records.json").write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "data_issues.json").write_text(json.dumps(issues, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(records)} records written, {len(issues)} issue entries logged")


if __name__ == "__main__":
    main()
