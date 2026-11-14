"""Single place that owns the embedding model. Changing EMBED_MODEL means re-embedding everything."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(get_settings().embed_model)


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    vecs = _model().encode(texts, normalize_embeddings=True).tolist()
    assert all(len(v) == s.embed_dims for v in vecs), f"expected {s.embed_dims} dims"
    return vecs


def is_loaded() -> bool:
    return _model.cache_info().currsize > 0
