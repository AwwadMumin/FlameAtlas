"""Regenerate docs/examples/* from the REAL pipeline (needs loaded Mongo). Keeps MOCK responses identical to real ones.
Run inside the backend container:  python scripts/export_live_examples.py"""
import json
import os
from pathlib import Path

os.environ["MOCK"] = "0"
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

OUT = get_settings().docs_dir / "examples"
c = TestClient(app)


def save(name, resp):
    assert resp.status_code == 200, (name, resp.text[:300])
    (OUT / f"{name}.json").write_text(json.dumps(resp.json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", name)


sc = {s["id"]: s["request"] for s in c.get("/api/demo-scenarios").json()["scenarios"]}
save("demo_scenarios", c.get("/api/demo-scenarios"))
save("presets", c.get("/api/presets"))
save("assess_evidence", c.post("/api/assess", json=sc["pmma_iss"]))
save("assess_sibal_iss", c.post("/api/assess", json=sc["sibal_iss"]))
save("assess_no_direct_moon", c.post("/api/assess", json=sc["pet_exploration"]))
save("assess_no_direct_1g_only", c.post("/api/assess", json=sc["pet_exploration"] | {"gravity": "orbit"}))
save("assess_unknown_material", c.post("/api/assess", json=sc["unknown_mars"]))
save("assess_unknown_empty", c.post("/api/assess", json={"material_query": "Zorbium-7", "gravity": "mars"}))
save("materials_search", c.get("/api/materials/search", params={"q": "acrylic"}))
save("material_detail", c.get("/api/materials/pmma"))
save("experiment_detail", c.get("/api/experiments/WSTF-013"))
save("about", c.get("/api/about"))
save("coverage", c.get("/api/coverage/pmma"))
save("next_experiments", c.get("/api/next-experiments", params={"preset": "exploration", "limit": 5}))
save("validation", c.get("/api/validation"))
save("labels_queue", c.get("/api/admin/labels/queue", params={"limit": 3}))
save("experiments_list", c.get("/api/experiments", params={"material": "pmma", "limit": 5}))
save("compare", c.post("/api/compare", json={"experiment_ids": ["WSTF-013", "WSTF-044", "LINK2018-S2-L01", "BASS2-001"], "use_llm": False}))
save("ask", c.post("/api/ask", json={"question": "How does PMMA behave at 18.5% oxygen in microgravity?", "use_llm": False}))
