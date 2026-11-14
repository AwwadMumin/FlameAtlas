"""Coverage grid per material + "suggested test" recommender (5.6). Suggested tests are never results."""
from __future__ import annotations

import math

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.api import CoverageResponse, NextExperiment, NextExperimentsResponse
from app.services import evidence as ev, store
from app.services.assess import PSI_TO_KPA, _presets
from app.services.records import gravity_bucket

BUCKETS = ("microgravity", "1g")


def pressure_labels() -> list[str]:
    e = get_settings().pressure_bin_edges_kpa
    return [f"<{e[0]:g}"] + [f"{a:g}-{b:g}" for a, b in zip(e, e[1:])] + [f">{e[-1]:g}", "not stated"]


def pressure_bin(p: float | None) -> int:
    """<60 | 60<=p<80 | 80<=p<=95 | >95 | not stated"""
    e = get_settings().pressure_bin_edges_kpa
    if p is None:
        return 4
    if p < e[0]:
        return 0
    if p < e[1]:
        return 1
    return 2 if p <= e[2] else 3


def _presets_kpa() -> list[dict]:
    return [{**p, "pressure_kpa": round(p["pressure_psia"] * PSI_TO_KPA, 2)} for p in _presets().values()]


def _cells(rows: list[dict]):
    for e in rows:
        c = ev.o2_coord(e)
        if c is None:
            continue
        yield e, math.floor(c), pressure_bin(e.get("pressure_kpa")), ev.has_outcome(e)


def coverage(material_id: str) -> CoverageResponse:
    if material_id not in store.materials():
        raise ApiError(404, "not_found", f"Unknown material_id '{material_id}'", {"material_id": material_id})
    rows = ev.material_rows(material_id)
    pres = _presets_kpa()
    coords = [math.floor(ev.o2_coord(e)) for e in rows if ev.o2_coord(e) is not None] + [math.floor(p["o2_pct"]) for p in pres]
    lo, hi = min(coords), max(coords)
    axis = [float(x) for x in range(lo, hi + 1)]
    grids = {b: [[{"outcomes": 0, "conditions_only": 0} for _ in axis] for _ in pressure_labels()] for b in BUCKETS}
    for e, o2b, pb, outc in _cells(rows):
        grids[gravity_bucket(e["gravity_level"])][pb][o2b - lo]["outcomes" if outc else "conditions_only"] += 1
    overlays = [{"preset_id": p["id"], "name": p["name"], "o2_pct": p["o2_pct"], "pressure_kpa": p["pressure_kpa"], "preset_gravity": p["gravity"],
                 "o2_index": math.floor(p["o2_pct"]) - lo, "pressure_index": pressure_bin(p["pressure_kpa"]),
                 "cells": {b: grids[b][pressure_bin(p["pressure_kpa"])][math.floor(p["o2_pct"]) - lo] for b in BUCKETS}} for p in pres]
    return CoverageResponse(material_id=material_id, o2_axis=axis, pressure_axis=pressure_labels(), grids=grids, preset_overlays=overlays,
                            empty_state_message=None if rows else "No flammability records for this material; every cell is empty.")


def _solid_materials() -> list[str]:
    words = get_settings().gap_excluded_kind_words
    return [mid for mid, m in store.materials().items() if not any(w in (m.get("kind") or "").lower() for w in words)]


def next_experiments(preset: str | None = None, limit: int = 10) -> NextExperimentsResponse:
    s = get_settings()
    P = _presets_kpa()
    if preset:
        P = [p for p in P if p["id"] == preset]
        if not P:
            raise ApiError(422, "validation_error", f"Unknown preset '{preset}'", {"allowed": list(_presets())})
    mats = _solid_materials()
    rows = {m: ev.material_rows(m) for m in mats}
    cnt: dict[str, dict[tuple[int, int, str], list[int]]] = {}   # material -> (o2bin, pbin, bucket) -> [outcomes, conditions_only]
    for m, rs in rows.items():
        d = cnt.setdefault(m, {})
        for e, o2b, pb, outc in _cells(rs):
            d.setdefault((o2b, pb, gravity_bucket(e["gravity_level"])), [0, 0])[0 if outc else 1] += 1

    def empty_ug(m, o2b, pb):
        return cnt[m].get((o2b, pb, "microgravity"), [0, 0])[0] == 0

    best: dict[tuple, NextExperiment] = {}
    for p in P:
        pb, p_o2b = pressure_bin(p["pressure_kpa"]), math.floor(p["o2_pct"])
        for dk in range(-s.gap_o2_bins_around_preset, s.gap_o2_bins_around_preset + 1):
            o2b = p_o2b + dk
            if o2b < 0:
                continue
            n_empty = sum(empty_ug(m, o2b, pb) for m in mats)
            for m in mats:
                if not empty_ug(m, o2b, pb):
                    continue
                a = 1.0 / (1 + abs(dk))
                b = n_empty / len(mats)
                has1g_cell = cnt[m].get((o2b, pb, "1g"), [0, 0])[0] > 0
                no_ug_at_all = not any(k[2] == "microgravity" and v[0] > 0 for k, v in cnt[m].items())
                has_1g_any = any(k[2] == "1g" and v[0] > 0 for k, v in cnt[m].items())
                c = 1.0 if has1g_cell else (0.5 if (no_ug_at_all and has_1g_any) else 0.0)
                score = s.gap_w_closeness * a + s.gap_w_materials * b + s.gap_w_1g_only * c
                o2 = p["o2_pct"] if dk == 0 else o2b + 0.5
                pr = [e for e in rows[m] if ev.has_outcome(e) and ev.o2_coord(e) is not None and abs(math.floor(ev.o2_coord(e)) - o2b) <= 2
                      and pressure_bin(e.get("pressure_kpa")) in (pb, 4)]
                pr = sorted(pr, key=lambda e: ev.distance(e, o2, p["pressure_kpa"], None))[:5]
                cond_only = cnt[m].get((o2b, pb, "microgravity"), [0, 0])[1]
                unk = cnt[m].get((o2b, 4, "microgravity"), [0, 0])[0]
                why = (f"No microgravity outcome is recorded for {store.materials()[m]['name_en']} in the {o2b}-{o2b + 1}% O2 / {pressure_labels()[pb]} kPa cell, "
                       f"{abs(dk)} O2 bin(s) from the {p['name']} atmosphere ({p['o2_pct']}% O2, {p['pressure_kpa']} kPa). "
                       f"{n_empty} of {len(mats)} solid materials are also untested in this cell, so one chamber setting would cover them."
                       + (" 1g outcomes exist in this very cell." if has1g_cell else " Material has 1g evidence but no microgravity evidence." if c == 0.5 else "")
                       + (f" {cond_only} 'tested at' row(s) here have no recorded outcome." if cond_only else "")
                       + (f" {unk} microgravity outcome row(s) at this O2 level do not state a pressure, so they cannot fill a pressure cell." if unk else "")
                       + (f" Bordering evidence: {', '.join(e['experiment_id'] for e in pr)}." if pr else " No bordering evidence for this material."))
                key = (m, o2b, pb)
                cand = NextExperiment(rank=0, material_id=m, o2_pct=round(o2, 2), pressure_kpa=p["pressure_kpa"], gravity="microgravity", preset_id=p["id"], why=why,
                                      score_parts={"closeness_to_preset": round(a, 3), "materials_affected": round(b, 3), "one_g_exists_ug_not": c, "score": round(score, 4)},
                                      bordering_evidence=[e["experiment_id"] for e in pr])
                if key not in best or cand.score_parts["score"] > best[key].score_parts["score"]:
                    best[key] = cand
    ranked = sorted(best.values(), key=lambda x: (-x.score_parts["score"], x.material_id, x.o2_pct))[:limit]
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return NextExperimentsResponse(preset=preset, suggestions=ranked, empty_state_message=None if ranked else "Every candidate cell already has microgravity outcomes.")
