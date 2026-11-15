"""Phase 5: labels (API + CSV), validation, coverage, next experiments. Uses a temp derived dir; synthetic labels exist only in tests."""
import json
import subprocess
import sys

import pytest
from helpers import EXPECTED
import yaml
from fastapi.testclient import TestClient

from app.core.config import get_settings


@pytest.fixture(scope="module")
def live():
    from app.services import store
    try:
        if store.get_db().experiments.count_documents({}) != EXPECTED["experiments"]:
            pytest.skip("Mongo not loaded")
    except Exception:
        pytest.skip("Mongo unavailable")
    s = get_settings(); s.mock = False
    from app.main import app
    yield TestClient(app)
    s.mock = True


@pytest.fixture
def derived(tmp_path):
    from helpers import temp_derived
    with temp_derived() as s:
        s.derived_dir = tmp_path / "derived"   # exported validation files go to a temp folder
        yield s.derived_dir


def _ex(live, eid):
    from app.services import store
    return store.get_db().experiments.find_one({"experiment_id": eid}, {"_id": 0})


def _first_words(notes, n=4):
    return " ".join(notes.split()[:n])


# ---------- labels ----------
def test_queue_and_suggestions_are_hints(live, derived):
    q = live.get("/api/admin/labels/queue?limit=1000").json()
    assert q["total"] == 121 and all(i["flame_behavior_notes"] for i in q["items"])
    assert all(i["status"] in ("suggested", "unlabelled") and i["label"] is None for i in q["items"])
    sug = [i for i in q["items"] if i["suggested_label"]]
    assert sug and all(" ".join(i["suggested_quote"].split()).lower() in " ".join(i["flame_behavior_notes"].split()).lower() for i in sug)
    from helpers import stored_labels
    assert stored_labels() == []                                    # suggestions are never saved as decisions


def test_save_label_rules_and_queue_effect(live, derived):
    e = _ex(live, "BASS-003")
    quote = _first_words(e["flame_behavior_notes"])
    body = {"experiment_id": "BASS-003", "label": "extinguished_by_flow_or_N2", "quote": quote, "labelled_by": "tester"}
    r = live.post("/api/admin/labels", json=body)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    from helpers import stored_labels
    assert stored_labels()[0]["experiment_id"] == "BASS-003"
    assert "BASS-003" not in [i["experiment_id"] for i in live.get("/api/admin/labels/queue?limit=1000").json()["items"]]
    c = live.get("/api/admin/labels/queue?status=confirmed").json()
    assert c["total"] == 1 and c["items"][0]["label"] == "extinguished_by_flow_or_N2" and c["items"][0]["labelled_by"] == "tester"
    live.post("/api/admin/labels", json=body | {"label": "unclear"})                      # upsert, no duplicate
    assert len(stored_labels()) == 1
    for bad, code in ((body | {"quote": "this text is not in the notes"}, 422), (body | {"experiment_id": "NOPE"}, 404),
                      (body | {"experiment_id": "WSTF-013"}, 422), (body | {"label": "burned_nicely"}, 422), (body | {"labelled_by": ""}, 422)):
        r = live.post("/api/admin/labels", json=bad)
        assert r.status_code == code and set(r.json()["error"]) == {"code", "message", "details"}, (bad, r.text)


def test_csv_import_service_and_script(live, derived, tmp_path):
    a, b = _ex(live, "BASS-001"), _ex(live, "BASS-002")
    csv_text = ("experiment_id,label,quote,labelled_by\n"
                f"BASS-001,sustained_burn,\"{_first_words(a['flame_behavior_notes'])}\",csv-user\n"
                "BASS-002,sustained_burn,not a real quote,csv-user\n"
                "BASS-004,,,\n")
    from app.services import labels
    r = labels.import_csv(csv_text)
    assert r["imported"] == 1 and len(r["errors"]) == 1 and r["errors"][0]["experiment_id"] == "BASS-002"
    # the script runs end-to-end against a separate derived dir
    f = tmp_path / "labels.csv"
    f.write_text(f"experiment_id,label,quote,labelled_by\nBASS-002,hardware_issue,\"{_first_words(b['flame_behavior_notes'], 2)}\",script-user\n")
    s = get_settings()
    env = {"DATA_DIR": str(tmp_path / "d"), "PATH": "/usr/local/bin:/usr/bin:/bin", "MONGODB_URI": s.mongodb_uri, "MONGODB_DB": s.mongodb_db,
           "LABELS_COLLECTION": s.labels_collection, "DERIVED_COLLECTION": s.derived_collection}
    out = subprocess.run([sys.executable, "scripts/import_labels.py", str(f)], capture_output=True, text=True, env=env, cwd=str(get_settings().data_dir.parent / "scripts" / ".."))
    assert out.returncode == 0 and "imported 1" in out.stdout, out.stdout + out.stderr
    from helpers import stored_labels
    assert {l["experiment_id"]: l["labelled_by"] for l in stored_labels()}["BASS-002"] == "script-user"


# ---------- validation ----------
def _label(live, eid, label):
    e = _ex(live, eid)
    live.post("/api/admin/labels", json={"experiment_id": eid, "label": label, "quote": _first_words(e["flame_behavior_notes"], 3), "labelled_by": "tester"})
    return e


def test_validation_empty_state_shows_pairs(live, derived):
    d = live.get("/api/validation").json()
    assert d["labels_confirmed"] == 0 and d["empty_state_message"] and len(d["saffire_pairs"]) == 9
    assert all(p["microgravity"]["gravity_bucket"] == "microgravity" and p["one_g"]["gravity_bucket"] == "1g" for p in d["saffire_pairs"])
    assert d["correction_model"]["status"] == "not_configured" and d["old_method_test"]["cases"] == []


def test_old_method_counts_and_report(live, derived):
    """Real PMMA data: MOC rows span 14-21 % (variant/pressure dependent), BASS notes span 16.7-22.6 % -> variant-dependent cases, no strict case."""
    from app.services import evidence as ev, validation
    rows = [e for e in ev.material_rows("pmma") if e["source_investigation"] == "BASS" and e["flame_behavior_notes"]]
    mocs = [e["outcome_value"] for e in ev.material_rows("pmma") if e.get("outcome_variable") == "MOC"]
    lo, hi = min(mocs), max(mocs)
    burn = next(e for e in rows if lo <= e["oxygen_pct"] < hi)           # burn below some MOC rows
    ok = next(e for e in rows if e["oxygen_pct"] >= hi)                    # burn at/above every MOC -> consistent
    non = next(e for e in rows if e["oxygen_pct"] > lo and e["experiment_id"] not in (burn["experiment_id"], ok["experiment_id"]))   # non-burn above some rows
    _label(live, burn["experiment_id"], "sustained_burn")
    _label(live, non["experiment_id"], "no_ignition")
    _label(live, ok["experiment_id"], "sustained_burn")
    o = live.get("/api/validation").json()["old_method_test"]
    assert live.get("/api/validation").json()["labels_confirmed"] == 3 and o["materials_evaluated"] == ["pmma"]
    assert o["n_evaluated"] == 3 and o["n_burn_below_moc"] == 0 and o["n_burn_below_moc_variant_dependent"] == 1
    assert o["n_nonburn_above_moc_variant_dependent"] + o["n_nonburn_above_moc"] == 1
    c = {x["experiment_id"]: x for x in o["cases"]}[burn["experiment_id"]]
    assert c["strength"] == "variant_dependent" and c["moc_range_pct"] == [lo, hi] and c["moc_pct"] == hi
    assert c["ug_source_url"] and c["moc_source_url"].startswith("https://ntrs") and c["quote"]
    validation.write_files()
    from helpers import stored_validation
    md = stored_validation()["report_md"]
    assert burn["experiment_id"] in md and "9 pair(s)" in md and "variant-dependent" in md and "Correction model not configured" in md
    from helpers import stored_validation
    d = stored_validation()
    assert d["data"]["labels_confirmed"] == 3 and burn["experiment_id"] in d["report_md"]


def test_old_method_strict_logic_synthetic():
    """Strict cases cannot occur in the current data, so test the logic on synthetic rows."""
    from app.services.validation import old_method_test
    def moc(i, v, p=101.35):
        return {"experiment_id": i, "evidence_type": "flammability_limit_1g_MOC_ULOI", "outcome_variable": "MOC", "outcome_value": v, "pressure_kpa": p,
                "gravity_level": "1g (ground)", "material_variant": "v", "source_ref": "r", "doi": None, "source_file": "https://x"}
    def ug(i, o2, p=100.0):
        return {"experiment_id": i, "gravity_level": "microgravity", "oxygen_pct": o2, "pressure_kpa": p, "evidence_type": "solid_burn_test", "source_ref": "r", "doi": "d", "source_file": "f"}
    rows = [moc("M1", 14.0), moc("M2", 21.0), moc("M3", 25.0, p=50.0), ug("a", 12.0), ug("b", 17.0), ug("c", 23.0), ug("d", 20.0)]
    lab = lambda l: {"label": l, "quote": "q", "labelled_by": "t", "status": "confirmed"}  # noqa: E731
    o = old_method_test({"a": lab("sustained_burn"), "b": lab("sustained_burn"), "c": lab("no_ignition"), "d": lab("hardware_issue")}, {"x": rows})
    assert (o["n_burn_below_moc"], o["n_burn_below_moc_variant_dependent"], o["n_nonburn_above_moc"], o["n_nonburn_above_moc_variant_dependent"]) == (1, 1, 1, 0)
    assert o["n_evaluated"] == 4        # M3 (50 kPa) is not pressure-compatible with the 100 kPa µg rows


def test_suggested_labels_never_count(live, derived):
    from helpers import put_labels
    put_labels([{"experiment_id": "BASS-001", "label": "sustained_burn", "quote": "q", "labelled_by": "x", "status": "suggested"}])
    assert live.get("/api/validation").json()["labels_confirmed"] == 0


def test_correction_check_with_fake_model(live, derived, tmp_path):
    """TEST-ONLY made-up coefficients; shows MAE/max/n are reported and flagged when n is small."""
    s = get_settings(); old = s.correction_models_path
    y = {"models": [{"id": "t", "status": "configured", "citation": "TEST", "page": "0", "equation": "x", "formula": "moc_1g_pct - a * airflow_cm_s",
                     "inputs": ["moc_1g_pct", "airflow_cm_s"], "coefficients": {"a": 0.1}, "valid_range": {"moc_1g_pct": [0, 100], "airflow_cm_s": [0, 50]}}]}
    (tmp_path / "m.yaml").write_text(yaml.safe_dump(y))
    try:
        s.correction_models_path = tmp_path / "m.yaml"
        from app.services import evidence as ev
        e = next(e for e in ev.material_rows("pmma") if e["source_investigation"] == "BASS" and e["flame_behavior_notes"] and e.get("airflow_cm_s") is not None and e["airflow_cm_s"] <= 50)
        _label(live, e["experiment_id"], "sustained_burn")
        c = live.get("/api/validation").json()["correction_model"]
        assert c["status"] == "configured" and c["n_pairs"] == 1 and c["mae_pct_o2"] is not None and c["max_error_pct_o2"] == c["mae_pct_o2"] and "small" in c["note"]
    finally:
        s.correction_models_path = old


# ---------- coverage ----------
def test_pressure_bins():
    from app.services.gaps import pressure_bin
    assert [pressure_bin(x) for x in (0, 59.99, 60, 79.99, 80, 95, 95.01, 101.35, None)] == [0, 0, 1, 1, 2, 2, 3, 3, 4]


def test_coverage_grid(live):
    from app.services import evidence as ev
    d = live.get("/api/coverage/pmma").json()
    rows = [e for e in ev.material_rows("pmma") if ev.o2_coord(e) is not None]
    tot = sum(c["outcomes"] + c["conditions_only"] for b in d["grids"].values() for r in b for c in r)
    assert tot == len(rows)
    n_out = sum(c["outcomes"] for b in d["grids"].values() for r in b for c in r)
    assert n_out == sum(ev.has_outcome(e) for e in rows)
    assert len(d["pressure_axis"]) == 5 and d["pressure_axis"][:4] == ["<60", "60-80", "80-95", ">95"]
    assert all(len(r) == len(d["o2_axis"]) for b in d["grids"].values() for r in b)
    assert {o["preset_id"] for o in d["preset_overlays"]} == {"iss", "intermediate", "exploration", "cev_cert"}
    iss = next(o for o in d["preset_overlays"] if o["preset_id"] == "iss")
    assert d["o2_axis"][iss["o2_index"]] == 21.0 and d["pressure_axis"][iss["pressure_index"]] == ">95"
    assert live.get("/api/coverage/nope").status_code == 404


# ---------- next experiments ----------
def test_next_experiments(live):
    d = live.get("/api/next-experiments?limit=25").json()
    s = d["suggestions"]
    assert s and [x["rank"] for x in s] == list(range(1, len(s) + 1))
    assert [x["score_parts"]["score"] for x in s] == sorted((x["score_parts"]["score"] for x in s), reverse=True)
    assert all(x["label"] == "Suggested test (not a result)" and x["gravity"] == "microgravity" for x in s)
    from app.services import store
    assert not any("liquid" in (store.materials()[x["material_id"]]["kind"] or "") for x in s)
    import math
    for x in s[:6]:                                                   # every suggested cell really has no µg outcome
        g = live.get(f"/api/coverage/{x['material_id']}").json()
        o2i = g["o2_axis"].index(float(math.floor(x["o2_pct"])))
        from app.services.gaps import pressure_bin
        assert g["grids"]["microgravity"][pressure_bin(x["pressure_kpa"])][o2i]["outcomes"] == 0
    p = live.get("/api/next-experiments?preset=exploration").json()
    assert p["suggestions"] and all(x["preset_id"] == "exploration" for x in p["suggestions"])
    assert live.get("/api/next-experiments?preset=zzz").status_code == 422
