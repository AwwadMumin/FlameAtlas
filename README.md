# Mission Lens (backend) — Team Orion, NASA Space Apps 2026

Backend + API only. See `docs/API_CONTRACT.md` for the frontend contract.

```bash
cp .env.example .env
docker compose up --build        # mongo (atlas-local) + backend on :8000
# no DB needed for the frontend team:  MOCK=1 -> served from docs/examples/*.json
```
Docs: http://localhost:8000/docs
