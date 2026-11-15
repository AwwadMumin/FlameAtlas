"""Rebuild site/index.html from the current data:  python site/build_site.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import flame_atlas as fa

recs, srcs = fa.load()
verified, _ = fa.verify_all(recs, srcs, show=False)
acc = fa.load_atlas()
n_all = len(json.loads((ROOT / "data" / "atlas_dataset.json").read_text(encoding="utf-8")))
keep = ["id", "investigation", "material", "material_family", "gravity", "o2_percent", "pressure_kpa", "flow_cms",
        "flow_direction", "sustained", "spread_mm_s", "outcome_text", "outcome_method", "quote", "source_id", "issues", "source", "evidence"]
briefs = {e: fa.mission_brief(acc, e) for e in fa.ENVIRONMENTS}
for b in briefs.values():
    b.pop("envelope", None)
o2 = list(range(15, 42)); p = list(range(25, 106, 5))
g = fa.gap_map(acc, "micro", None, o2, p)
envl = fa.envelope(acc)
gold = json.loads((ROOT / "data" / "gold.json").read_text(encoding="utf-8"))
by = {r["id"]: r for r in verified}
def score(part):
    it = [x for x in gold["records"] if x["set"] == part]
    return [sum(1 for x in it if by.get(x["id"], {}).get("sustained") == x["sustained"]), len(it)]
bundle = {"records": [{k: r.get(k) for k in keep} for r in acc], "briefs": briefs, "envs": fa.ENVIRONMENTS,
          "gap": {"o2": o2, "p": p, "grid": [[{"s": c["status"], "n": c["close_runs"], "m": c["materials"]} for c in row] for row in g["grid"]]},
          "envelope": envl, "earth_vs_space": fa.earth_vs_space(acc),
          "issues": json.loads((ROOT / "data" / "data_issues.json").read_text(encoding="utf-8")),
          "stats": fa.compute_statistics(acc), "eval": {"quotes": [len(verified), len(recs)], "dev": score("development"), "held": score("held-out"), "v1": [14, 19]}}
tol = fa.tolerances(acc)
e = fa.ENVIRONMENTS["moon"]; sc = {"o2": e["o2"], "pressure": e["pressure"], "flow": None, "gravity": "micro"}
cand = [r for r in acc if r["gravity"] == "micro" and r.get("pressure_kpa") is not None and r.get("o2_percent") is not None]
near = min(cand, key=lambda r: fa.distance(r, sc, tol)[0])
o2s = [r["o2_percent"] for r in acc if r.get("o2_percent") is not None]
bundle["worked"] = {"env": e, "tol": tol, "o2_range": [min(o2s), max(o2s)], "record": {k: near.get(k) for k in keep},
                    "d": fa.distance(near, sc, tol)[0]}
data = json.dumps(bundle, ensure_ascii=False, default=list).replace("</", "<\\/")
tpl = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
d = bundle["worked"]["d"]; t_o2 = tol["o2_percent"]; t_p = tol["pressure_kpa"]
eq = (f"d = √( (({near['o2_percent']:.2f} − {e['o2']:g}) / {t_o2:.2f})² + (({near['pressure_kpa']:.1f} − {e['pressure']:g}) / {t_p:g})² ) = {d:.2f}")
for k, v in {"__D__": f"{d:.2f}", "__EQ__": eq, "__NSOLID__": str(len(acc)), "__NALL__": str(n_all)}.items():
    tpl = tpl.replace(k, v)
(ROOT / "site" / "index.html").write_text(tpl.replace("__DATA__", data), encoding="utf-8")
print("site/index.html rebuilt:", len(acc), "real-material records of", n_all, "; d =", round(bundle["worked"]["d"], 2))
