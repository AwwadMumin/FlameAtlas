#!/usr/bin/env bash
# Stage a Hugging Face Space (Docker SDK) from this repo:  bash backend/scripts/make_hf_space.sh [out_dir]
# Then:  cd <out_dir> && git init && git add . && git commit -m deploy && git remote add space https://huggingface.co/spaces/<user>/<space> && git push space HEAD:main --force
# Secrets (MONGODB_URI, MONGODB_DB, optional ANTHROPIC_API_KEY) are set in the Space settings, never in these files.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/../mission-lens-space}"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -R "$ROOT/backend/app" "$ROOT/backend/scripts" "$ROOT/backend/tests" "$OUT/"
cp "$ROOT/backend/requirements.txt" "$ROOT/backend/requirements-ml.txt" "$OUT/"
mkdir -p "$OUT/data" "$OUT/docs"
for f in "$ROOT"/data/*.json; do cp "$f" "$OUT/data/"; done
cp -R "$ROOT/data/derived" "$OUT/data/derived"
cp -R "$ROOT/docs/." "$OUT/docs/"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +
cat > "$OUT/README.md" <<'YML'
---
title: Mission Lens API
emoji: 🔥
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---
Mission Lens backend (Team Orion, NASA Space Apps 2026). API docs at `/docs`, health at `/api/health`.
YML
cat > "$OUT/Dockerfile" <<'DOCKER'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt
ENV PYTHONPATH=/app DATA_DIR=/app/data DOCS_DIR=/app/docs HF_HOME=/hf PORT=7860
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && chmod -R a+rX /hf
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY docs ./docs
RUN chmod -R a+rX /app
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
DOCKER
echo "staged: $OUT ($(du -sh "$OUT" | cut -f1))"
