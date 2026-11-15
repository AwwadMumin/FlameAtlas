"""Atlas can report WriteConcernError after the primary applied the write: the label must still be accepted, but only if it is really stored."""
import pytest
from helpers import EXPECTED, stored_labels, temp_derived
from pymongo.errors import WriteConcernError

from app.models.api import LabelIn
from app.services import labels, store


class Flaky:
    """Wraps a real collection; replace_one raises WriteConcernError after (or instead of) writing."""
    def __init__(self, real, really_write):
        self.real, self.really_write = real, really_write

    def replace_one(self, *a, **k):
        if self.really_write:
            self.real.replace_one(*a, **k)
        raise WriteConcernError("waiting for replication timed out", 64, {})

    def find_one(self, *a, **k):
        return self.real.find_one(*a, **k)


def _body():
    e = store.get_db().experiments.find_one({"experiment_id": "BASS-003"}, {"_id": 0})
    return LabelIn(experiment_id="BASS-003", label="unclear", quote=e["flame_behavior_notes"][:20], labelled_by="t")


@pytest.fixture
def db():
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")


def test_write_concern_error_after_a_real_write_is_accepted(db, monkeypatch):
    with temp_derived():
        real = labels._coll()
        monkeypatch.setattr(labels, "_coll", lambda: Flaky(real, True))
        out = labels.save_label(_body())
        assert out.status == "confirmed" and [l["experiment_id"] for l in stored_labels()] == ["BASS-003"]


def test_write_concern_error_without_a_stored_label_still_raises(db, monkeypatch):
    with temp_derived():
        real = labels._coll()
        monkeypatch.setattr(labels, "_coll", lambda: Flaky(real, False))
        with pytest.raises(WriteConcernError):
            labels.save_label(_body())
        assert stored_labels() == []
