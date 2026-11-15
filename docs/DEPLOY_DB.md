# Putting the data in a hosted database

## Recommendation: MongoDB Atlas (not Supabase)
The backend already runs on MongoDB with `$vectorSearch`; moving to Atlas is a connection string and one loader command, no code change.
Supabase is Postgres + pgvector. It would work, but the data layer (`services/store.py`, `materials.py` text/vector search, `evidence.py`
retrieval, `gaps.py`, `validation.py`, the `queries` log) would have to be rewritten and re-tested. Say so if the team prefers Supabase; it is a
separate piece of work, not a setting.

## Steps (Atlas)
1. Create an Atlas project and a cluster (the free M0 tier supports vector search; the data set is only a few MB).
2. Database access: create two users on database `ignis_mu`: a **loader** user (readWrite) and an **API** user (read, plus write on `queries`).
3. Network access: allow the IP of the machine that loads the data and, later, of the API host. Avoid `0.0.0.0/0` outside of a short test.
4. Copy the SRV connection string into your **local `.env`** (it is git-ignored). Never paste it into chat, issues or commits.
5. Load (drops and rebuilds `materials`, `experiments`, `evidence_cards`; creates the `evidence_vector` index and waits until it is queryable):
   ```bash
   docker compose run --rm -e MONGODB_URI="$ATLAS_URI" backend \
       python scripts/load_to_mongo.py --db ignis_mu --embed --confirm-drop
   ```
   The loader refuses a non-local host without `--confirm-drop`.
6. Check: run the API with `MONGODB_URI` pointing at Atlas and open `/api/health`: `db.connected: true`, counts 31 / 970 / 970, `vector_index.queryable: true`.

## Before hosting the API (not done yet)
- **Labels and validation live in files** (`data/derived/outcome_labels.json`, `validation.json`). On an ephemeral host (most PaaS) they disappear on restart.
  Move them to a Mongo collection (small change) or mount a persistent volume.
- **The image needs `data/`** (knowledge pack, materials, derived files). Compose mounts it; a production image must copy it (build from the repo root) or mount it.
- Set `CORS_ORIGINS` to the real frontend origin, and keep `ANTHROPIC_API_KEY` in the host's secret store.
