"""Expected data-set sizes, computed from the data files (base inputs + extra sources) instead of hard-coded."""
from app.core.config import get_settings
from app.services.extra_sources import expected_counts

EXPECTED = expected_counts(get_settings().data_dir)


# ---- database-backed labels / validation: tests use throw-away collections ----
import uuid
from contextlib import contextmanager


@contextmanager
def temp_derived():
    """Point labels and the validation result at unique empty collections; drop them afterwards."""
    from app.services import store
    s = get_settings(); old = (s.labels_collection, s.derived_collection)
    tag = uuid.uuid4().hex[:8]
    s.labels_collection, s.derived_collection = f"test_labels_{tag}", f"test_derived_{tag}"
    try:
        yield s
    finally:
        db = store.get_db()
        db[s.labels_collection].drop(); db[s.derived_collection].drop()
        s.labels_collection, s.derived_collection = old


def put_labels(rows: list[dict]) -> None:
    from app.services import store
    s = get_settings()
    store.get_db()[s.labels_collection].insert_many([{"_id": r["experiment_id"], **r} for r in rows])


def stored_labels() -> list[dict]:
    from app.services import store
    return list(store.get_db()[get_settings().labels_collection].find({}, {"_id": 0}).sort("experiment_id", 1))


def put_validation(data: dict) -> None:
    from app.services import store
    store.get_db()[get_settings().derived_collection].replace_one({"_id": "validation"}, {"_id": "validation", "data": data, "report_md": ""}, upsert=True)


def stored_validation() -> dict:
    from app.services import store
    return store.get_db()[get_settings().derived_collection].find_one({"_id": "validation"})
