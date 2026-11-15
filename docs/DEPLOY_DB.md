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
- **Labels and validation now live in the database** (collections `outcome_labels` and `derived_docs`), so they survive restarts and redeploys. The loader never drops them. Exported `validation.json`/`.md` files are only a convenience copy.
  Move them to a Mongo collection (small change) or mount a persistent volume.
- **The production image is self-contained**: build from the repo root with `docker build -f backend/Dockerfile -t mission-lens .`. It holds the code, `data/` (without `data/raw`), `docs/` and the embedding model. Run it with `MONGODB_URI` and `MONGODB_DB` set and port 8000.
- Set `CORS_ORIGINS` to the real frontend origin, and keep `ANTHROPIC_API_KEY` in the host's secret store.

## Hosting the API on Render

`render.yaml` at the repo root is a Blueprint (Docker, `backend/Dockerfile`, branch `Backend`, health check `/api/health`).

1. Render dashboard: **New > Blueprint**, pick the repo, confirm the branch. Render asks for the secrets marked `sync: false`.
2. Set `MONGODB_URI` to the Atlas connection string. Optional: `ANTHROPIC_API_KEY`. Set `CORS_ORIGINS` to the frontend's origin once it is known.
3. Atlas **Network Access**: Render web services have no fixed IP on the starter plan, so allow `0.0.0.0/0` and rely on a strong, rotated database password (or use Render's static outbound IPs and allow only those).
4. The plan is `starter` because torch + the embedding model do not fit the free tier's 512 MB. The container listens on Render's `PORT`.
5. Check `https://<service>.onrender.com/api/health`: expect 31 / 970 / 970 and `vector_index.queryable: true`. Swagger is at `/docs`.

The data is already loaded in Atlas (see above); the service does not load or drop anything on start.

## Free hosting: Hugging Face Spaces (no card)

Render's plan that fits torch + the embedding model is paid. A Hugging Face Space (Docker SDK, free CPU, 16 GB RAM) runs the same API.

1. Create an account and a new Space: **Create new Space → SDK: Docker → Blank**, visibility Public or Private.
2. Space **Settings → Variables and secrets**: secret `MONGODB_URI` (Atlas string), variable `MONGODB_DB` = `ignis_mu`, optional secret `ANTHROPIC_API_KEY`, variable `CORS_ORIGINS` = the frontend origin (or `*` while developing).
3. Stage the files and push them to the Space (it is a separate git repo; use a HF access token with write role as the password):
   ```bash
   bash backend/scripts/make_hf_space.sh ../mission-lens-space
   cd ../mission-lens-space && git init -b main && git add . && git commit -m deploy
   git remote add space https://huggingface.co/spaces/<user>/<space> && git push space main --force
   ```
4. After the build (~5 min) open `https://<user>-<space>.hf.space/api/health` (31 / 970 / 970, vector index queryable) and `/docs`.
5. Atlas Network Access must allow `0.0.0.0/0` (Spaces have no fixed IP). Free Spaces sleep after about 2 days without traffic and wake on the next request.

The staged copy contains no `.env` files and no `data/raw`. Tested as a non-root user against Atlas.
