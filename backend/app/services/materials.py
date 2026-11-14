"""Material resolution: exact (EN/AR normalised) -> Mongo text index -> vector over names/aliases."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from app.core.config import get_settings
from app.models.api import MaterialCard, MaterialMatch, MaterialVariant
from app.services import store

_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().replace("ـ", "")  # tatweel
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))  # diacritics
    s = s.translate(_AR_MAP)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def tokens(s: str) -> list[str]:
    return norm(s).split()


def to_card(m: dict) -> MaterialCard:
    return MaterialCard(
        material_id=m["material_id"], name_en=m["name_en"], name_ar=m.get("name_ar"), kind=m.get("kind"),
        chemical_family=m.get("chemical_family"), aliases=m.get("aliases", []),
        variants=[MaterialVariant(variant=v["variant"], n_records=v["n_records"], inferred="not named" in v["variant"])
                  for v in m.get("variants", [])],
        oxygen_pct_range=m.get("oxygen_pct_range"), pressure_kpa_range=m.get("pressure_kpa_range"),
        moc_pct_range_1g=m.get("moc_pct_range_1g"), uloi_pct_range_1g=m.get("uloi_pct_range_1g"),
        gravity_levels=m.get("gravity_levels", []), has_microgravity_evidence=m["has_microgravity_evidence"],
        has_1g_evidence=m["has_1g_evidence"], cross_gravity_group=m.get("cross_gravity_group"),
        warnings=m.get("warnings", []), dois=m.get("dois", []))


def _names(m: dict) -> list[str]:
    return [m["material_id"], m["name_en"], m.get("name_ar") or ""] + list(m.get("aliases", []))


@lru_cache
def _exact_index() -> dict[str, str]:
    return {norm(n): mid for mid, m in store.materials().items() for n in _names(m) if n}


@lru_cache
def _vector_index():
    import numpy as np
    from app.services.embeddings import embed
    pairs = [(mid, n) for mid, m in store.materials().items() for n in [m["name_en"]] + list(m.get("aliases", []))]
    return pairs, np.array(embed([n for _, n in pairs]))


def _token_verified(q: str, m: dict) -> bool:
    """Every query token must equal, or be a >=3-char prefix of, a token of one single name/alias."""
    qt = tokens(q)
    if not qt:
        return False
    for n in _names(m):
        nt = tokens(n)
        if all(any(t == x or (len(t) >= 3 and x.startswith(t)) for x in nt) for t in qt):
            return True
    return False


def search(q: str, limit: int = 5) -> list[MaterialMatch]:
    s = get_settings()
    mats = store.materials()
    out: dict[str, MaterialMatch] = {}
    mid = _exact_index().get(norm(q))
    if mid:
        out[mid] = MaterialMatch(material=to_card(mats[mid]), score=1.0, match_type="exact")
    # (2) text index (candidate generator) + token verification so "plexi glass" never lands on "epoxy glass"
    try:
        hits = list(store.get_db().materials.find({"$text": {"$search": q}}, {"score": {"$meta": "textScore"}, "_id": 0})
                    .sort([("score", {"$meta": "textScore"})]).limit(10))
    except Exception:  # noqa: BLE001
        hits = []
    for h in hits:
        if h["material_id"] not in out and _token_verified(q, mats[h["material_id"]]):
            out[h["material_id"]] = MaterialMatch(material=to_card(mats[h["material_id"]]), score=min(0.99, 0.9), match_type="text")
    for m in mats.values():  # prefix typeahead
        if m["material_id"] not in out and _token_verified(q, m):
            out[m["material_id"]] = MaterialMatch(material=to_card(m), score=0.85, match_type="text")
    # (3) vector over names/aliases
    if not out:
        try:
            import numpy as np
            from app.services.embeddings import embed
            pairs, V = _vector_index()
            sims = V @ np.array(embed([q])[0])
            best: dict[str, float] = {}
            for i in np.argsort(-sims)[:10]:
                best.setdefault(pairs[i][0], float(sims[i]))
            for mid, sc in best.items():
                if sc >= s.material_suggest_threshold:
                    out[mid] = MaterialMatch(material=to_card(mats[mid]), score=round(sc, 3), match_type="vector",
                                             confident=sc >= s.material_vector_threshold)
        except Exception:  # noqa: BLE001
            pass
    return sorted(out.values(), key=lambda m: -m.score)[:limit]


def resolve(q: str) -> MaterialMatch | None:
    """Best confident match, else None -> unknown-material flow."""
    for m in search(q):
        if m.confident:
            return m
    return None
