from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongodb_db: str = "ignis_mu"
    cors_origins: str = "*"
    mock: bool = False
    data_dir: Path = ROOT / "data"
    docs_dir: Path = ROOT / "docs"

    # embeddings (changing the model means re-embedding everything)
    embed_model: str = "all-MiniLM-L6-v2"
    embed_dims: int = 384
    similarity_threshold: float = 0.55

    # coverage tolerances, shown to the user as "matched within ±..."
    tol_o2_pct: float = 1.5
    tol_pressure_kpa: float = 20.0

    # condition-distance weights for ranking
    w_o2: float = 1.0
    w_pressure: float = 0.5
    w_airflow: float = 0.3
    top_n_per_group: int = 8

    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
