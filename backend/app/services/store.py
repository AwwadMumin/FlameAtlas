"""Data access: Mongo handle + cached read-only reference data (materials, knowledge pack)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import get_settings


@lru_cache
def get_db() -> Database:
    s = get_settings()
    return MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=3000)[s.mongodb_db]


@lru_cache
def materials() -> dict[str, dict[str, Any]]:
    return {m["material_id"]: m for m in get_db().materials.find({}, {"_id": 0})}


@lru_cache
def knowledge() -> dict[str, Any]:
    return json.loads((get_settings().data_dir / "flame_in_freefall_knowledge.json").read_text(encoding="utf-8"))


@lru_cache
def findings() -> dict[str, dict]:
    return {f["id"]: f for f in knowledge()["guide_findings"]["findings"]}


@lru_cache
def investigations() -> dict[str, dict]:
    return {i["accession"]: i for i in knowledge()["investigations"]}


@lru_cache
def field_spans() -> dict[str, float]:
    """Normalisation spans for the condition distance, read from the data (no hard-coded numbers)."""
    out = {}
    for f in ("oxygen_pct", "pressure_kpa", "airflow_cm_s"):
        r = list(get_db().experiments.aggregate([{"$match": {f: {"$ne": None}}},
              {"$group": {"_id": None, "mn": {"$min": f"${f}"}, "mx": {"$max": f"${f}"}}}]))
        out[f] = (r[0]["mx"] - r[0]["mn"]) or 1.0 if r else 1.0
    return out


def strip(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc
