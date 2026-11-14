"""Phase 6: optional LLM summary, number guard, fallback to template. No API key / network needed (fake client)."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services import summary


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != 872:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); s.mock = False
    from app.main import app
    yield TestClient(app)
    s.mock = True


@pytest.fixture
def key():
    s = get_settings(); old = s.anthropic_api_key
    s.anthropic_api_key = "test-key-not-real"
    yield s
    s.anthropic_api_key = old


class FakeClient:
    """Mimics client.beta.messages.create(...) and records the request."""
    def __init__(self, text=None, stop="end_turn", raises=None):
        self.text, self.stop, self.raises, self.calls = text, stop, raises, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.raises:
            raise self.raises
        blocks = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text or "")]
        return SimpleNamespace(stop_reason=self.stop, content=blocks)


def _req(**kw):
    return {"material_query": "acrylic", "oxygen_pct": 21, "pressure_kpa": 101, "gravity": "orbit"} | kw


def _ctx_resp(live):
    from app.models.api import AssessRequest
    from app.services import assess
    r = assess._assess(AssessRequest(**_req()))
    return r, json.dumps(summary.build_context(r), ensure_ascii=False, default=str)


# ---------- no key: everything works, nothing is called ----------
def test_no_key_uses_template_and_never_calls_llm(live, monkeypatch):
    s = get_settings(); old = s.anthropic_api_key; s.anthropic_api_key = None
    monkeypatch.setattr(summary, "get_client", lambda: pytest.fail("LLM must not be called without a key"))
    try:
        d = live.post("/api/assess", json=_req()).json()
    finally:
        s.anthropic_api_key = old
    assert d["summary_source"] == "template" and d["summary_fallback_reason"] is None


# ---------- guard unit tests ----------
def test_guard_accepts_numbers_from_records(live):
    r, ctx = _ctx_resp(live)
    rec = r.evidence_groups[0].records[0]
    good = (f"Evidence: PMMA (acrylic) has tested records within ±{r.matched_tolerances.o2_pct:g}% O2. Closest is {rec.experiment_id} "
            f"at {rec.oxygen_pct}% O2 ({rec.source_ref}).")
    assert summary.check_text(good, ctx, r) is None


@pytest.mark.parametrize("text,why", [
    ("Evidence: PMMA burned at 37.5% O2 in microgravity.", "number"),
    ("Evidence: records cover 4242 tests.", "number"),
    ("Evidence: there are seventeen relevant records.", "spelled-out"),
    ("Evidence: see BASS-999 for details.", "identifier"),
    ("PMMA looks fine at these conditions.", "verdict"),
    ("", "empty"),
])
def test_guard_rejects(live, text, why):
    r, ctx = _ctx_resp(live)
    reason = summary.check_text(text, ctx, r)
    assert reason and why in reason, (text, reason)


def test_guard_formulas_and_gravity_labels_do_not_whitelist_numbers(live):
    r, ctx = _ctx_resp(live)
    assert summary.check_text("Evidence at O2 in 1g and µg conditions.", ctx, r) is None
    assert summary.numbers("O2 N2 CO2 1g 0 g µg BASS-096 PSI-26 10.60555/58h4-dy80 NASA-STD-6001") == set()   # labels/ids never whitelist or trip numbers
    assert summary.numbers("21.5% at 101 kPa, 1,000 s") == {21.5, 101.0, 1000.0}


# ---------- end to end with a fake client ----------
def test_llm_text_with_extra_number_falls_back_to_template(live, key, monkeypatch):
    """Acceptance: an LLM output containing an extra number falls back to the template."""
    fake = FakeClient("Evidence: PMMA has records near 21% O2, and the limit is 12.7% O2 in microgravity.")
    monkeypatch.setattr(summary, "get_client", lambda: fake)
    d = live.post("/api/assess", json=_req()).json()
    assert d["summary_source"] == "template" and "12.7" in d["summary_fallback_reason"]
    assert "12.7" not in d["summary_text"] and d["summary_text"].startswith("PMMA (acrylic): EVIDENCE")
    assert len(fake.calls) == 1


def test_valid_llm_text_is_used_and_marked_checked(live, key, monkeypatch):
    r, _ = _ctx_resp(live)
    rec = r.evidence_groups[0].records[0]
    text = f"Evidence: PMMA has tested microgravity records near 21% O2; closest is {rec.experiment_id} ({rec.source_ref})."
    fake = FakeClient(text)
    monkeypatch.setattr(summary, "get_client", lambda: fake)
    d = live.post("/api/assess", json=_req()).json()
    assert d["summary_source"] == "llm_checked" and d["summary_text"] == text and d["summary_fallback_reason"] is None
    kw = fake.calls[0]                                                   # request shape for claude-opus-5-5
    assert kw["model"] == "claude-opus-5-5" and kw["output_config"] == {"effort": "low"}
    assert "temperature" not in kw and "top_p" not in kw and "thinking" not in kw
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["max_tokens"] >= 2000
    assert "Never add a number" in kw["system"] and "experiment_id" in kw["messages"][0]["content"]


@pytest.mark.parametrize("fake,why", [
    (FakeClient(raises=RuntimeError("boom")), "LLM unavailable"),
    (FakeClient("Evidence: ok", stop="refusal"), "refusal"),
    (FakeClient("Evidence: ok", stop="max_tokens"), "max_tokens"),
])
def test_llm_failures_fall_back(live, key, monkeypatch, fake, why):
    monkeypatch.setattr(summary, "get_client", lambda: fake)
    r = live.post("/api/assess", json=_req())
    assert r.status_code == 200
    d = r.json()
    assert d["summary_source"] == "template" and why in d["summary_fallback_reason"]


def test_use_llm_false_skips_call(live, key, monkeypatch):
    monkeypatch.setattr(summary, "get_client", lambda: pytest.fail("must not call"))
    assert live.post("/api/assess", json=_req(use_llm=False)).json()["summary_source"] == "template"


def test_unknown_material_estimate_must_be_labelled_not_tested(live, key, monkeypatch):
    body = _req(material_query="Zorbium-7", gravity="mars", unknown_material_props={"char_yield_pct": 30})
    monkeypatch.setattr(summary, "get_client", lambda: FakeClient("No direct evidence. LOI estimate is 29.5% O2."))
    assert live.post("/api/assess", json=body).json()["summary_fallback_reason"] == "estimate not labelled 'not tested'"
    ok = "No direct evidence for this material. The LOI (downward, 1g) estimate of 29.5% O2 from char yield 30.0% is not tested and is not a microgravity limit."
    monkeypatch.setattr(summary, "get_client", lambda: FakeClient(ok))
    d = live.post("/api/assess", json=body).json()
    assert d["summary_source"] == "llm_checked" and d["summary_text"] == ok


def test_mock_mode_never_calls_llm(key, monkeypatch):
    monkeypatch.setattr(summary, "get_client", lambda: pytest.fail("must not call"))
    from app.main import app
    s = get_settings(); old = s.mock; s.mock = True
    try:
        assert TestClient(app).post("/api/assess", json=_req()).json()["summary_source"] == "template"
    finally:
        s.mock = old
