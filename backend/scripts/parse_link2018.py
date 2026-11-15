"""Parse Tables S1 (microgravity) and S2 (1g) of the Link et al. 2018 supplementary PDF into rows.

Source: Link, Huang, Fernandez-Pello, Olson, Ferkul (2018), "The Effect of Gravity on Flame Spread over PMMA Cylinders",
Sci Rep 8:120, doi:10.1038/s41598-017-18398-4, Supplemental Material (CC BY 4.0, attribution required).

The PDF tables are two side-by-side blocks whose label cells (d, XO2, sample) are vertically centred on their rows, so the text order is
useless. We use word coordinates, then check: every row has exactly the expected cells, every label's position matches the mean position of the
rows it was assigned, and every numeric word inside the table region is consumed exactly once. Nothing is inferred or converted.

  pip install pdfplumber
  python backend/scripts/parse_link2018.py         # writes data/derived/link2018_S1_S2.csv and .json
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
PDF = DATA / "raw" / "nature" / "Link2018_SciRep8-120_MOESM1_supplementary.pdf"
OUT = DATA / "derived"
CITE = "Link et al. 2018, Sci Rep 8:120, Supplemental Material"
NUM = re.compile(r"^\d+(?:\.\d+)?$")
SAMPLE = re.compile(r"^[A-Z]\d+[a-z]?$")


def page_words(page):
    return [{"t": w["text"], "x": w["x0"], "y": w["top"], "used": False} for w in page.extract_words(x_tolerance=1.5, y_tolerance=2)]


def nearest(x, centers):
    return min(centers, key=lambda k: abs(centers[k] - x))


def cluster_rows(ws, tol=4.0):
    rows, cur = [], []
    for w in sorted(ws, key=lambda w: w["y"]):
        if cur and w["y"] - cur[-1]["y"] > tol:
            rows.append(cur)
            cur = []
        cur.append(w)
    if cur:
        rows.append(cur)
    return rows


def partition(row_ys, label_ys):
    """Split ordered rows into len(label_ys) contiguous groups minimising sum |mean(group) - label_y|. Returns groups of row indices."""
    n, m = len(row_ys), len(label_ys)
    INF = float("inf")
    f = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    f[0][0] = 0.0
    for j in range(1, m + 1):
        for i in range(j, n + 1):
            for k in range(j - 1, i):
                if f[k][j - 1] == INF:
                    continue
                c = f[k][j - 1] + abs(sum(row_ys[k:i]) / (i - k) - label_ys[j - 1])
                if c < f[i][j]:
                    f[i][j], back[i][j] = c, k
    groups, i = [], n
    for j in range(m, 0, -1):
        k = back[i][j]
        groups.append(list(range(k, i)))
        i = k
    return groups[::-1]


def parse_s1(page):
    ws = [w for w in page_words(page) if 330 <= w["y"] <= 700]
    hdr = [w for w in page_words(page) if 320 <= w["y"] <= 326]
    unit = {}
    for side, xc in (("left", 267), ("right", 482)):
        cand = min((w for w in hdr if "/s" in w["t"]), key=lambda w: abs(w["x"] - xc) + (0 if abs(w["x"] - xc) < 15 else 1e6))
        assert abs(cand["x"] - xc) < 15, f"S1 {side}: Vf unit header not found"
        unit[side] = cand["t"].strip("()")
    cols = {"left": {"d": 101, "xo2": 131, "sample": 163, "vg": 203, "dt": 237, "vf": 268},
            "right": {"d": 308, "xo2": 344, "sample": 383, "vg": 421, "dt": 452, "vf": 486}}
    out = []
    for side in ("left", "right"):
        side_ws = [w for w in ws if (w["x"] < 300) == (side == "left")]
        for w in side_ws:
            w["col"] = nearest(w["x"], cols[side])
        steps = [w for w in side_ws if w["col"] in ("vg", "dt", "vf")]
        rows = cluster_rows(steps)
        parsed = []
        for r in rows:
            by = {w["col"]: w for w in r}
            assert sorted(by) == ["dt", "vf", "vg"] and len(r) == 3 and all(NUM.match(w["t"]) for w in r), f"S1 {side} bad row at y={r[0]['y']:.0f}: {[w['t'] for w in r]}"
            parsed.append({"y": sum(w["y"] for w in r) / 3, "vg": float(by["vg"]["t"]), "dt": float(by["dt"]["t"]), "vf": float(by["vf"]["t"]), "words": r})
        xo2 = sorted((w for w in side_ws if w["col"] == "xo2"), key=lambda w: w["y"])
        smp = sorted((w for w in side_ws if w["col"] == "sample"), key=lambda w: w["y"])
        dls = sorted((w for w in side_ws if w["col"] == "d"), key=lambda w: w["y"])
        assert all(SAMPLE.match(s["t"]) for s in smp) and xo2 and all(NUM.match(w["t"]) for w in xo2 + dls), f"S1 {side}: bad label words"
        groups = partition([p["y"] for p in parsed], [s["y"] for s in smp])
        owner = {}
        for sm, g in zip(smp, groups):
            lab = min(xo2, key=lambda w: abs(w["y"] - sm["y"]))
            assert abs(lab["y"] - sm["y"]) <= 14, f"S1 {side} sample {sm['t']}: no O2 label nearby"
            owner.setdefault(id(lab), []).append(sm["t"])
        assert len(owner) == len(xo2) and all(1 <= len(v) <= 2 for v in owner.values()), f"S1 {side}: O2 label use is inconsistent {owner}"
        for sm, g in zip(smp, groups):
            mean = sum(parsed[i]["y"] for i in g) / len(g)
            assert abs(mean - sm["y"]) <= 4.0, f"S1 {side} sample {sm['t']}: label y {sm['y']:.1f} vs rows mean {mean:.1f}"
            xo = float(min(xo2, key=lambda w: abs(w["y"] - sm["y"]))["t"])
            name = sm["t"]
            d_lab = min(dls, key=lambda w: abs(w["y"] - mean))
            for n, i in enumerate(g, 1):
                p = parsed[i]
                out.append({"table": "S1", "gravity": "microgravity", "block": side, "diameter_cm": float(d_lab["t"]), "o2_pct": xo, "sample_no": name,
                            "step": n, "flow_cm_s": p["vg"], "duration_s": p["dt"], "spread_rate_x1e3": p["vf"], "spread_rate_unit_printed": f"x10^-3 {unit[side]}",
                            "uncertainty_pct": None, "no_value": False, "source_ref": f"{CITE}, Table S1 (block {side}, y={p['y']:.0f})"})
        for w in side_ws:
            w["used"] = True
        # band check: each d label centred on its rows
        for d in dls:
            members = [o for o in out if o["block"] == side and o["diameter_cm"] == float(d["t"])]
            names = {o["sample_no"] for o in members}
            ys = [parsed[i]["y"] for sm, g in zip(smp, groups) if sm["t"] in names for i in g]
            assert ys and abs(sum(ys) / len(ys) - d["y"]) <= 4.0, f"S1 {side} d={d['t']} label not centred on its rows"
    assert all(w["used"] for w in ws)
    return out, unit


def parse_s2(page):
    allw = page_words(page)
    fig_y = min(w["y"] for w in allw if w["t"] == "Figure")
    ws = [w for w in allw if 140 <= w["y"] < fig_y]
    cols = {"left": {"d": 140, "xo2": 171, "vg": 209, "vf": 244, "pm": 283}, "right": {"d": 311, "xo2": 341, "vg": 378, "vf": 414, "pm": 455}}
    out = []
    for side in ("left", "right"):
        side_ws = [w for w in ws if (w["x"] < 300) == (side == "left")]
        for w in side_ws:
            w["col"] = nearest(w["x"], cols[side])
        rows = cluster_rows([w for w in side_ws if w["col"] in ("vg", "vf", "pm")])
        xo2 = [w for w in side_ws if w["col"] == "xo2"]
        dls = [w for w in side_ws if w["col"] == "d"]
        assert all(NUM.match(w["t"]) for w in xo2 + dls)
        rows_p = []
        for r in rows:
            by = {w["col"]: w for w in r}
            assert sorted(by) == ["pm", "vf", "vg"] and len(r) == 3, f"S2 {side} bad row at y={r[0]['y']:.0f}: {[w['t'] for w in r]}"
            assert NUM.match(by["vg"]["t"]) and all(by[c]["t"] == "-" or NUM.match(by[c]["t"]) for c in ("vf", "pm"))
            assert (by["vf"]["t"] == "-") == (by["pm"]["t"] == "-"), f"S2 {side}: vf/pm dash mismatch at y={r[0]['y']:.0f}"
            rows_p.append({"y": sum(w["y"] for w in r) / 3, "vg": float(by["vg"]["t"]), "vf": by["vf"]["t"], "pm": by["pm"]["t"]})
        used = {}
        for rp in rows_p:
            lab = min(xo2, key=lambda w: abs(w["y"] - rp["y"]))
            assert abs(lab["y"] - rp["y"]) <= 7.5, f"S2 {side}: no O2 label near row y={rp['y']:.0f}"
            rp["xo2"] = float(lab["t"])
            used.setdefault(id(lab), []).append(rp)
        assert len(used) == len(xo2), f"S2 {side}: an O2 label was not used"
        assert all(len(v) <= 2 and (len(v) == 1 or v[0]["vg"] != v[1]["vg"]) for v in used.values()), f"S2 {side}: label shared by incompatible rows"
        dls.sort(key=lambda w: w["y"])
        for d, g in zip(dls, partition([rp["y"] for rp in rows_p], [d["y"] for d in dls])):
            ys = [rows_p[i]["y"] for i in g]
            assert abs(sum(ys) / len(ys) - d["y"]) <= 4.0, f"S2 {side} d={d['t']} label not centred on its rows"
            for i in g:
                rows_p[i]["d"] = float(d["t"])
        for rp in rows_p:
            dash = rp["vf"] == "-"
            out.append({"table": "S2", "gravity": "1g", "block": side, "diameter_cm": rp["d"], "o2_pct": rp["xo2"], "sample_no": None, "step": None,
                        "flow_cm_s": rp["vg"], "duration_s": None, "spread_rate_x1e3": None if dash else float(rp["vf"]),
                        "spread_rate_unit_printed": "x10^-3 cm/s", "uncertainty_pct": None if dash else float(rp["pm"]), "no_value": dash,
                        "source_ref": f"{CITE}, Table S2 (block {side}, y={rp['y']:.0f}); '-' = no value reported in source" if dash else
                                      f"{CITE}, Table S2 (block {side}, y={rp['y']:.0f})"})
        for w in side_ws:
            w["used"] = True
    assert all(w["used"] for w in ws)
    return out


def main() -> int:
    with pdfplumber.open(PDF) as pdf:
        s1, unit = parse_s1(pdf.pages[0])
        s2 = parse_s2(pdf.pages[1])
    rows = s1 + s2
    OUT.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0])
    with open(OUT / "link2018_S1_S2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    (OUT / "link2018_S1_S2.json").write_text(json.dumps({"source": CITE, "doi": "10.1038/s41598-017-18398-4", "license": "CC BY 4.0",
                                                        "s1_vf_unit_printed_by_block": unit, "rows": rows}, indent=1), encoding="utf-8")
    print(f"S1 rows: {len(s1)} ({len({r['sample_no'] for r in s1})} samples); S2 rows: {len(s2)} ({sum(r['no_value'] for r in s2)} with '-')")
    print("S1 printed Vf unit by block:", unit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
