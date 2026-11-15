"""Saving human labels can be protected with ADMIN_TOKEN (the labels drive the red banner)."""
from fastapi.testclient import TestClient
from helpers import temp_derived

from app.core.config import get_settings
from app.main import app

c = TestClient(app)
BODY = {"experiment_id": "BASS-003", "label": "unclear", "quote": "x", "labelled_by": "t"}


def test_label_post_requires_token_when_configured():
    s = get_settings(); old = (s.admin_token, s.mock); s.admin_token, s.mock = "secret-123", False
    try:
        with temp_derived():   # a right-token call really saves a label: keep it out of the real collection
            r = c.post("/api/admin/labels", json=BODY)
            assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
            r = c.post("/api/admin/labels", json=BODY, headers={"X-Admin-Token": "wrong"})
            assert r.status_code == 401
            r = c.post("/api/admin/labels", json=BODY, headers={"X-Admin-Token": "secret-123"})
            assert r.status_code != 401
    finally:
        s.admin_token, s.mock = old


def test_label_post_open_when_not_configured():
    s = get_settings(); old = (s.admin_token, s.mock); s.admin_token, s.mock = None, True
    try:
        assert c.post("/api/admin/labels", json=BODY).status_code == 200      # MOCK example, writes nothing
    finally:
        s.admin_token, s.mock = old
