from __future__ import annotations

from app.core.config import Settings


def check(s: Settings) -> dict:
    out = {"mock": s.mock, "db": {"connected": False}, "vector_index": {"name": "evidence_vector", "queryable": None},
           "embedding_model": {"name": s.embed_model, "dims": s.embed_dims, "loaded": False}}
    try:
        from app.services import embeddings
        out["embedding_model"]["loaded"] = embeddings.is_loaded()
    except Exception:  # noqa: BLE001
        pass
    if s.mock:
        out["db"]["note"] = "MOCK=1: no database used"
        return out
    try:
        from pymongo import MongoClient
        c = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=2000)
        c.admin.command("ping")
        db = c[s.mongodb_db]
        out["db"] = {"connected": True, "db": s.mongodb_db,
                     "counts": {n: db[n].count_documents({}) for n in ("materials", "experiments", "evidence_cards")}}
        try:
            idx = [i for i in db.evidence_cards.list_search_indexes() if i.get("name") == "evidence_vector"]
            out["vector_index"]["queryable"] = bool(idx and idx[0].get("queryable"))
        except Exception as e:  # noqa: BLE001
            out["vector_index"]["error"] = str(e)[:200]
    except Exception as e:  # noqa: BLE001
        out["db"] = {"connected": False, "error": str(e)[:200]}
    return out
