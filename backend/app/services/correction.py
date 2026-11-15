"""Pluggable ΔO2 correction models (FLARE-style). Coefficients come ONLY from correction_models.yaml (entered by the team)."""
from __future__ import annotations

import ast
import json
import math
import operator as op
from dataclasses import dataclass, field
from typing import Any

import yaml

from app.core.config import get_settings

NOT_CONFIGURED_MSG = "Correction model not configured"
_BIN = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow}
_FUN = {"log": math.log, "ln": math.log, "log10": math.log10, "exp": math.exp, "sqrt": math.sqrt}
REQUIRED = ("citation", "page", "equation", "formula", "inputs", "coefficients", "valid_range")


@dataclass
class CorrectionResult:
    status: str                      # not_configured | configured
    applicable: bool = False         # configured, inputs present AND inside valid_range
    message: str | None = None
    value: float | None = None
    unit: str = "% O2"
    error: float | None = None
    error_unit: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] | None = None


def load_model() -> dict | None:
    cfg = yaml.safe_load(get_settings().correction_models_path.read_text(encoding="utf-8")) or {}
    for m in cfg.get("models", []):
        if m.get("status") == "configured":
            return m
    return None


def status() -> tuple[str, str | None]:
    m = load_model()
    if m is None:
        return "not_configured", NOT_CONFIGURED_MSG
    missing = [k for k in REQUIRED if not m.get(k)]
    if missing:
        return "not_configured", f"{NOT_CONFIGURED_MSG} (incomplete: missing {', '.join(missing)})"
    return "configured", None


def _eval(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return float(env[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, env)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUN and len(node.args) == 1:
        return _FUN[node.func.id](_eval(node.args[0], env))
    raise ValueError("unsupported expression in correction formula")


def measured_error() -> tuple[float | None, str | None]:
    """Leave-one-out MAE from the stored validation result (database `derived_docs`, written by build_validation). None until measured."""
    try:
        from app.services import store
        doc = store.get_db()[get_settings().derived_collection].find_one({"_id": "validation"})
        cm = (doc or {}).get("data", {}).get("correction_model", {})
        return cm.get("mae_pct_o2"), "% O2 (leave-one-out MAE)"
    except Exception:  # noqa: BLE001
        return None, None


def estimate(inputs: dict[str, float | None], require_error: bool = True) -> CorrectionResult:
    st, msg = status()
    if st != "configured":
        return CorrectionResult(status=st, message=msg)
    m = load_model()
    need = list(m["inputs"])
    given = {k: inputs.get(k) for k in need}
    meta = {"id": m.get("id"), "citation": m["citation"], "page": str(m["page"]), "equation": m["equation"]}
    missing = [k for k, v in given.items() if v is None]
    if missing:
        return CorrectionResult("configured", False, f"Correction model needs {', '.join(missing)}, which is not available here.", inputs=given, model=meta)
    for k, v in given.items():
        lo_hi = (m["valid_range"] or {}).get(k)
        if lo_hi is None or not (lo_hi[0] <= v <= lo_hi[1]):
            return CorrectionResult("configured", False, f"Input {k}={v} is outside the model's valid range {lo_hi}.", inputs=given, model=meta)
    try:
        val = _eval(ast.parse(m["formula"], mode="eval"), {**m["coefficients"], **given})
    except Exception as e:  # noqa: BLE001
        return CorrectionResult("configured", False, f"Correction formula could not be evaluated: {e}", inputs=given, model=meta)
    err, err_unit = measured_error() if require_error else (None, None)
    if require_error and err is None:
        return CorrectionResult("configured", False, "Model configured but its error has not been measured yet (run build_validation); not shown as an estimate.",
                                inputs=given, model=meta)
    return CorrectionResult("configured", True, None, round(val, 2), error=err, error_unit=err_unit, inputs=given, model=meta)
