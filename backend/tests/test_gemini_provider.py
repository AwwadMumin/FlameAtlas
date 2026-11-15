"""Gemini as an alternative LLM: provider choice, response parsing, and the same number guard (no network, no key needed)."""
import pytest

from app.core.config import get_settings
from app.services import summary


@pytest.fixture
def cfg():
    s = get_settings(); old = (s.anthropic_api_key, s.gemini_api_key, s.llm_provider, s.mock)
    yield s
    s.anthropic_api_key, s.gemini_api_key, s.llm_provider, s.mock = old


def test_provider_selection(cfg):
    cfg.mock = False
    cfg.anthropic_api_key = cfg.gemini_api_key = None
    assert summary.provider() is None and not summary.llm_available()
    cfg.gemini_api_key, cfg.llm_provider = "g", "auto"
    assert summary.provider() == "gemini" and summary.llm_available()
    cfg.anthropic_api_key = "a"
    assert summary.provider() == "anthropic"                  # auto prefers Anthropic when both are set
    cfg.llm_provider = "gemini"
    assert summary.provider() == "gemini"
    cfg.llm_provider = "anthropic"; cfg.anthropic_api_key = None
    assert summary.provider() is None                          # explicit choice without its key: never silently use the other
    cfg.gemini_api_key, cfg.llm_provider, cfg.mock = "g", "auto", True
    assert not summary.llm_available()                         # MOCK never calls an LLM
    assert not summary.llm_available(use_llm=False)


def test_gemini_text_parsing():
    ok = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "A "}, {"text": "hidden", "thought": True}, {"text": "B"}]}}]}
    assert summary._gemini_text(ok) == "A B"                   # thought parts are dropped
    for bad, msg in (({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked"), ({"candidates": []}, "no candidates"),
                     ({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}, "stopped early")):
        with pytest.raises(RuntimeError, match=msg):
            summary._gemini_text(bad)


def test_gemini_http_error_never_leaks_key(cfg, monkeypatch):
    import io
    import urllib.error
    import urllib.request
    cfg.gemini_api_key = "SECRET-KEY-123"

    def boom(req, timeout=0):
        assert req.get_header("X-goog-api-key") == "SECRET-KEY-123" and "SECRET" not in req.full_url
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError) as e:
        summary._gemini("s", "u")
    assert "429" in str(e.value) and "SECRET" not in str(e.value)


def test_guard_rejects_unsupported_superlatives():
    ctx = '{"records":[{"experiment_id":"WSTF-045","outcome_value":19.0}]}'
    r = summary.check_free("The lowest oxygen where PMMA burns in 1g is 19.0 % O2 (WSTF-045).", ctx)
    assert r and "lowest" in r
    assert summary.check_free("Minimum O2 is 19.0 % (WSTF-045).", ctx) and "Minimum" in summary.check_free("Minimum O2 is 19.0 % (WSTF-045).", ctx)
    assert summary.check_free("In the retrieved records, WSTF-045 reports MOC 19.0 % O2.", ctx) is None
    assert summary.check_free("It is the lowest.", '{"note":"the lowest row is 14.0"}') is None      # allowed when the context itself says it
    assert "safe" in summary.check_free("PMMA is safe at 19.0 % O2.", ctx)


def test_gemini_text_goes_through_the_number_guard(cfg, monkeypatch):
    ctx = '{"records":[{"experiment_id":"WSTF-013","outcome_value":19.0}]}'
    assert summary.check_free("WSTF-013 reports MOC 19.0 % O2.", ctx) is None
    assert "23.4" in summary.check_free("WSTF-013 reports MOC 23.4 % O2.", ctx)
    assert "spelled-out" in summary.check_free("WSTF-013 reports nineteen percent.", ctx)
