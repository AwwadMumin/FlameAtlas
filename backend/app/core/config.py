import os
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
    ask_similarity_threshold: float = 0.70   # /api/ask: unrelated questions score ~0.55-0.60, relevant ones >= 0.75 (measured on the MiniLM cards)

    # coverage tolerances, shown to the user as "matched within ±..."
    tol_o2_pct: float = 1.5
    tol_pressure_kpa: float = 20.0

    # condition-distance weights for ranking
    w_o2: float = 1.0
    w_pressure: float = 0.5
    w_airflow: float = 0.3
    top_n_per_group: int = 8
    material_vector_threshold: float = 0.80   # auto-resolve; lower scores are suggestions only
    material_suggest_threshold: float = 0.65

    correction_models_path: Path = Path(__file__).resolve().parent / "correction_models.yaml"
    admin_token: str | None = None                # when set, POST /api/admin/labels needs header X-Admin-Token (human labels drive the red banner)
    labels_collection: str = "outcome_labels"      # human labels live in the database, not in files
    derived_collection: str = "derived_docs"       # validation result (+ markdown report)
    derived_dir: Path = Path(os.environ.get("DATA_DIR", ROOT / "data")) / "derived"
    # Van Krevelen LOI = a + b * CR (formula given in the team brief; 1g downward LOI, not a microgravity limit)
    vk_intercept: float = 17.5
    vk_slope: float = 0.40

    # gap map / next-experiment recommender
    pressure_bin_edges_kpa: tuple[float, ...] = (60.0, 80.0, 95.0)
    gap_w_closeness: float = 0.5
    gap_w_materials: float = 0.3
    gap_w_1g_only: float = 0.2
    gap_o2_bins_around_preset: int = 3
    gap_excluded_kind_words: tuple[str, ...] = ("liquid", "gaseous")

    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"     # override with LLM_MODEL
    llm_max_tokens: int = 4000              # thinking is always on for this model: leave room for it plus ~150 words
    llm_timeout_s: float = 20.0
    llm_effort: str = "low"


@lru_cache
def get_settings() -> Settings:
    return Settings()
