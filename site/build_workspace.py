"""Build site/workspace.html: Alaa's Flame Atlas research workspace, running on the verified NASA records.

    python site/build_workspace.py

Reads the engine's verified records and embeds them, with the tolerances, mission briefs and statistics,
into site/workspace_template.html. No server, no network: the page works from GitHub Pages or a laptop.
"""
import base64
import json
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
sys.path.insert(0, str(ROOT))
import flame_atlas as fa  # noqa: E402

KEEP = ["id", "investigation", "material", "material_family", "gravity", "o2_percent", "pressure_kpa",
        "flow_cms", "flow_direction", "sustained", "spread_mm_s", "outcome_text", "quote", "source_id", "issues",
        "evidence", "source", "outcome_method", "pressure_assumed"]

SOURCE_INFO = {
    "PSI-26": ("Burning and Suppression of Solids (BASS)", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-26"),
    "PSI-98": ("Spacecraft Fire Experiment-I (Saffire-I)", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-98"),
    "PSI-99": ("Spacecraft Fire Experiment-II (Saffire-II)", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-99"),
    "PSI-100": ("Spacecraft Fire Experiment-III (Saffire-III)", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-100"),
    "PSI-25": ("Burning and Suppression of Solids II (BASS-II), Summary Report NASA/TM-20210011385", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-25"),
    "PSI-20": ("ACME Burning Rate Emulator (BRE)", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-20"),
    "PSI-159": ("ACME Cool Flames Investigation with Gases (CFI-G)", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-159"),
    "CHALLENGE": ("NASA Space Apps 2026: Flame in Freefall challenge statement", None),
    "PSI-26-page": ("NASA PSI-26 (BASS) investigation page", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-26"),
}


def clean(v):
    if isinstance(v, float):
        return round(v, 4)
    return v


def main():
    records, sources = fa.load()
    verified, rejected = fa.verify_all(records, sources, show=False)
    if rejected:
        raise SystemExit(f"{len(rejected)} records failed verification; fix the data first.")
    accepted = fa.load_atlas()                       # one dataset: all real-material records
    others = fa.load_atlas(groups=("emulated_solid", "gas_flame"))
    model_report = json.loads((fa.DATA / "model_report.json").read_text(encoding="utf-8"))
    tol = fa.tolerances(accepted)
    briefs = {}
    for key, env in fa.ENVIRONMENTS.items():
        b = fa.mission_brief(accepted, key)
        briefs[key] = {"name": env["name"], "o2": env["o2"], "pressure": env["pressure"], "quote": env["quote"],
                       "lines": [{k: l.get(k) for k in ("text", "source", "quote")} for l in b["lines"]],
                       "next": fa.next_tests(accepted, key)}
    stats = fa.compute_statistics(accepted)
    issues = json.loads((fa.DATA / "data_issues.json").read_text(encoding="utf-8"))
    ext = []
    for r in others:
        ext.append({"id": r["id"], "inv": r["investigation"], "psi": r["source_id"], "g": r["gravity"], "mat": r["material"],
                    "cls": "emulated solid (gas burner)" if r["group"] == "emulated_solid" else "gas flame",
                    "o2": r.get("o2_percent"), "p": r.get("pressure_kpa"), "flow": r.get("flow_cms"),
                    "out": "kept burning" if r["sustained"] else "went out" if r["sustained"] is False else None,
                    "notes": r.get("outcome_text"), "vt": r.get("outcome_method"), "ref": r.get("source"),
                    "url": f"https://psi.nasa.gov/physci/repo/data/investigations/{r['source_id']}", "flags": "; ".join(r.get("issues") or [])})
    data = {
        "ext": ext,
        "catalog": None,
        "model": model_report,
        "n_verified": len(verified),
        "n_all": len(accepted) + len(others),
        "records": [{k: clean(r.get(k)) for k in KEEP} for r in accepted],
        "tol": {k: round(v, 4) for k, v in tol.items()},
        "briefs": briefs,
        "stats": stats,
        "envelope": fa.envelope(accepted),
        "issues": issues,
        "sources": {k: {"title": t, "url": u} for k, (t, u) in SOURCE_INFO.items()},
        "anchors": list(__import__("csv").DictReader(open(fa.DATA / "team_ibrahim" / "limit_anchors.csv", encoding="utf-8-sig"))),
    }
    logo = SITE / "flame-atlas-logo.png"
    logo_uri = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo.exists() else ""
    html = (SITE / "workspace_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    css = (SITE / "workspace_alaa.css").read_text(encoding="utf-8")
    html = html.replace("__CSS__", css).replace("__DATA__", payload).replace("__LOGO__", logo_uri)
    (SITE / "workspace.html").write_text(html, encoding="utf-8")
    print(f"workspace.html: {len(accepted)} real-material records + {len(ext)} emulated/gas records, {len(html)//1024} KB")


if __name__ == "__main__":
    main()
