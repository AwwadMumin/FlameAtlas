FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
ENV PYTHONPATH=/app DATA_DIR=/app/data DOCS_DIR=/app/docs HF_HOME=/hf
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
