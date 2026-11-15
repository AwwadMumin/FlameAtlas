"""Microgravity burn-outcome model: Bayesian logistic regression for REAL solid materials.

Adapted from models.py of the `ai-engine` branch (commit 43030de). The training data is data/atlas_dataset.json from that branch.

  P(flame keeps burning) from oxygen, airflow and material (PMMA is the reference group).
  Gaussian priors, MAP by Newton's method, posterior by Laplace approximation, predictions by sampling.
  Each run is weighted by how its label was obtained. Only label methods listed in settings.model_label_methods are used.
  Validation: leave-one-investigation-out (train without one NASA investigation, test on it).

Rules kept: only microgravity; the model never predicts outside the oxygen or airflow range it was trained on; a material the model
has no coefficient for gets the prior material spread (a wide interval), never a guess. Output is always "Model estimate — not tested".
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.core.config import get_settings

SEED = 2026
INFORMATIVE_MAX_WIDTH = 0.5      # a 95% interval wider than this says almost nothing: it is shown as "cannot be determined", not as a headline number
FAMILY_GROUP = {"PMMA sphere": "PMMA", "PMMA (sheet / slab)": "PMMA", "PMMA rod": "PMMA",
                "SIBAL (cotton-fiberglass fabric)": "SIBAL", "Wax (candle / slab)": "Wax",
                "Nomex fabric": "Nomex", "Silicone": "Silicone", "Ultem sheet": "Ultem"}
MATS = ["SIBAL", "Wax", "Nomex", "Silicone", "Ultem"]                      # PMMA is the reference
CATALOG_TO_GROUP = {"pmma": "PMMA", "sibal": "SIBAL", "wax": "Wax", "nomex": "Nomex", "silicone": "Silicone", "pei": "Ultem"}  # Ultem = PEI
PRIOR_SD = [5.0, 2.0, 2.0] + [1.5] * len(MATS)
MATERIAL_PRIOR_SD = 1.5
NAMES = ["intercept", "oxygen (+2 points)", "log airflow", *[f"{m} vs PMMA" for m in MATS]]


def _x(o2: float, flow: float, group: str | None) -> list[float]:
    return [1.0, (o2 - 20.0) / 2.0, math.log1p(flow) - 2.0] + [1.0 if group == m else 0.0 for m in MATS]


def _fit(X, y, w):
    beta = np.zeros(X.shape[1])
    P = np.diag(1.0 / np.asarray(PRIOR_SD) ** 2)
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


def _sample_p(beta, cov, X, n, seed=SEED):
    draws = np.random.default_rng(seed).multivariate_normal(beta, cov, size=n)
    return 1 / (1 + np.exp(-(X @ draws.T)))


@dataclass
class Model:
    beta: np.ndarray
    cov: np.ndarray
    n: int
    o2_range: tuple[float, float]
    flow_range: tuple[float, float]
    flows: list[float]
    by_investigation: dict[str, int]
    by_material: dict[str, dict[str, int]]
    by_label_method: dict[str, int]
    odds_ratio: list[float]
    validation: dict


def rows_for_training() -> list[dict]:
    s = get_settings()
    data = json.loads((s.data_dir / "atlas_dataset.json").read_text(encoding="utf-8"))
    allowed = set(s.model_label_methods)
    return [r for r in data
            if r["group"] == "real_solid" and r["gravity"] == "micro" and r["sustained"] is not None
            and r["o2_percent"] is not None and r["flow_cms"] is not None and r.get("material_family") in FAMILY_GROUP
            and r.get("label_method") in allowed]


def _metrics(y, p):
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    pred = (p >= 0.5).astype(float)
    pos, neg = np.sum(y == 1), np.sum(y == 0)
    tp, tn = np.sum((pred == 1) & (y == 1)), np.sum((pred == 0) & (y == 0))
    bal = [v for v in (tp / pos if pos else None, tn / neg if neg else None) if v is not None]
    return {"n": int(len(y)), "accuracy": round(float(np.mean(pred == y)), 3),
            "balanced_accuracy": round(float(np.mean(bal)), 3) if len(bal) == 2 else None, "brier": round(float(np.mean((p - y) ** 2)), 3)}


@lru_cache
def get_model() -> Model:
    rows = rows_for_training()
    X = np.array([_x(r["o2_percent"], r["flow_cms"], FAMILY_GROUP[r["material_family"]]) for r in rows])
    y = np.array([1.0 if r["sustained"] else 0.0 for r in rows])
    w = np.array([r["weight"] or 0.5 for r in rows])
    beta, cov = _fit(X, y, w)
    # leave-one-investigation-out
    per, oof_p, oof_y, oof_base = {}, [], [], []
    for inv in sorted({r["investigation"] for r in rows}):
        te = np.array([r["investigation"] == inv for r in rows])
        if te.all() or not te.any():
            continue
        b, c = _fit(X[~te], y[~te], w[~te])
        p = _sample_p(b, c, X[te], 1500).mean(axis=1)
        base = float(np.average(y[~te], weights=w[~te]))
        per[inv] = {"model": _metrics(y[te], p), "baseline_always_burns_share": _metrics(y[te], np.full(te.sum(), base))}
        oof_p += list(p); oof_y += list(y[te]); oof_base += [base] * int(te.sum())
    pooled = {"model": _metrics(oof_y, oof_p), "baseline": _metrics(oof_y, oof_base)} if oof_y else None
    sd = np.sqrt(np.diag(cov))
    b_o2, s_o2 = beta[1] / 2.0, sd[1] / 2.0
    mats: dict[str, dict[str, int]] = {}
    for r in rows:
        g = FAMILY_GROUP[r["material_family"]]
        m = mats.setdefault(g, {"tests": 0, "burned": 0})
        m["tests"] += 1; m["burned"] += 1 if r["sustained"] else 0
    flows = sorted({float(r["flow_cms"]) for r in rows})
    labels: dict[str, int] = {}
    for r in rows:
        labels[r["label_method"]] = labels.get(r["label_method"], 0) + 1
    return Model(beta=beta, cov=cov, n=len(rows), o2_range=(min(r["o2_percent"] for r in rows), max(r["o2_percent"] for r in rows)),
                 flow_range=(flows[0], flows[-1]), flows=flows,
                 by_investigation={i: sum(1 for r in rows if r["investigation"] == i) for i in sorted({r["investigation"] for r in rows})},
                 by_material=mats, by_label_method=labels,
                 odds_ratio=[round(math.exp(v), 2) for v in (b_o2, b_o2 - 1.96 * s_o2, b_o2 + 1.96 * s_o2)],
                 validation={"method": "leave-one-investigation-out", "per_investigation": per, "pooled": pooled})


def predict(group: str | None, o2: float, flow: float | None, n: int = 4000) -> dict:
    """Return {applicable, reason | probability, lo, hi, ...}. group=None means a material the model has no coefficient for."""
    m = get_model()
    lo, hi = m.o2_range
    if not lo <= o2 <= hi:
        return {"applicable": False, "reason": f"{o2:g}% O2 is outside the {lo:g}–{hi:g}% range this model was trained on, so it does not predict there."}
    if flow is not None and not m.flow_range[0] <= flow <= m.flow_range[1]:
        return {"applicable": False, "reason": f"Airflow {flow:g} cm/s is outside the {m.flow_range[0]:g}–{m.flow_range[1]:g} cm/s range this model was trained on."}
    flows = [flow] if flow is not None else m.flows
    rng = np.random.default_rng(SEED)
    draws = rng.multivariate_normal(m.beta, m.cov, size=n)
    X = np.array([_x(o2, f, group) for f in flows])
    logit = X @ draws.T
    if group is None:   # no coefficient for this material: add the prior material spread (a wide interval, never a point guess)
        logit = logit + rng.normal(0.0, MATERIAL_PRIOR_SD, size=(1, n))
    p = (1 / (1 + np.exp(-logit))).mean(axis=0)
    return {"applicable": True, "probability": float(p.mean()), "lo": float(np.percentile(p, 2.5)), "hi": float(np.percentile(p, 97.5)),
            "flows_averaged": flow is None}


def describe(group: str | None, o2: float, flow: float | None, role: str, basis: str, pressure_kpa: float | None = None):
    """Build the API object (BurnPrediction) or return (None, reason) when the model does not apply."""
    from app.models.api import BurnPrediction, ModelValidation, ModelValidationItem
    pr = predict(group, o2, flow)
    if not pr["applicable"]:
        return None, pr["reason"]
    m = get_model()
    v = m.validation
    per = [ModelValidationItem(investigation=k, n=x["model"]["n"], model_brier=x["model"]["brier"], baseline_brier=x["baseline_always_burns_share"]["brier"],
                               model_accuracy=x["model"]["accuracy"], baseline_accuracy=x["baseline_always_burns_share"]["accuracy"]) for k, x in v["per_investigation"].items()]
    pool = v["pooled"]
    beats = pool["model"]["brier"] < pool["baseline"]["brier"]
    val = ModelValidation(pooled_n=pool["model"]["n"], model_brier=pool["model"]["brier"], baseline_brier=pool["baseline"]["brier"],
                          model_accuracy=pool["model"]["accuracy"], baseline_accuracy=pool["baseline"]["accuracy"], beats_baseline=beats, per_investigation=per,
                          statement=("When a whole NASA investigation was held out, the model " + ("did better" if beats else "did NOT do better") +
                                     f" than a constant guess (Brier {pool['model']['brier']:.2f} vs {pool['baseline']['brier']:.2f}, lower is better; "
                                     f"{pool['model']['n']} runs). " + ("" if beats else "Treat the probability as a rough, unproven indication.")))
    pct, lo, hi = round(pr["probability"] * 100), round(pr["lo"] * 100), round(pr["hi"] * 100)
    who = f"{group}" if group else "a material the model has no data for"
    informative = (pr["hi"] - pr["lo"]) <= INFORMATIVE_MAX_WIDTH
    where = (f" at {o2:g}% O2 and {flow:g} cm/s airflow" if flow is not None else f" at {o2:g}% O2, averaged over the tested airflows ({m.flow_range[0]:g}–{m.flow_range[1]:g} cm/s)")
    stmt = (f"Model estimate (not tested): {pct}% chance the flame keeps burning in microgravity (95% interval {lo}–{hi}%) for {who}{where}." if informative else
            f"Model estimate (not tested): too uncertain to call. The 95% interval for {who}{where} spans {lo}–{hi}% (central value {pct}%, which mostly reflects PMMA, the reference material).")
    caveats = [f"Trained on {m.n} labelled microgravity runs of real solids ({', '.join(f'{k} {v}' for k, v in m.by_investigation.items())}); "
               f"oxygen {m.o2_range[0]:g}–{m.o2_range[1]:g}%, airflow {m.flow_range[0]:g}–{m.flow_range[1]:g} cm/s. It does not predict outside these ranges.",
               "Some labels come from a rule applied to crew notes (89.5% right on 19 held-out runs), not from a human reading each note.",
               "Pressure, thickness and sample size are not model inputs."]
    if group is None:
        caveats.append("This material is not one the model has data for: the interval includes the full spread between materials seen in training, so it is wide.")
    if role == "cross_check":
        caveats.append("A tested record exists at these conditions. The tested record is the evidence; this estimate is only a cross-check.")
    return BurnPrediction(
        role=role, basis=basis, probability_sustained=round(pr["probability"], 3), interval_95=(round(pr["lo"], 3), round(pr["hi"], 3)), informative=informative,
        material_group=group, statement=stmt, inputs={"oxygen_pct": o2, "airflow_cm_s": flow, "pressure_kpa_not_used": pressure_kpa},
        airflow_assumption=None if flow is not None else f"No airflow given: averaged over the {len(m.flows)} airflows tested ({m.flow_range[0]:g}–{m.flow_range[1]:g} cm/s).",
        trained_on={"n_runs": m.n, "by_investigation": m.by_investigation, "by_material": m.by_material, "by_label_method": m.by_label_method,
                    "o2_range": list(m.o2_range), "flow_range_cm_s": list(m.flow_range), "dataset": "data/atlas_dataset.json (ai-engine branch, commit 43030de)",
                    "method": "Bayesian logistic regression, Laplace posterior"},
        validation=val, oxygen_odds_ratio_per_point=m.odds_ratio, caveats=caveats), None
