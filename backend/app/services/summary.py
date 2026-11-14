"""Optional LLM summary with a hard number guard (rule 1: "no quote, no number").

Flow: build a compact context from the already-retrieved result -> ask Claude to summarise it -> check the text:
  * every number must exist in the context (record fields, request values, tolerances, computed counts shown in verdict_reason);
  * spelled-out numbers are rejected; the verdict label must be stated; refusals / errors / timeouts are rejected.
Any failure -> keep the deterministic template summary (summary_source = "template"). With no ANTHROPIC_API_KEY nothing is called.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.models.api import AssessRequest, AssessResponse, Verdict

log = logging.getLogger("mission_lens.summary")

SYSTEM_PROMPT = """You write a short summary for a spacecraft fire-safety engineer from a JSON context of NASA microgravity combustion records.

Hard rules:
1. Use ONLY facts in the JSON context. Never add a number, percentage, count, date, unit, standard or identifier that is not in the context. Copy numbers exactly as written there. Write numbers as digits; never spell a number out in words.
2. Do not estimate, interpolate, extrapolate, convert units, or compare quantities the context does not compare. 1g MOC/ULOI (NASA-STD-6001 Test 1, upward) and LOI (downward) are different quantities: never treat them as equal.
3. State the verdict exactly as `verdict_label` and keep its meaning: "No direct evidence" means there are no tested records at these conditions; "Model estimate - not tested" must say it was not tested. Never say a material is safe or will behave a certain way without a record that shows it.
4. Records with display_kind "tested_at" show conditions only (no outcome); records with display_kind "smoke" are not burn evidence. Mention warnings and quality_flags that affect a value you cite.
5. Cite records by experiment_id. If something is not in the context, say "not available".
6. Plain text, no markdown, at most 120 words."""

_FORMULAS = re.compile(r"\b(?:CO2|O2|N2|H2O|CH4|CO)\b")
_IDENT = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b|\b10\.\d{4,9}/\S+")      # BASS-096, PSI-26, RG-05, NASA-STD-6001, DOI
_ONE_G = re.compile(r"\b1\s?g\b|\b0\s?g\b|µg", re.I)
_NUM = re.compile(r"\d+(?:\.\d+)?")
_WORDS = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|(?:thir|four|fif|six|seven|eight|nine)teen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
                    r"|hundred|thousand|million|dozen|half|double|triple|twice|thrice)\b", re.I)


def _strip(s: str) -> str:
    """Remove identifiers, chemical formulas and gravity labels so their digits neither whitelist nor trip the check."""
    s = _IDENT.sub(" ", s)
    s = _FORMULAS.sub(" ", s)
    return _ONE_G.sub(" ", s)


def numbers(s: str) -> set[float]:
    return {round(float(m), 6) for m in _NUM.findall(_strip(s).replace(",", ""))}


def check_text(text: str, context_json: str, resp: AssessResponse) -> str | None:
    """Return None if the text passes, else the reason it was rejected."""
    t = text.strip()
    if not t:
        return "empty LLM text"
    if len(t) > 1500:
        return "LLM text too long"
    ctx_low = context_json.lower()
    fake = [i for i in _IDENT.findall(t) if any(c.isdigit() for c in i) and i.lower().rstrip(".,;:)") not in ctx_low]
    if fake:
        return "identifier not in the retrieved records: " + ", ".join(fake)
    allowed = numbers(context_json)
    bad = sorted(n for n in numbers(t) if n not in allowed)
    if bad:
        return "number(s) not in the retrieved records: " + ", ".join(f"{b:g}" for b in bad)
    w = _WORDS.search(_strip(t))
    if w:
        return f"spelled-out number '{w.group(0)}'"
    low = t.lower().replace("—", "-")
    need = {Verdict.EVIDENCE: ["evidence"], Verdict.NO_DIRECT_EVIDENCE: ["no direct evidence"],
            Verdict.MODEL_ESTIMATE: ["model estimate", "not tested"]}[resp.verdict]
    if any(n not in low for n in need):
        return f"verdict label '{resp.verdict_label}' not stated"
    if resp.estimate and "not tested" not in low:
        return "estimate not labelled 'not tested'"
    return None


def _rec(r: Any) -> dict:
    d = r.model_dump() if hasattr(r, "model_dump") else r
    keys = ("experiment_id", "source_investigation", "gravity_bucket", "material_variant", "oxygen_pct", "oxygen_basis", "pressure_kpa", "airflow_cm_s",
            "outcome_variable", "outcome_value", "outcome_unit", "outcome_class", "uloi_pct", "display_kind", "display_text", "quality_flags", "source_ref")
    out = {k: d.get(k) for k in keys if d.get(k) not in (None, [], "")}
    if d.get("flame_behavior_notes"):
        out["flame_behavior_notes"] = d["flame_behavior_notes"][:400]
    return out


def build_context(resp: AssessResponse) -> dict[str, Any]:
    recs = [_rec(r) for g in resp.evidence_groups for r in g.records[:3]][:8]
    ctx: dict[str, Any] = {
        "verdict": resp.verdict.value, "verdict_label": resp.verdict_label, "verdict_reason": resp.verdict_reason,
        "material": resp.material.name_en if resp.material else "unknown material (not in the data)",
        "requested": {k: v for k, v in resp.requested.items() if v is not None and k in ("oxygen_pct", "pressure_kpa", "gravity", "airflow_cm_s", "question")},
        "tolerances": resp.matched_tolerances.text, "records": recs,
        "nearest_evidence": [{"gravity_bucket": n.gravity_bucket, "delta_o2_pct": n.delta_o2_pct, "delta_pressure_kpa": n.delta_pressure_kpa, **_rec(n.record)}
                             for n in resp.nearest_evidence[:4]],
        "warnings": resp.warnings[:6]}
    if resp.earth_vs_space and resp.earth_vs_space.available:
        e = resp.earth_vs_space
        ctx["earth_vs_space"] = {"comparison": e.comparison_text, "banner": e.banner, "one_g_not_conservative": e.one_g_not_conservative,
                                 "moc_values": e.baseline_1g.moc_values[:8] if e.baseline_1g else [], "note": e.baseline_1g.test_note if e.baseline_1g else None,
                                 "correction_model": e.correction_model_message}
    if resp.estimate:
        ctx["estimate"] = resp.estimate.model_dump(include={"label", "value", "unit", "error", "error_unit", "inputs", "equation", "citation"})
    if resp.findings:
        ctx["researchers_guide_findings"] = [{"id": f.id, "claim": f.claim, "page": f.page} for f in resp.findings[:3]]
    return ctx


def get_client():
    import anthropic
    s = get_settings()
    return anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_s, max_retries=1)


def generate(context_json: str, question: str | None) -> str:
    """One Claude call. Raises on refusal or API errors (caller falls back to the template)."""
    s = get_settings()
    user = f"Context (JSON):\n{context_json}\n\nEngineer's question: {question or '(none)'}\n\nWrite the summary."
    # Claude Opus 5.5: thinking is always on (parameter omitted); no sampling params; effort is the depth control;
    # server-side refusal fallback opted in by default.
    r = get_client().beta.messages.create(
        model=s.llm_model, max_tokens=s.llm_max_tokens, system=SYSTEM_PROMPT, output_config={"effort": s.llm_effort},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default", messages=[{"role": "user", "content": user}])
    if r.stop_reason == "refusal":
        raise RuntimeError("model declined (stop_reason=refusal)")
    if r.stop_reason == "max_tokens":
        raise RuntimeError("output cut off (max_tokens)")
    return "".join(b.text for b in r.content if b.type == "text")


def finalize(resp: AssessResponse, req: AssessRequest) -> AssessResponse:
    """Replace the template summary with a checked LLM summary when possible. Never raises."""
    s = get_settings()
    if not (s.anthropic_api_key and req.use_llm) or s.mock:
        return resp
    try:
        ctx = json.dumps(build_context(resp), ensure_ascii=False, default=str)
        text = generate(ctx, req.question)
        reason = check_text(text, ctx, resp)
        if reason is None:
            return resp.model_copy(update={"summary_text": text.strip(), "summary_source": "llm_checked", "summary_fallback_reason": None})
        log.warning("LLM summary rejected: %s", reason)
    except Exception as e:  # noqa: BLE001  (network, auth, refusal, timeout...)
        reason = f"LLM unavailable: {type(e).__name__}: {str(e)[:120]}"
        log.warning(reason)
    return resp.model_copy(update={"summary_source": "template", "summary_fallback_reason": reason})
