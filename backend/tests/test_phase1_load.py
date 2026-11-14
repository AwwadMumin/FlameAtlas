"""Integration: needs the loaded Mongo (docker compose + load_to_mongo.py --embed). Skipped otherwise."""
import os

import pytest

pymongo = pytest.importorskip("pymongo")
from app.core.config import get_settings  # noqa: E402

s = get_settings()
try:
    c = pymongo.MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=1500)
    c.admin.command("ping")
    db = c[s.mongodb_db]
    LOADED = db.evidence_cards.count_documents({}) == 872
except Exception:
    LOADED = False
pytestmark = pytest.mark.skipif(not LOADED, reason="Mongo not loaded")


def test_counts_and_embeddings():
    assert db.materials.count_documents({}) == 31 and db.experiments.count_documents({}) == 872
    assert db.evidence_cards.count_documents({"embedding": {"$exists": True}}) == 872
    assert len(db.evidence_cards.find_one()["embedding"]) == s.embed_dims == 384


def test_vector_search_prefilter():
    from app.services.embeddings import embed
    q = embed(["PMMA flame spread"])[0]
    r = list(db.evidence_cards.aggregate([{"$vectorSearch": {"index": "evidence_vector", "path": "embedding", "queryVector": q,
        "numCandidates": 50, "limit": 5, "filter": {"material_id": "pmma", "flammability_relevant": True}}}]))
    assert r and all(x["material_id"] == "pmma" and x["flammability_relevant"] for x in r)
