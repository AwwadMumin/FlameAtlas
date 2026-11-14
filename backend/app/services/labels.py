"""Human outcome labels (data/derived/outcome_labels.json). Phase 3: read-only access; Phase 5 adds writing."""
from __future__ import annotations

import json

from app.core.config import get_settings


def load_all() -> list[dict]:
    p = get_settings().derived_dir / "outcome_labels.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def confirmed() -> dict[str, dict]:
    """experiment_id -> label record, only human-confirmed labels (suggestions never count)."""
    return {l["experiment_id"]: l for l in load_all() if l.get("status") == "confirmed"}
