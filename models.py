"""Flame Atlas AI models, trained on data/atlas_dataset.json.

    python models.py            # fit, validate, print the report, write data/model_report.json

1. Solid-material model (Bayesian logistic regression)
   P(flame keeps burning) for REAL solid materials in microgravity, from oxygen, airflow and material.
   Gaussian priors, MAP fit by Newton's method, posterior by Laplace approximation, predictions by sampling.
   Each record is weighted by how its label was obtained (NASA table 1.0, crew-note rule 0.9, report comment 0.35).
   Validation: leave-one-investigation-out (train without one NASA investigation, test on it).
   Range rule: the model never predicts outside the oxygen range it was trained on.

2. Emulated-solid model (ACME BRE, PSI-20)
   The only NASA microgravity data that reaches Moon-base air (up to 40% O2, down to 57 kPa). A gas burner that
   emulates a burning solid. Bayesian logistic regression on oxygen, pressure, heat of combustion and fuel flux.
   Caveat kept with every output: BRE lists only tests that ignited, so its probabilities are "given ignition".
"""
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RNG = np.random.default_rng(2026)
MOON = {"o2": 30.0, "pressure_kpa": 70.3}


# ------------------------------------------------------------------ Bayesian logistic regression

def fit_logistic(X, y, w, prior_sd):
    """MAP with Gaussian prior N(0, prior_sd^2) per coefficient; Laplace posterior covariance."""
    beta = np.zeros(X.shape[1])
    P = np.diag(1.0 / np.asarray(prior_sd) ** 2)
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ beta))
        g = X.T @ (w * (y - p)) - P @ beta
        H = X.T @ (X * (w * p * (1 - p))[:, None]) + P
        step = np.linalg.solve(H, g)
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    p = 1 / (1 + np.exp(-X @ beta))
    H = X.T @ (X * (w * p * (1 - p))[:, None]) + P
    return beta, np.linalg.inv(H)


def predict(beta, cov, X, n=4000):
    draws = RNG.multivariate_normal(beta, cov, size=n)
    p = 1 / (1 + np.exp(-(X @ draws.T)))
    return p.mean(axis=1), np.percentile(p, 2.5, axis=1), np.percentile(p, 97.5, axis=1)


def metrics(y, p, w=None):
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    pred = (p >= 0.5).astype(float)
    tp, tn = np.sum((pred == 1) & (y == 1)), np.sum((pred == 0) & (y == 0))
    pos, neg = np.sum(y == 1), np.sum(y == 0)
    bal = np.mean([tp / pos if pos else np.nan, tn / neg if neg else np.nan])
    return {"n": int(len(y)), "accuracy": float(np.mean(pred == y)),
            "balanced_accuracy": None if np.isnan(bal) else float(bal),
            "recall_not_sustained": float(tn / neg) if neg else None,
            "brier": float(np.mean((p - y) ** 2))}


# ------------------------------------------------------------------ 1. real solids

FAMILY_GROUP = {"PMMA sphere": "PMMA", "PMMA (sheet / slab)": "PMMA", "PMMA rod": "PMMA",
                "SIBAL (cotton-fiberglass fabric)": "SIBAL", "Wax (candle / slab)": "Wax",
                "Nomex fabric": "Nomex", "Silicone": "Silicone", "Ultem sheet": "Ultem"}
MATS = ["SIBAL", "Wax", "Nomex", "Silicone", "Ultem"]          # PMMA is the reference


def solid_rows(data):
    rows = []
    for r in data:
        if r["group"] != "real_solid" or r["gravity"] != "micro" or r["sustained"] is None:
            continue
        if r["o2_percent"] is None or r["flow_cms"] is None or not r.get("material_family"):
            continue
        rows.append(r)
    return rows


def solid_X(o2, flow, mat):
    x = [1.0, (o2 - 20.0) / 2.0, math.log1p(flow) - 2.0]
    x += [1.0 if mat == m else 0.0 for m in MATS]
    return x


SOLID_PRIOR = [5.0, 2.0, 2.0] + [1.5] * len(MATS)
SOLID_NAMES = ["intercept", "oxygen (+2 points)", "log airflow", *[f"{m} vs PMMA" for m in MATS]]


def solid_model(data):
    rows = solid_rows(data)
    X = np.array([solid_X(r["o2_percent"], r["flow_cms"], FAMILY_GROUP[r["material_family"]]) for r in rows])
    y = np.array([1.0 if r["sustained"] else 0.0 for r in rows])
    w = np.array([r["weight"] or 0.5 for r in rows])
    beta, cov = fit_logistic(X, y, w, SOLID_PRIOR)
    sd = np.sqrt(np.diag(cov))

    # leave-one-investigation-out
    cv = {}
    for inv in sorted({r["investigation"] for r in rows}):
        tr = np.array([r["investigation"] != inv for r in rows])
        if tr.all() or (~tr).all():
            continue
        b, c = fit_logistic(X[tr], y[tr], w[tr], SOLID_PRIOR)
        p, _, _ = predict(b, c, X[~tr], n=2000)
        base = float(np.average(y[tr], weights=w[tr]))
        cv[inv] = {"model": metrics(y[~tr], p), "baseline_always_burns": metrics(y[~tr], np.full((~tr).sum(), base))}

    o2_lo = min(r["o2_percent"] for r in rows)
    o2_hi = max(r["o2_percent"] for r in rows)
    # oxygen effect: odds ratio per +1 point O2 (coefficient is per +2 points)
    b_o2, s_o2 = beta[1] / 2.0, sd[1] / 2.0
    o2_or = [math.exp(b_o2), math.exp(b_o2 - 1.96 * s_o2), math.exp(b_o2 + 1.96 * s_o2)]

    curves = {}
    grid = np.round(np.arange(math.floor(o2_lo), o2_hi + 0.01, 0.5), 2)
    for mat in ["PMMA"] + MATS:
        Xg = np.array([solid_X(o, 10.0, mat) for o in grid])
        m, lo, hi = predict(beta, cov, Xg, n=3000)
        curves[mat] = [{"o2": float(o), "p": float(a), "lo": float(b_), "hi": float(c_)}
                       for o, a, b_, c_ in zip(grid, m, lo, hi)]

    counts = {}
    for r in rows:
        g = FAMILY_GROUP[r["material_family"]]
        counts.setdefault(g, [0, 0])
        counts[g][1] += 1
        counts[g][0] += 1 if r["sustained"] else 0

    return {"n": len(rows), "by_investigation": {i: sum(1 for r in rows if r["investigation"] == i)
                                                  for i in sorted({r["investigation"] for r in rows})},
            "materials": {k: {"burned": v[0], "tests": v[1]} for k, v in counts.items()},
            "coefficients": [{"name": n, "mean": float(b), "sd": float(s)} for n, b, s in zip(SOLID_NAMES, beta, sd)],
            "oxygen_odds_ratio_per_point": o2_or, "o2_range": [o2_lo, o2_hi], "flow_used_for_curves": 10.0,
            "curves": curves, "cv": cv,
            "moon_air": {"o2": MOON["o2"], "inside_range": MOON["o2"] <= o2_hi,
                         "statement": f"Moon-base air ({MOON['o2']:g}% O2) is {MOON['o2'] - o2_hi:.1f} points beyond the "
                                      f"highest oxygen any real solid was tested at ({o2_hi:g}%). The model does not "
                                      f"predict there."}}


# ------------------------------------------------------------------ 2. emulated solids (ACME BRE)

def bre_X(o2, p_kpa, hc, flux):
    return [1.0, (o2 - 30.0) / 4.0, (p_kpa - 70.0) / 20.0, (hc - 35.0) / 12.0, math.log(flux) - 1.0]


BRE_PRIOR = [5.0, 2.0, 2.0, 2.0, 2.0]
BRE_NAMES = ["intercept", "oxygen (+4 points)", "pressure (+20 kPa)", "heat of combustion (+12 kJ/g)", "log fuel flux"]


def bre_model(data):
    rows = [r for r in data if r["group"] == "emulated_solid" and r["sustained"] is not None and r["o2_percent"]
            and r["pressure_kpa"] and r.get("hc_kJ_g") and r.get("fuel_mass_flux_g_m2s")]
    X = np.array([bre_X(r["o2_percent"], r["pressure_kpa"], r["hc_kJ_g"], r["fuel_mass_flux_g_m2s"]) for r in rows])
    y = np.array([1.0 if r["sustained"] else 0.0 for r in rows])
    w = np.ones(len(rows))
    beta, cov = fit_logistic(X, y, w, BRE_PRIOR)
    sd = np.sqrt(np.diag(cov))
    # leave-one-out
    preds = []
    for i in range(len(rows)):
        tr = np.arange(len(rows)) != i
        b, c = fit_logistic(X[tr], y[tr], w[tr], BRE_PRIOR)
        preds.append(float(1 / (1 + np.exp(-X[i] @ b))))
    near = [r for r in rows if 60 <= r["pressure_kpa"] <= 80 and 24 <= r["o2_percent"] <= 32]
    fluxes = sorted(r["fuel_mass_flux_g_m2s"] for r in rows)
    lo_f, hi_f = fluxes[len(fluxes) // 10], fluxes[-len(fluxes) // 10]
    moon = {}
    for hc, label in ((23.6, "PMMA-like fuel (23.6 kJ/g)"), (47.2, "polyethylene-like fuel (47.2 kJ/g)")):
        fl = np.geomspace(lo_f, hi_f, 9)
        Xg = np.array([bre_X(MOON["o2"], MOON["pressure_kpa"], hc, f) for f in fl])
        m, lo, hi = predict(beta, cov, Xg, n=3000)
        moon[label] = [{"flux": float(f), "p": float(a), "lo": float(b_), "hi": float(c_)}
                       for f, a, b_, c_ in zip(fl, m, lo, hi)]
    return {"n": len(rows), "o2_range": [min(r["o2_percent"] for r in rows), max(r["o2_percent"] for r in rows)],
            "pressure_range_kpa": [min(r["pressure_kpa"] for r in rows), max(r["pressure_kpa"] for r in rows)],
            "coefficients": [{"name": n, "mean": float(b), "sd": float(s)} for n, b, s in zip(BRE_NAMES, beta, sd)],
            "loo": metrics(y, preds), "baseline": metrics(y, np.full(len(y), y.mean())),
            "near_moon_tests": {"n": len(near), "burned": sum(1 for r in near if r["sustained"]),
                                "ids": [r["id"] for r in near]},
            "moon_air_estimate": moon,
            "caveat": "BRE is a gas burner emulating a solid, and its table lists only tests that ignited: "
                      "probabilities are 'keeps burning, given it ignited', for an emulated fuel, not a real material."}


def main():
    data = json.loads((DATA / "atlas_dataset.json").read_text(encoding="utf-8"))
    s, b = solid_model(data), bre_model(data)
    (DATA / "model_report.json").write_text(json.dumps({"solid": s, "bre": b}, indent=1), encoding="utf-8")

    print(f"SOLID-MATERIAL MODEL (Bayesian logistic regression): {s['n']} labelled microgravity runs {s['by_investigation']}")
    for c in s["coefficients"]:
        print(f"  {c['name']:<22} {c['mean']:+.2f} ± {c['sd']:.2f}")
    o = s["oxygen_odds_ratio_per_point"]
    print(f"  Oxygen: each +1 point O2 multiplies the odds of sustained burning by {o[0]:.2f} (95% CI {o[1]:.2f}-{o[2]:.2f})")
    print("  Leave-one-investigation-out validation:")
    for inv, v in s["cv"].items():
        m, bl = v["model"], v["baseline_always_burns"]
        ba = "n/a" if m["balanced_accuracy"] is None else f"{m['balanced_accuracy']:.0%}"
        print(f"    test on {inv:<11} n={m['n']:<3} accuracy {m['accuracy']:.0%} (baseline {bl['accuracy']:.0%}), "
              f"balanced {ba}, Brier {m['brier']:.3f} (baseline {bl['brier']:.3f})")
    print("  ", s["moon_air"]["statement"])

    print(f"\nEMULATED-SOLID MODEL (ACME BRE, PSI-20): {b['n']} tests, O2 {b['o2_range']}, pressure {b['pressure_range_kpa']} kPa")
    for c in b["coefficients"]:
        print(f"  {c['name']:<30} {c['mean']:+.2f} ± {c['sd']:.2f}")
    print(f"  Leave-one-out accuracy {b['loo']['accuracy']:.0%} (baseline {b['baseline']['accuracy']:.0%}), "
          f"Brier {b['loo']['brier']:.3f} (baseline {b['baseline']['brier']:.3f})")
    nm = b["near_moon_tests"]
    print(f"  Tests near Moon-base air (24-32% O2, 60-80 kPa): {nm['burned']} of {nm['n']} kept burning")
    for label, pts in b["moon_air_estimate"].items():
        print(f"  Moon air, {label}: P(keeps burning | ignited) from {pts[0]['p']:.0%} [{pts[0]['lo']:.0%}-{pts[0]['hi']:.0%}] "
              f"at low fuel flux to {pts[-1]['p']:.0%} [{pts[-1]['lo']:.0%}-{pts[-1]['hi']:.0%}] at high flux")
    print("  Caveat:", b["caveat"])


if __name__ == "__main__":
    main()
