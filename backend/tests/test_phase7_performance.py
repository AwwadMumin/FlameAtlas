"""Phase 7: assess < 1.5 s without the LLM, for the demo scenarios (p95 over repeated runs)."""
import statistics
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != 872:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); s.mock = False
    old = s.anthropic_api_key; s.anthropic_api_key = None
    from app.main import app
    yield TestClient(app)
    s.mock, s.anthropic_api_key = True, old


def test_assess_latency_budget(live):
    scen = [s["request"] | {"use_llm": False} for s in live.get("/api/demo-scenarios").json()["scenarios"]]
    qs = scen + [scen[0] | {"question": "will it self-extinguish?"}]          # includes a vector-search request
    for q in qs:
        live.post("/api/assess", json=q)                                      # warm-up
    times = {}
    for i, q in enumerate(qs):
        ts = []
        for _ in range(15):
            t = time.perf_counter(); r = live.post("/api/assess", json=q); ts.append(time.perf_counter() - t)
            assert r.status_code == 200
        times[i] = sorted(ts)[int(0.95 * len(ts)) - 1]
        print(f"scenario {i}: median {statistics.median(ts) * 1000:.0f} ms, p95 {times[i] * 1000:.0f} ms")
    assert max(times.values()) < 1.5
