"""
Load Ignis_mu data into MongoDB (Atlas or a local MongoDB with vector search).

Collections
  materials       25 canonical materials (aliases, variants, stats, warnings)
  experiments     851 NASA experiment records (+ material_id, material_variant, evidence_type)
  evidence_cards  one text card per experiment; `embedding` is added by --embed

Usage
  python load_to_mongo.py --dry-run                       # validate files only, no database
  python load_to_mongo.py --uri "mongodb+srv://..." --db ignis_mu
  python load_to_mongo.py --uri ... --db ignis_mu --embed # also compute embeddings (see embed())

Needs: pip install pymongo   (and your embedding library if you use --embed)
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EMBED_DIMS = 1536   # must match your embedding model (e.g. 1536 for OpenAI text-embedding-3-small, 384 for MiniLM)


def embed(texts):
    """Return one vector (list of floats, length EMBED_DIMS) per text.
    Plug in YOUR model here and keep it fixed; changing it later means re-embedding everything.
    Example (sentence-transformers):
        from sentence_transformers import SentenceTransformer
        global _m; _m = globals().get('_m') or SentenceTransformer('all-MiniLM-L6-v2')
        return _m.encode(texts, normalize_embeddings=True).tolist()   # then set EMBED_DIMS = 384
    """
    raise NotImplementedError("Implement embed() with your embedding model, then use --embed")


def load_files():
    mats = json.loads((HERE / "materials.json").read_text(encoding="utf-8"))["materials"]
    exps = json.loads((HERE / "experiments.json").read_text(encoding="utf-8"))
    cards = json.loads((HERE / "evidence_cards.json").read_text(encoding="utf-8"))
    return mats, exps, cards


def validate(mats, exps, cards):
    ids = [e["experiment_id"] for e in exps]
    assert len(ids) == len(set(ids)), "experiment_id must be unique"
    mids = {m["material_id"] for m in mats}
    bad = [e["experiment_id"] for e in exps if e["material_id"] is not None and e["material_id"] not in mids]
    assert not bad, f"unknown material_id in {bad[:5]}"
    assert {c["experiment_id"] for c in cards} == set(ids), "every experiment needs exactly one card"
    return dict(materials=len(mats), experiments=len(exps), cards=len(cards),
                no_material=sum(e["material_id"] is None for e in exps))


def vector_index_definition():
    # Atlas Vector Search index on evidence_cards.embedding; the filter fields allow pre-filtering.
    return {"name": "evidence_vector", "type": "vectorSearch", "definition": {"fields": [
        {"type": "vector", "path": "embedding", "numDimensions": EMBED_DIMS, "similarity": "cosine"},
        {"type": "filter", "path": "material_id"},
        {"type": "filter", "path": "evidence_type"},
        {"type": "filter", "path": "gravity_level"},
        {"type": "filter", "path": "flammability_relevant"}]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri"); ap.add_argument("--db", default="ignis_mu")
    ap.add_argument("--embed", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    mats, exps, cards = load_files()
    print("validated:", validate(mats, exps, cards))
    if a.dry_run:
        print("dry run: nothing written. Vector index definition:\n", json.dumps(vector_index_definition(), indent=1))
        return 0
    if not a.uri:
        sys.exit("--uri is required unless --dry-run")
    if a.embed:
        for i in range(0, len(cards), 64):
            batch = cards[i:i + 64]
            for c, v in zip(batch, embed([c["text"] for c in batch])):
                assert len(v) == EMBED_DIMS, f"embedding has {len(v)} dims, expected {EMBED_DIMS}"
                c["embedding"] = v
    from pymongo import MongoClient, ASCENDING, TEXT
    db = MongoClient(a.uri)[a.db]
    for name, docs in (("materials", mats), ("experiments", exps), ("evidence_cards", cards)):
        db[name].drop()          # reload is idempotent: the data is rebuilt from the files
        db[name].insert_many(docs)
    db.materials.create_index([("material_id", ASCENDING)], unique=True)
    db.materials.create_index([("name_en", TEXT), ("name_ar", TEXT), ("aliases", TEXT)], name="materials_text")
    db.experiments.create_index([("experiment_id", ASCENDING)], unique=True)
    db.experiments.create_index([("material_id", ASCENDING), ("evidence_type", ASCENDING), ("gravity_level", ASCENDING)])
    db.experiments.create_index([("source_investigation", ASCENDING)])
    db.evidence_cards.create_index([("experiment_id", ASCENDING)], unique=True)
    db.evidence_cards.create_index([("material_id", ASCENDING)])
    print("loaded. Next: create the vector index on evidence_cards (Atlas UI or API) with:\n",
          json.dumps(vector_index_definition(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
