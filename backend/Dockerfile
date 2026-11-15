# Build from the repo root:  docker build -f backend/Dockerfile -t mission-lens .
# The image is self-contained: code + the read-only inputs in data/ (not data/raw) + docs/examples + the embedding model.
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt
ENV PYTHONPATH=/app DATA_DIR=/app/data DOCS_DIR=/app/docs HF_HOME=/hf
# embedding model baked in so a fresh container needs no download at start
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/tests ./tests
COPY data ./data
COPY docs ./docs
# hosts such as Render inject PORT; default 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
