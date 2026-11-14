"""Load Mission Lens data into MongoDB (atlas-local or Atlas). Based on data/load_to_mongo.py (input files untouched).

  python scripts/load_to_mongo.py --dry-run
  python scripts/load_to_mongo.py --uri "$MONGODB_URI" --db ignis_mu --embed

Collections: materials, experiments, evidence_cards (+ `embedding`, 384 dims, all-MiniLM-L6-v2).
Creates the `evidence_vector` vector index programmatically and waits until it is queryable.
"""
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings  # noqa: E402

DATA = get_settings().data_dir
EMBED_DIMS = 384  # all-MiniLM-L6-v2; must equal Settings.embed_dims


def embed(texts):
    from app.services.embeddings import embed as _e
    return _e(texts)


def load_files():
    mats = json.loads((DATA / "materials.json").read_text(encoding="utf-8"))["materials"]
    exps = json.loads((DATA / "experiments.json").read_text(encoding="utf-8"))
    cards = json.loads((DATA / "evidence_cards.json").read_text(encoding="utf-8"))
    return mats, exps, cards


def validate(mats, exps, cards):
    ids = [e["experiment_id"] for e in exps]
    assert len(ids) == len(set(ids)), "experiment_id must be unique"
    mids = {m["material_id"] for m in mats}
    bad = [e["experiment_id"] for e in exps if e["material_id"] is not None and e["material_id"] not in mids]
    assert not bad, f"unknown material_id in {bad[:5]}"
    assert {c["experiment_id"] for c in cards} == set(ids), "every experiment needs exactly one card"
    assert get_settings().embed_dims == EMBED_DIMS
    return dict(materials=len(mats), experiments=len(exps), cards=len(cards), no_material=sum(e["material_id"] is None for e in exps))


def vector_index_definition():
    return {"name": "evidence_vector", "type": "vectorSearch", "definition": {"fields": [
        {"type": "vector", "path": "embedding", "numDimensions": EMBED_DIMS, "similarity": "cosine"},
        {"type": "filter", "path": "material_id"},
        {"type": "filter", "path": "evidence_type"},
        {"type": "filter", "path": "gravity_level"},
        {"type": "filter", "path": "flammability_relevant"}]}}


def create_vector_index(db, timeout=180):
    from pymongo.operations import SearchIndexModel
    d = vector_index_definition()
    coll = db.evidence_cards
    for i in coll.list_search_indexes():
        if i["name"] == d["name"]:
            coll.drop_search_index(d["name"])
            while any(x["name"] == d["name"] for x in coll.list_search_indexes()):
                time.sleep(1)
    coll.create_search_index(SearchIndexModel(definition=d["definition"], name=d["name"], type="vectorSearch"))
    t0 = time.time()
    while time.time() - t0 < timeout:
        idx = [i for i in coll.list_search_indexes() if i["name"] == d["name"]]
        if idx and idx[0].get("queryable"):
            return True
        time.sleep(2)
    raise TimeoutError("vector index not queryable in time")


def smoke_test(db):
    q = embed(["PMMA rod flame spread in microgravity"])[0]
    res = list(db.evidence_cards.aggregate([{"$vectorSearch": {
        "index": "evidence_vector", "path": "embedding", "queryVector": q, "numCandidates": 100, "limit": 3,
        "filter": {"material_id": "pmma", "flammability_relevant": True}}},
        {"$project": {"experiment_id": 1, "text": 1, "score": {"$meta": "vectorSearchScore"}}}]))
    assert res, "vector search returned nothing"
    return res


def main():
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default=s.mongodb_uri); ap.add_argument("--db", default=s.mongodb_db)
    ap.add_argument("--embed", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--if-empty", action="store_true", help="skip when the DB already holds the full embedded data set and a queryable vector index")
    a = ap.parse_args()
    mats, exps, cards = load_files()
    print("validated:", validate(mats, exps, cards))
    if a.dry_run:
        print("dry run: nothing written.")
        return 0
    if a.if_empty:
        from pymongo import MongoClient as _MC
        d = _MC(a.uri, serverSelectionTimeoutMS=5000)[a.db]
        try:
            ready = (d.experiments.count_documents({}) == len(exps) and d.evidence_cards.count_documents({"embedding": {"$exists": True}}) == len(cards)
                     and any(i["name"] == "evidence_vector" and i.get("queryable") for i in d.evidence_cards.list_search_indexes()))
        except Exception:  # noqa: BLE001
            ready = False
        if ready:
            print("data already loaded and embedded: nothing to do")
            return 0
    if a.embed:
        for i in range(0, len(cards), 64):
            batch = cards[i:i + 64]
            for c, v in zip(batch, embed([c["text"] for c in batch])):
                c["embedding"] = v
        print("embedded", sum("embedding" in c for c in cards), "cards")
    from pymongo import MongoClient, ASCENDING, TEXT
    db = MongoClient(a.uri)[a.db]
    for name, docs in (("materials", mats), ("experiments", exps), ("evidence_cards", cards)):
        db[name].drop()
        db[name].insert_many(docs)
    db.materials.create_index([("material_id", ASCENDING)], unique=True)
    db.materials.create_index([("name_en", TEXT), ("name_ar", TEXT), ("aliases", TEXT)], name="materials_text")
    db.experiments.create_index([("experiment_id", ASCENDING)], unique=True)
    db.experiments.create_index([("material_id", ASCENDING), ("evidence_type", ASCENDING), ("gravity_level", ASCENDING)])
    db.experiments.create_index([("source_investigation", ASCENDING)])
    db.evidence_cards.create_index([("experiment_id", ASCENDING)], unique=True)
    db.evidence_cards.create_index([("material_id", ASCENDING)])
    print("loaded:", {n: db[n].count_documents({}) for n in ("materials", "experiments", "evidence_cards")})
    if a.embed:
        create_vector_index(db)
        print("vector index queryable")
        for r in smoke_test(db):
            print(f"  {r['score']:.3f} {r['experiment_id']}: {r['text'][:90]}")
        print("embedded cards:", db.evidence_cards.count_documents({"embedding": {"$exists": True}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
