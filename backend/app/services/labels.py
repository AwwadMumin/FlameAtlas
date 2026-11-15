"""Human outcome labels for BASS crew notes -> MongoDB collection `outcome_labels` (one document per experiment_id).

Keyword rules only PRE-SUGGEST a label (status 'suggested', computed on the fly, never saved as a decision).
Only a human POST / CSV import writes a record, and it is stored as 'confirmed'. Input files are never touched.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, get_args

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.api import LabelIn, LabelOut, LabelQueueItem, LabelQueueResponse, OutcomeLabel
from app.services import store

LABELS = set(get_args(OutcomeLabel))

# priority order: first matching rule wins. These are hints for the human, not decisions.
RULES: list[tuple[str, str, re.Pattern]] = [
    ("no_ignition", "no_ignition: 'did not / failed to ignite'",
     re.compile(r"(did not|didn't|failed to|fail to|wouldn't|would not|no) ignit|ignition fail|failed ignition|did not light|never ignit", re.I)),
    ("hardware_issue", "hardware_issue: igniter / video / lens problem",
     re.compile(r"igniter (broke|broken|failed|didn't work|did not work|burned out|stopped)|broke igniter|lost video|lens cap|hardware (issue|problem|failure)", re.I)),
    ("extinguished_by_flow_or_N2", "extinguished_by_flow_or_N2: N2 / fan / flow ended the flame",
     re.compile(r"n2 (on|did not|didn't)|extinguish\w* (by|with|when) (n2|nitrogen|fan|flow)|went out when (the )?(fan|flow|air)|(turned|turn) (off|down) (the )?(air|flow|fan)|flow (off|stopped)|only extinguishes when", re.I)),
    ("brief_then_self_extinguished", "brief_then_self_extinguished: 'extinguished by itself'",
     re.compile(r"self[- ]extinguish|extinguished (by itself|itself|on its own)|went out (by itself|on its own)|went out when igniter", re.I)),
    ("sustained_burn", "sustained_burn: steady / sustained spread or long burn",
     re.compile(r"steady(ly)? (spread|burn)|steady spreading|sustained|spread (all the way|downstream|upstream)|\b\d+\s*(s|sec|seconds?|min|minutes?) (total )?burn|burn(ed)? (for|until)|reach a steady", re.I)),
]


def _coll():
    return store.get_db()[get_settings().labels_collection]


def load_all() -> list[dict]:
    return list(_coll().find({}, {"_id": 0}).sort("experiment_id", 1))


def confirmed() -> dict[str, dict]:
    """experiment_id -> label record. Only human-confirmed labels; suggestions never count."""
    return {l["experiment_id"]: l for l in load_all() if l.get("status") == "confirmed"}


def suggest(notes: str | None) -> tuple[str | None, str | None, str | None]:
    """(label, rule description, quote) — the quote is the verbatim sentence around the match."""
    if not notes:
        return None, None, None
    for label, desc, pat in RULES:
        m = pat.search(notes)
        if m:
            a = max(notes.rfind(".", 0, m.start()), notes.rfind("\n", 0, m.start())) + 1
            ends = [i for i in (notes.find(".", m.end()), notes.find("\n", m.end())) if i != -1]
            b = min(ends) + 1 if ends else len(notes)
            return label, desc, notes[a:b].strip()
    return None, None, None


def labelable() -> list[dict]:
    """BASS records that carry verbatim crew notes (the ones a human can label)."""
    return list(store.get_db().experiments.find(
        {"source_investigation": {"$regex": "^BASS"}, "flame_behavior_notes": {"$ne": None}, "flammability_relevant": True}, {"_id": 0}).sort("experiment_id", 1))


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def queue(status: str = "pending", limit: int = 200, offset: int = 0) -> LabelQueueResponse:
    done = {l["experiment_id"]: l for l in load_all()}
    items: list[LabelQueueItem] = []
    for e in labelable():
        rec = done.get(e["experiment_id"])
        sl, rule, sq = suggest(e["flame_behavior_notes"])
        st = rec["status"] if rec else ("suggested" if sl else "unlabelled")
        items.append(LabelQueueItem(
            experiment_id=e["experiment_id"], material_id=e["material_id"], oxygen_pct=e["oxygen_pct"], pressure_kpa=e["pressure_kpa"],
            flame_behavior_notes=e["flame_behavior_notes"], suggested_label=sl, suggestion_rule=rule, suggested_quote=sq, status=st,
            label=rec["label"] if rec else None, quote=rec["quote"] if rec else None, labelled_by=rec["labelled_by"] if rec else None))
    if status == "pending":
        items = [i for i in items if i.status != "confirmed"]
    elif status != "all":
        items = [i for i in items if i.status == status]
    return LabelQueueResponse(total=len(items), items=items[offset:offset + limit])


def save_label(body: LabelIn) -> LabelOut:
    e = store.get_db().experiments.find_one({"experiment_id": body.experiment_id}, {"_id": 0})
    if not e:
        raise ApiError(404, "not_found", f"Unknown experiment_id '{body.experiment_id}'", {"experiment_id": body.experiment_id})
    notes = e.get("flame_behavior_notes")
    if not notes or not e["source_investigation"].startswith("BASS"):
        raise ApiError(422, "validation_error", "Only BASS records with verbatim crew notes can be labelled", {"experiment_id": body.experiment_id})
    if _norm(body.quote) not in _norm(notes):
        raise ApiError(422, "validation_error", "quote must be a verbatim span of flame_behavior_notes", {"experiment_id": body.experiment_id, "notes": notes})
    rec = LabelOut(**body.model_dump(), status="confirmed")
    _coll().replace_one({"_id": body.experiment_id}, {"_id": body.experiment_id, **rec.model_dump()}, upsert=True)   # atomic upsert: no duplicates
    return rec


def import_csv(text: str) -> dict[str, Any]:
    """CSV columns: experiment_id,label,quote,labelled_by (header required). Rows are validated like the API; bad rows are reported."""
    ok, errors = 0, []
    for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            if not (row.get("label") or "").strip():
                continue  # blank label = not labelled yet (spreadsheet export of the whole queue)
            save_label(LabelIn(experiment_id=(row.get("experiment_id") or "").strip(), label=row["label"].strip(), quote=(row.get("quote") or "").strip(),
                               labelled_by=(row.get("labelled_by") or "").strip()))
            ok += 1
        except ApiError as e:
            errors.append({"line": i, "experiment_id": row.get("experiment_id"), "error": e.message})
        except Exception as e:  # noqa: BLE001  (pydantic validation etc.)
            errors.append({"line": i, "experiment_id": row.get("experiment_id"), "error": str(e).splitlines()[0][:160]})
    return {"imported": ok, "errors": errors}
