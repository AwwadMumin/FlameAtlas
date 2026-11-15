"""Frontend adapter endpoints: experiment list, COMPARE agent, ASK agent.

Both agents follow the project rules: facts come from records only ("no quote, no number"); the comparability rules are deterministic code,
the optional LLM only phrases the summary and its text is checked number-by-number (summary.check_free), falling back to the template.
Nothing is converted or interpolated: records measured in different quantities or units are reported as NOT comparable.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import api as M
from app.services import evidence as ev, store, summary
from app.services.earth_to_space import procedure
from app.services.records import display_kind, gravity_bucket, source_url, to_record

log = logging.getLogger("mission_lens.research")
_YEAR = re.compile(r"\b(19[6-9]\d|20[0-4]\d)\b")
_MOON_MARS = re.compile(r"\b(moon|lunar|mars|martian)\b", re.I)

METHODOLOGY = ("Deterministic rules over NASA records. A pair is comparable only if both are burn-relevant (not smoke/detection), have a recorded outcome, "
               "are the same material and report the SAME outcome variable in the SAME unit as printed (no conversion; LOI downward and MOC/ULOI upward are never mixed). "
               "Differences in gravity, O2 (beyond the configured tolerance), pressure, airflow, test procedure, material variant or source campaign are listed as limitations. "
               "Nothing is interpolated or inferred; missing values are reported as 'not stated'.")


# ---------------------------------------------------------------- list
def _year(e: dict) -> int | None:
    x = e.get("extra") or {}
    for k in ("Date", "date", "Test date", "Year", "year"):
        m = _YEAR.search(str(x.get(k) or ""))
        if m:
            return int(m.group(1))
    return None


def _item(e: dict) -> M.ExperimentListItem:
    mat = store.materials().get(e.get("material_id") or "")
    name = mat["name_en"] if mat else e.get("fuel_material")
    rec = to_record(e)
    cond = []
    if e.get("oxygen_pct") is not None:
        cond.append(f"{e['oxygen_pct']}% O2")
    if e.get("pressure_kpa") is not None:
        cond.append(f"{e['pressure_kpa']} kPa")
    return M.ExperimentListItem(
        id=e["experiment_id"], program=e.get("source_investigation"), title=f"{name or 'material not named'} — {e.get('source_investigation') or 'source not named'} ({e['experiment_id']})",
        material=name, material_id=e.get("material_id"), gravity="Microgravity" if gravity_bucket(e["gravity_level"]) == "microgravity" else "Earth gravity (1g)",
        oxygen=None if e.get("oxygen_pct") is None else f"{e['oxygen_pct']}%", airflow=None if e.get("airflow_cm_s") is None else f"{e['airflow_cm_s']} cm/s",
        year=_year(e), summary=rec.display_text, source_id=e["experiment_id"], source_url=source_url(e), evidence_type=e.get("evidence_type"), display_kind=display_kind(e),
        quality_flags=e.get("quality_flags") or [], flammability_relevant=e.get("flammability_relevant") is not False)


def list_experiments(material: str | None, gravity: str | None, q: str | None, include_smoke: bool, limit: int, offset: int) -> M.ExperimentListResponse:
    f: dict[str, Any] = {}
    if material:
        f["material_id"] = material
    if gravity:
        b = ev.GRAVITY_BUCKET.get(gravity)
        if b is None:
            return M.ExperimentListResponse(experiments=[], total=0, returned=0)
        f["gravity_level"] = "microgravity" if b == "microgravity" else {"$ne": "microgravity"}
    if not include_smoke:
        f["flammability_relevant"] = True
    if q:
        f["$or"] = [{k: {"$regex": re.escape(q), "$options": "i"}} for k in ("experiment_id", "fuel_material", "source_investigation", "material_id")]
    c = store.get_db().experiments
    total = c.count_documents(f)
    rows = list(c.find(f, {"_id": 0}).sort("experiment_id", 1).skip(offset).limit(limit))
    items = [_item(e) for e in rows]
    return M.ExperimentListResponse(experiments=items, total=total, returned=len(items))


# ---------------------------------------------------------------- compare
def _fetch(ids: list[str]) -> list[dict]:
    if len(set(ids)) != len(ids):
        raise ApiError(422, "validation_error", "experiment_ids must be distinct", {"experiment_ids": ids})
    got = {e["experiment_id"]: e for e in store.get_db().experiments.find({"experiment_id": {"$in": ids}}, {"_id": 0})}
    missing = [i for i in ids if i not in got]
    if missing:
        raise ApiError(404, "not_found", f"Unknown experiment_id(s): {', '.join(missing)}", {"experiment_ids": missing})
    return [got[i] for i in ids]


def _quantity(e: dict) -> str:
    return f"{e.get('outcome_variable')} [{e.get('outcome_unit') or 'no unit'}]"


def _hard_block(ref: dict, e: dict) -> str | None:
    """Reason the pair cannot be compared on one quantity, or None."""
    for r in (ref, e):
        if r.get("flammability_relevant") is False:
            return f"{r['experiment_id']} is a smoke/detection record, not burn evidence"
    for r in (ref, e):
        if r.get("outcome_type") == "conditions_only":
            return f"{r['experiment_id']} only records the test conditions ('tested at'); the source reports no outcome"
    if ref.get("material_id") != e.get("material_id"):
        return f"different materials ({ref.get('material_id') or 'not named'} vs {e.get('material_id') or 'not named'})"
    va, vb = ref.get("outcome_variable"), e.get("outcome_variable")
    if not va or not vb:
        return "at least one record has no measured quantity (only verbatim notes or a class)"
    if va != vb:
        loi = {"LOI"}
        up = {"MOC", "ULOI"}
        if (va in loi and vb in up) or (vb in loi and va in up):
            return f"{va} (downward, ASTM D2863) and {vb} (upward, NASA-STD-6001 Test 1) are different quantities and are never mixed"
        return f"different quantities ({va} vs {vb})"
    if (ref.get("outcome_unit") or "") != (e.get("outcome_unit") or ""):
        return f"{va} is printed in different units ('{ref.get('outcome_unit')}' vs '{e.get('outcome_unit')}'); no conversion is done"
    for r in (ref, e):
        if r.get("outcome_value") is None and not r.get("outcome_class"):
            return f"{r['experiment_id']} has no value for {va}"
    return None


def _differences(ref: dict, e: dict) -> list[tuple[str, str, str]]:
    """(key, category, text). Numbers shown are record values; deltas are computed from the two shown values."""
    s = get_settings()
    out: list[tuple[str, str, str]] = []
    gb = (gravity_bucket(ref["gravity_level"]), gravity_bucket(e["gravity_level"]))
    if gb[0] != gb[1]:
        out.append(("gravity", "experimental_conditions", f"gravity differs: {ref['experiment_id']} is {gb[0]}, {e['experiment_id']} is {gb[1]} (hardware and flow set-ups also differ between µg and 1g tests)"))
    a, b = ev.o2_coord(ref), ev.o2_coord(e)
    if a is None or b is None:
        out.append(("o2", "data_coverage", "O2 not stated for " + " and ".join(r["experiment_id"] for r, v in ((ref, a), (e, b)) if v is None)))
    elif abs(a - b) > s.tol_o2_pct:
        out.append(("o2", "experimental_conditions", f"O2 differs by {abs(a - b):.1f}% ({a}% vs {b}%), outside the ±{s.tol_o2_pct:g}% tolerance"))
    pa, pb = ref.get("pressure_kpa"), e.get("pressure_kpa")
    if pa is None or pb is None:
        out.append(("pressure", "data_coverage", "pressure not stated for " + " and ".join(r["experiment_id"] for r, v in ((ref, pa), (e, pb)) if v is None)))
    elif abs(pa - pb) > s.tol_pressure_kpa:
        out.append(("pressure", "experimental_conditions", f"pressure differs by {abs(pa - pb):.1f} kPa ({pa} vs {pb} kPa), outside the ±{s.tol_pressure_kpa:g} kPa tolerance"))
    fa, fb = ref.get("airflow_cm_s"), e.get("airflow_cm_s")
    if fa is None or fb is None:
        out.append(("airflow", "data_coverage", "airflow not stated for " + " and ".join(r["experiment_id"] for r, v in ((ref, fa), (e, fb)) if v is None)))
    elif fa != fb:
        out.append(("airflow", "experimental_conditions", f"airflow differs ({fa} vs {fb} cm/s)"))
    if ref.get("evidence_type") == "flammability_limit_1g_MOC_ULOI" and e.get("evidence_type") == "flammability_limit_1g_MOC_ULOI":
        pr, pe = procedure(ref), procedure(e)
        if pr != pe or pr == "not_stated":
            out.append(("procedure", "methodology", f"1g test procedure: {ref['experiment_id']} is {pr}, {e['experiment_id']} is {pe} (configuration changes the measured limit; Hirsch et al. 2011)"))
    if ref.get("material_variant") != e.get("material_variant"):
        out.append(("variant", "experimental_conditions", f"material variant differs ('{ref.get('material_variant')}' vs '{e.get('material_variant')}')"))
    if ref.get("source_investigation") != e.get("source_investigation"):
        out.append(("source", "methodology", f"different source campaigns ({ref.get('source_investigation')} vs {e.get('source_investigation')}); hardware and protocol may differ"))
    return out


def _value_text(e: dict) -> str:
    if e.get("outcome_value") is not None:
        return f"{e.get('outcome_variable')} = {e['outcome_value']} {e.get('outcome_unit') or ''}".strip()
    return f"{e.get('outcome_variable')}: class {e.get('outcome_class')}"


def compare(req: M.CompareRequest) -> M.ComparisonResponse:
    recs = _fetch(req.experiment_ids)
    ref, others = recs[0], recs[1:]
    items = [M.CompareItem(experiment_id=ref["experiment_id"], comparable=True, reason="Reference record: " + (_value_text(ref) if ref.get("outcome_variable") else "no measured quantity"))]
    lims: dict[str, M.ScientificLimitation] = {}
    for e in others:
        block = _hard_block(ref, e)
        diffs = _differences(ref, e) if block is None else []
        if block:
            items.append(M.CompareItem(experiment_id=e["experiment_id"], comparable=False, reason=block + ".", differences=[d[2] for d in diffs]))
            continue
        why = f"Same quantity ({_quantity(ref)}): {_value_text(ref)} vs {_value_text(e)}."
        items.append(M.CompareItem(experiment_id=e["experiment_id"], comparable=True, reason=why, differences=[d[2] for d in diffs]))
        for key, cat, text in diffs:
            L = lims.setdefault(key, M.ScientificLimitation(id=f"LIM-{key}", category=cat, severity="caution" if cat in ("experimental_conditions", "methodology") else "info",
                                                            title={"gravity": "Different gravity", "o2": "Different O2", "pressure": "Different pressure", "airflow": "Different airflow",
                                                                   "procedure": "Different test procedure", "variant": "Different material variant", "source": "Different source campaign"}[key],
                                                            description="", affected_experiment_ids=[]))
            L.description = (L.description + " " if L.description else "") + f"{e['experiment_id']} vs {ref['experiment_id']}: " + text + "."
            L.affected_experiment_ids = sorted(set(L.affected_experiment_ids) | {e["experiment_id"]})
    for e in recs:
        if e.get("quality_flags"):
            lims[f"q-{e['experiment_id']}"] = M.ScientificLimitation(
                id=f"LIM-flags-{e['experiment_id']}", category="measurement_uncertainty", severity="caution", title=f"Data-quality flags on {e['experiment_id']}",
                description="; ".join(e["quality_flags"]) + ".", affected_experiment_ids=[e["experiment_id"]], source_ids=[e["experiment_id"]], source_urls=[u for u in [source_url(e)] if u])
    if any(gravity_bucket(r["gravity_level"]) != gravity_bucket(ref["gravity_level"]) for r in recs):
        lims["interp"] = M.ScientificLimitation(id="LIM-interpretation", category="interpretation", severity="info", title="Data cover only microgravity and 1g",
                                                description="No record covers Moon or Mars gravity; nothing here can be read as an estimate for those.", affected_experiment_ids=[r["experiment_id"] for r in recs])
    for L in lims.values():
        L.source_ids = L.source_ids or L.affected_experiment_ids
        L.source_urls = L.source_urls or [u for u in (source_url(r) for r in recs if r["experiment_id"] in L.source_ids) if u]
    sources = [M.SourceRef(source_id=r["experiment_id"], title=r.get("source_ref") or r["experiment_id"], url=source_url(r)) for r in recs]
    n_ok = sum(1 for i in items[1:] if i.comparable)
    tmpl = _compare_template(ref, items, len(others), n_ok)
    text, src, reason = tmpl, "template", None
    if summary.llm_available(req.use_llm):
        ctx = json.dumps({"reference": ref["experiment_id"], "counts": {"compared": len(others), "comparable": n_ok},
                          "records": [summary._rec(r) for r in recs], "items": [i.model_dump() for i in items],
                          "limitations": [{"id": L.id, "title": L.title, "description": L.description} for L in lims.values()]}, ensure_ascii=False, default=str)
        try:
            out = summary.complete(COMPARE_PROMPT, f"Context (JSON):\n{ctx}\n\nWrite the comparison summary.")
            reason = summary.check_free(out, ctx)
            if reason is None:
                text, src = out.strip(), "llm_checked"
            else:
                log.warning("LLM compare summary rejected: %s", reason)
        except Exception as ex:  # noqa: BLE001
            reason = f"LLM unavailable: {type(ex).__name__}: {str(ex)[:120]}"
            log.warning(reason)
    return M.ComparisonResponse(summary=text, reference_id=ref["experiment_id"], items=items, limitations=list(lims.values()), methodology=METHODOLOGY, sources=sources,
                                generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), summary_source=src, summary_fallback_reason=reason)


def _compare_template(ref: dict, items: list[M.CompareItem], n: int, n_ok: int) -> str:
    head = f"Reference {ref['experiment_id']}: " + (_value_text(ref) if ref.get("outcome_variable") else "no measured quantity recorded") + "."
    body = f" {n_ok} of {n} other record(s) report the same quantity and can be compared; see the listed differences before reading them side by side."
    bad = [f"{i.experiment_id} ({i.reason.rstrip('.')})" for i in items[1:] if not i.comparable]
    return head + body + (" Not comparable: " + "; ".join(bad) + "." if bad else "")


COMPARE_PROMPT = """You write a short comparison note for a spacecraft fire-safety engineer from a JSON context of NASA microgravity combustion records and pre-computed comparability results.
Hard rules: use ONLY facts in the context; copy numbers exactly; write numbers as digits; never convert units, estimate, interpolate, or call two records comparable when `items` says they are not.
Mention the limitations that matter. Cite records by experiment_id. 1g MOC/ULOI (upward) and LOI (downward) are different quantities. Never call a value the lowest, highest, minimum, maximum, always or never unless the context says so. Plain text, at most 110 words."""


# ---------------------------------------------------------------- ask
ASK_PROMPT = """You answer a spacecraft fire-safety engineer's question from a JSON context of retrieved NASA microgravity combustion records.
Hard rules: use ONLY facts in the context; copy numbers exactly as written; write numbers as digits; never estimate, interpolate, or convert units. Data exist only for microgravity and 1g.
Records with display_kind "tested_at" show conditions only (no outcome); "smoke" records are not burn evidence. If the context does not answer the question, say "not available in the retrieved records".
Cite records by experiment_id. You only see a few retrieved records, not the whole database: never call a value the lowest, highest, minimum, maximum, only, always, never or safe unless the context says so; say "in the retrieved records". Plain text, at most 120 words."""


_O2 = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)", re.I)
_UG = re.compile(r"micro-?gravity|\bµg\b|\bug\b|\borbit|\bspace\b|\bISS\b|weightless|freefall|free fall", re.I)
_1G = re.compile(r"\bearth\b|\b1\s?g\b|\bground\b|normal gravity", re.I)


def parse_question(q: str) -> dict[str, Any]:
    """Conditions mentioned in the question (used only to filter / rank retrieved records; never to fill in values)."""
    from app.services import materials
    nq = materials.norm(q)
    hit = [(len(n), mid) for n, mid in materials._exact_index().items() if len(n) >= 3 and re.search(rf"\b{re.escape(n)}\b", nq)]
    o2 = _O2.search(q)
    g = "microgravity" if _UG.search(q) and not _1G.search(q) else "1g" if _1G.search(q) and not _UG.search(q) else None
    return {"material_id": max(hit)[1] if hit else None, "oxygen_pct": float(o2.group(1)) if o2 else None, "gravity": g}


def _retrieve(question: str, ids: list[str]) -> tuple[list[dict], dict[str, Any]]:
    if ids:
        return _fetch(ids), {}
    s = get_settings()
    from app.services.embeddings import embed
    cond = parse_question(question)
    flt: dict[str, Any] = {"flammability_relevant": True}
    if cond["material_id"]:
        flt["material_id"] = cond["material_id"]
    res = list(store.get_db().evidence_cards.aggregate([{"$vectorSearch": {
        "index": "evidence_vector", "path": "embedding", "queryVector": embed([question])[0], "numCandidates": 200, "limit": 40, "filter": flt}},
        {"$project": {"experiment_id": 1, "score": {"$meta": "vectorSearchScore"}}}]))
    score = {r["experiment_id"]: float(r["score"]) for r in res if r["score"] >= s.ask_similarity_threshold}
    by = {e["experiment_id"]: e for e in store.get_db().experiments.find({"experiment_id": {"$in": list(score)}}, {"_id": 0})}
    rows = [by[i] for i in score if i in by]
    if cond["gravity"]:
        rows = [e for e in rows if gravity_bucket(e["gravity_level"]) == cond["gravity"]]
    if cond["oxygen_pct"] is not None:   # prefer records whose O2 is closest to the one asked about; records without O2 rank last
        rows.sort(key=lambda e: (not ev.has_outcome(e), ev.o2_coord(e) is None, abs((ev.o2_coord(e) or 0) - cond["oxygen_pct"]), -score[e["experiment_id"]]))
    else:
        rows.sort(key=lambda e: (not ev.has_outcome(e), -score[e["experiment_id"]]))   # records with an outcome first
    return rows[:6], cond


def ask(req: M.AskRequest) -> M.AskResponse:
    rows, cond = _retrieve(req.question, req.experiment_ids)
    recs = [to_record(e) for e in rows]
    cites = [M.SourceRef(source_id=e["experiment_id"], title=e.get("source_ref") or e["experiment_id"], url=source_url(e)) for e in rows]
    notes: list[str] = []
    if _MOON_MARS.search(req.question):
        notes.append("No record covers Moon or Mars gravity; data exist only for microgravity and 1g, so nothing below is a Moon or Mars result.")
    if any(r.display_kind == "tested_at" for r in recs):
        notes.append("Records marked 'tested at' show conditions only; the source reports no outcome.")
    flags = sorted({f for e in rows for f in (e.get("quality_flags") or [])})
    if flags:
        notes.append("Data-quality flags: " + "; ".join(f.rstrip(".") for f in flags) + ".")
    if not rows:
        return M.AskResponse(answer="No direct evidence: no record in the database is close enough to this question. Nothing is inferred.", limitations=" ".join(notes) or None,
                             citations=[], records=[])
    lines = [f"- {r.experiment_id}: {r.display_text}" for r in recs]
    used = [f"material {cond['material_id']}" if cond.get("material_id") else None, f"{cond['gravity']} only" if cond.get("gravity") else None,
            f"closest to {cond['oxygen_pct']}% O2" if cond.get("oxygen_pct") is not None else None]
    used = [u for u in used if u]
    lead = "No direct evidence for Moon or Mars gravity. " if _MOON_MARS.search(req.question) else ""
    tmpl = (lead + f"{len(recs)} record(s) matched your question" + (f" ({'; '.join(used)})" if used else "") + " (retrieval only, not a prediction):\n" + "\n".join(lines))
    text, src, reason = tmpl, "template", None
    if summary.llm_available(req.use_llm):
        ctx = json.dumps({"question": req.question, "counts": {"records": len(recs)}, "records": [summary._rec(r) for r in recs]}, ensure_ascii=False, default=str)
        try:
            out = summary.complete(ASK_PROMPT, f"Context (JSON):\n{ctx}\n\nWrite the answer.")
            reason = summary.check_free(out, ctx)
            if reason is None and out.strip().lower().startswith("not available") and len(out.strip()) < 80:
                reason = "the AI found nothing to add to the retrieved records (record list shown instead)"
            if reason is None:
                text, src = out.strip(), "llm_checked"
            else:
                log.warning("LLM answer rejected: %s", reason)
        except Exception as ex:  # noqa: BLE001
            reason = f"LLM unavailable: {type(ex).__name__}: {str(ex)[:120]}"
            log.warning(reason)
    return M.AskResponse(answer=text, limitations=" ".join(notes) or None, citations=cites, records=recs, answer_source=src, answer_fallback_reason=reason)
