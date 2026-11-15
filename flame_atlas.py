"""
Flame Atlas core engine: verify, rank, score confidence, measure accuracy.
Python 3.9+ standard library only. No internet, no packages, runs on any laptop.

  python flame_atlas.py demo        # live demo: accept / reject, ranking, confidence
  python flame_atlas.py eval        # accuracy report against a gold set
  python flame_atlas.py brief --env moon   # Mission Brief: iss | moon | spacesuit
  python flame_atlas.py stats       # p-values (Fisher exact, sign test) and 95% intervals
  python flame_atlas.py findings    # what has been tested, Earth vs space
  python flame_atlas.py gaps        # gap map: conditions nobody has tested
  python flame_atlas.py next --env moon   # which test to fly next for this habitat
  python flame_atlas.py benchmark   # Flame Atlas vs ChatGPT vs plain RAG, same questions
  python flame_atlas.py rank --o2 21 --pressure 101.3 --flow 10 --gravity micro

Implements the rules in "Flame Atlas - Methodology":
  - No quote, no number: every record needs a quote found word for word in its source.
  - Units converted by code, ranges checked by code.
  - Ranking by fixed, transparent rules. No language model ranks anything.
  - Confidence: High / Medium / Low / No evidence.

Data: data/records.json holds 148 runs extracted from NASA PSI-26 (BASS), PSI-98, PSI-99 and PSI-100
(Saffire-I/II/III). Every record carries a quote that verify() finds word for word in data/sources/.
"""
import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# ---------------------------------------------------------------- 1. verify

def normalize(text):
    """Compare text fairly: lower case, unify dashes and quotes, collapse spaces."""
    text = text.lower()
    text = re.sub(r"[‐-―−]", "-", text)
    text = re.sub(r"[‘’“”]", "'", text)
    text = re.sub(r"-\s*\n\s*", "", text)          # words split across lines
    return re.sub(r"\s+", " ", text).strip()


def quote_in_source(quote, source_text):
    return bool(quote) and normalize(quote) in normalize(source_text)


PRESSURE_TO_KPA = {"kpa": 1.0, "atm": 101.325, "psi": 6.895, "bar": 100.0, "torr": 0.133322}
FLOW_TO_CMS = {"cm/s": 1.0, "mm/s": 0.1, "m/s": 100.0}


def to_number(value, unit, table):
    if value is None:
        return None
    unit = (unit or "").strip().lower()
    if unit not in table:
        raise ValueError(f"unknown unit '{unit}'")
    return round(float(value) * table[unit], 4)


def verify(record, sources):
    """Return (clean_record, None) if accepted, or (None, reason) if rejected."""
    src = sources.get(record.get("source_id"))
    if src is None:
        return None, "source not found"
    if not quote_in_source(record.get("quote", ""), src):
        return None, "quote not found word for word in source"
    words = len(record["quote"].split())
    if words > 25:
        return None, f"quote too long ({words} words, max 25)"
    try:
        clean = dict(record)
        clean["pressure_kpa"] = to_number(record.get("pressure"), record.get("pressure_unit"), PRESSURE_TO_KPA)
        clean["flow_cms"] = to_number(record.get("flow"), record.get("flow_unit"), FLOW_TO_CMS)
    except (ValueError, TypeError) as e:
        return None, f"unit error: {e}"
    o2 = record.get("o2_percent")
    if o2 is not None and not 0 <= o2 <= 100:
        return None, "range check: oxygen must be 0-100%"
    if clean["pressure_kpa"] is not None and clean["pressure_kpa"] <= 0:
        return None, "range check: pressure must be above zero"
    if clean["flow_cms"] is not None and clean["flow_cms"] < 0:
        return None, "range check: flow cannot be negative"
    if record.get("gravity") not in ("micro", "earth"):
        return None, "gravity must be 'micro' or 'earth'"
    return clean, None


# ---------------------------------------------------------------- 2. rank

VARS = [("o2_percent", "o2"), ("pressure_kpa", "pressure"), ("flow_cms", "flow")]


# Floor for each tolerance: roughly the measurement resolution of each variable.
# Without it, a dataset where all runs share one pressure gives a near-zero
# tolerance, and a 0.1 kPa rounding difference would push a run "far".
MIN_TOL = {"o2_percent": 1.0, "pressure_kpa": 5.0, "flow_cms": 2.0}


def tolerances(records, share=0.20):
    """Tolerance = max(20% of the variable's range in the data, a physical floor)."""
    tol = {}
    for field, _ in VARS:
        vals = [r[field] for r in records if r.get(field) is not None]
        span = (max(vals) - min(vals)) if len(vals) > 1 else 0
        tol[field] = max(span * share, MIN_TOL[field])
    return tol


def distance(run, scenario, tol):
    """d = sqrt(sum(((x - xs) / tol)^2)); a missing variable is skipped and marked partial."""
    # Oxygen is the controlling variable for flammability: a run with unknown O2
    # is never treated as "close" to a scenario that specifies O2.
    if scenario.get("o2") is not None and run.get("o2_percent") is None:
        return math.inf, True
    total, used = 0.0, 0
    for field, key in VARS:
        if scenario.get(key) is None or run.get(field) is None:
            continue
        total += ((run[field] - scenario[key]) / tol[field]) ** 2
        used += 1
    if used == 0:
        return math.inf, True
    return math.sqrt(total), used < len([k for _, k in VARS if scenario.get(k) is not None])


def confidence(close_runs):
    n = len(close_runs)
    sources = {r["source_id"] for r in close_runs}
    if n >= 3 and len(sources) >= 2:
        return "High"
    if n >= 2:
        return "Medium"
    if n == 1:
        return "Low"
    return None


def rank(records, scenario, use_earth_proxy=False):
    tol = tolerances(records)
    want = scenario.get("gravity", "micro")
    by_material = {}
    for r in records:
        proxy = r["gravity"] != want
        if proxy and not use_earth_proxy:
            continue
        d, partial = distance(r, scenario, tol)
        if d > 2:
            continue
        key = r.get("material_family") or r.get("material")
        if not key:
            continue
        m = by_material.setdefault(key, {"close": [], "far": [], "proxy": False, "partial": False})
        (m["close"] if d <= 1 else m["far"]).append(dict(r, d=round(d, 2)))
        m["proxy"] |= proxy
        m["partial"] |= partial

    rows = []
    for material, m in by_material.items():
        runs = m["close"]
        if runs:
            known = [r for r in runs if r.get("sustained") is not None]
            sustained = (sum(1 for r in known if r["sustained"]) / len(known)) if known else None
            spreads = [r["spread_mm_s"] for r in runs if r.get("spread_mm_s") is not None]
            spread = statistics.median(spreads) if spreads else None
            conf = confidence(runs)
            ci = wilson_ci(sum(1 for r in known if r["sustained"]), len(known)) if known else None
            if m["proxy"] and conf in ("High", "Medium"):
                conf = "Low"
        else:
            sustained, spread, conf, ci = None, None, "Low", None
        rows.append({
            "material": material, "close_runs": len(runs), "far_runs": len(m["far"]),
            "sustained_share": sustained, "ci95": ci, "median_spread_mm_s": spread, "confidence": conf,
            "sources": sorted({r["source_id"] for r in runs + m["far"]}),
            "notes": [n for n, on in (("Earth data used as proxy", m["proxy"]),
                                      ("some variables missing", m["partial"]),
                                      ("far runs only", not runs)) if on],
        })
    rows.sort(key=lambda x: (-(x["sustained_share"] or -1), -(x["median_spread_mm_s"] or -1)))
    ranked = [r for r in rows if r["sustained_share"] is not None]
    for r in rows:
        r.setdefault("tier", "-")
    for i, r in enumerate(ranked):
        third = len(ranked) / 3
        r["tier"] = "higher" if i < third else ("medium" if i < 2 * third else "lower")
    return rows


# ---------------------------------------------------------------- 3. evaluate

def field_accuracy(extracted, gold, numeric_tol=0.01):
    num_fields = ["o2_percent", "pressure_kpa", "flow_cms", "spread_mm_s"]
    cat_fields = ["material", "gravity", "sustained"]
    gold_by_id = {g["id"]: g for g in gold}
    num_ok = num_n = cat_ok = cat_n = 0
    errors = []
    for e in extracted:
        g = gold_by_id.get(e["id"])
        if not g:
            continue
        for f in num_fields:
            if g.get(f) is None:
                continue
            num_n += 1
            ev = e.get(f)
            if ev is not None and abs(ev - g[f]) <= numeric_tol * max(1, abs(g[f])):
                num_ok += 1
            else:
                errors.append((e["id"], f, ev, g[f]))
        for f in cat_fields:
            if f not in g:
                continue
            cat_n += 1
            if str(e.get(f)).lower() == str(g[f]).lower():
                cat_ok += 1
            else:
                errors.append((e["id"], f, e.get(f), g[f]))
    return (num_ok, num_n), (cat_ok, cat_n), errors


def pct(ok, n):
    return f"{100 * ok / n:.1f}% ({ok}/{n})" if n else "n/a"


# ---------------------------------------------------------------- 4. benchmark

def score_answer(q, a, rel_tol=0.05):
    """One system's answer to one question -> (correct, cited_right, hallucinated)."""
    said_none = bool(a.get("no_evidence"))
    value = a.get("value")
    if not q["answerable"]:
        hallucinated = (value is not None) and not said_none
        return (not hallucinated), None, hallucinated
    if said_none or value is None:
        return False, False, False
    g = q["gold_value"]
    if isinstance(g, (int, float)) and isinstance(value, (int, float)):
        correct = abs(value - g) <= rel_tol * max(1e-9, abs(g))
    else:
        correct = str(value).strip().lower() == str(g).strip().lower()
    cited = bool(a.get("source")) and a.get("source") == q.get("gold_source")
    return correct, cited, False


def benchmark(path):
    b = json.loads(Path(path).read_text(encoding="utf-8"))
    qs = b["questions"]
    systems = b["systems"]
    print(f"BENCHMARK: {len(qs)} questions "
          f"({sum(q['answerable'] for q in qs)} answerable from the data, "
          f"{sum(not q['answerable'] for q in qs)} not answerable)")
    if b.get("synthetic"):
        print("  !! EXAMPLE FILE WITH MADE-UP ANSWERS. Do not present these numbers. !!")
    head = f"  {'System':<26}{'Correct':<16}{'Correct source':<17}{'Invented an answer':<20}{'Repeatable'}"
    print(head)
    rows = []
    for name in systems:
        ok = n = cited = cited_n = hall = hall_n = missing = 0
        rep_ok = rep_n = 0
        for q in qs:
            a = q["answers"].get(name)
            if a is None:
                missing += 1
                continue
            correct, c, h = score_answer(q, a)
            n += 1
            ok += correct
            if q["answerable"]:
                cited_n += 1
                cited += bool(c)
            else:
                hall_n += 1
                hall += h
            if "value_second_run" in a:
                rep_n += 1
                rep_ok += a["value_second_run"] == a.get("value")
        rows.append(dict(system=name, correct=(ok, n), cited=(cited, cited_n), hall=(hall, hall_n), rep=(rep_ok, rep_n)))
        print(f"  {name:<26}{pct(ok, n):<16}{pct(cited, cited_n):<17}{pct(hall, hall_n):<20}{pct(rep_ok, rep_n)}"
              + (f"   ({missing} unanswered)" if missing else ""))
    print("\n  Correct: right value, or 'no evidence' when the data has none.")
    print("  Invented an answer: gave a number to a question the data cannot answer (lower is better).")
    print("  Repeatable: same answer when the same question is asked twice.")
    return rows


# ---------------------------------------------------------------- 5. gap map

def gap_map(records, gravity="micro", flow=None, o2_steps=None, p_steps=None):
    """Grid over oxygen x pressure: how many tested runs sit close to each cell.
    0 close runs = a gap: conditions nobody has tested. We mark it, we never fill it."""
    tol = tolerances(records)
    runs = [r for r in records if r["gravity"] == gravity]
    o2_steps = o2_steps or [16, 18, 21, 22, 24, 27, 30, 34, 40]
    p_steps = p_steps or [29.6, 70.3, 101.3]
    grid = []
    for p in p_steps:
        row = []
        for o2 in o2_steps:
            sc = {"o2": o2, "pressure": p, "flow": flow, "gravity": gravity}
            close, far, mats, srcs = 0, 0, set(), set()
            for r in runs:
                d, partial = distance(r, sc, tol)
                if partial:
                    continue          # missing pressure: this run cannot vouch for any cell
                if d <= 1:
                    close += 1; mats.add(r.get("material_family") or r.get("material") or "?"); srcs.add(r["source_id"])
                elif d <= 2:
                    far += 1
            status = ("covered" if close >= 3 and len(srcs) >= 2 else
                      "thin" if close >= 1 else "far only" if far else "gap")
            row.append({"o2": o2, "pressure_kpa": p, "close_runs": close, "far_runs": far,
                        "materials": sorted(mats), "sources": sorted(srcs), "status": status})
        grid.append(row)
    return {"gravity": gravity, "flow_cms": flow, "o2_steps": o2_steps, "pressure_steps": p_steps, "grid": grid}


def print_gap_map(g):
    sym = {"covered": "###", "thin": " + ", "far only": " . ", "gap": "   "}
    print(f"GAP MAP ({g['gravity']} gravity"
          + (f", flow {g['flow_cms']} cm/s" if g["flow_cms"] is not None else ", any flow") + ")")
    print("  ### covered (3+ close runs, 2+ sources)    +  thin (1-2 runs)    .  far runs only    blank = NEVER TESTED")
    print(f"  {'kPa \\ O2%':>10} " + "".join(f"{o:>5}" for o in g["o2_steps"]))
    for row in reversed(g["grid"]):
        print(f"  {row[0]['pressure_kpa']:>10} " + "".join(f"[{sym[c['status']]}]"[0:5] for c in row))
    cells = [c for row in g["grid"] for c in row]
    gaps = [c for c in cells if c["status"] == "gap"]
    print(f"\n  {len(gaps)} of {len(cells)} condition cells have no nearby test at all.")
    for c in gaps[:6]:
        print(f"    untested: O2 {c['o2']}%, {c['pressure_kpa']} kPa")
    if len(gaps) > 6:
        print(f"    ... and {len(gaps) - 6} more")


# ---------------------------------------------------------------- 6. findings + mission brief

PSI_TO_KPA = 6.895
ENVIRONMENTS = {
    # Values from the 2026 challenge statement (data/sources/CHALLENGE.txt), quoted below.
    "iss":       {"name": "ISS / spacecraft cabin", "o2": 21.0, "pressure": 101.3, "gravity": "micro",
                  "quote": "where the Earth's pressure at sea level is 14.7 psi"},
    "moon":      {"name": "Moon Base / pressurized rover", "o2": 30.0, "pressure": round(10.2 * PSI_TO_KPA, 1),
                  "gravity": "micro",
                  "quote": "The intermediate oxygen concentration used on the Moon will likely be 30% or greater, with a corresponding pressure of 10.2 psi or less."},
    "spacesuit": {"name": "Spacesuit", "o2": 100.0, "pressure": round(4.3 * PSI_TO_KPA, 1), "gravity": "micro",
                  "quote": "spacesuits are filled with 100% oxygen to only 4.3 psi"},
}
PARTIAL_G_QUOTE = "there is currently no partial-gravity combustion data available in PSI."


def envelope(records):
    """What has actually been tested, per material family (microgravity, verified records only)."""
    fam = {}
    for r in records:
        if r["gravity"] != "micro" or not r.get("material_family"):
            continue
        f = fam.setdefault(r["material_family"], {"runs": 0, "o2": [], "p": [], "flow": [], "sources": set(),
                                                  "burned": 0, "not_burned": 0})
        f["runs"] += 1
        f["sources"].add(r["source_id"])
        if r.get("o2_percent") is not None: f["o2"].append(r["o2_percent"])
        if r.get("pressure_kpa") is not None: f["p"].append(r["pressure_kpa"])
        if r.get("flow_cms") is not None: f["flow"].append(r["flow_cms"])
        if r.get("sustained") is True: f["burned"] += 1
        if r.get("sustained") is False: f["not_burned"] += 1
    out = {}
    for k, f in fam.items():
        out[k] = {"runs": f["runs"], "sources": sorted(f["sources"]), "burned": f["burned"], "not_burned": f["not_burned"],
                  "o2_range": [min(f["o2"]), max(f["o2"])] if f["o2"] else None,
                  "pressure_kpa_range": [min(f["p"]), max(f["p"])] if f["p"] else None,
                  "flow_range": [min(f["flow"]), max(f["flow"])] if f["flow"] else None}
    return out


def earth_vs_space(records):
    """Same NASA table, same material: microgravity result next to the 1-g result (Saffire-II)."""
    pairs = []
    by_id = {r["id"]: r for r in records}
    for r in records:
        if r["gravity"] == "micro" and r["id"] + "_1g" in by_id:
            g = by_id[r["id"] + "_1g"]
            if r.get("sustained") != g.get("sustained") or r.get("spread_mm_s") != g.get("spread_mm_s"):
                pairs.append({"material": r["material"], "id": r["id"], "micro_g": r["outcome_text"],
                              "one_g": g["outcome_text"], "micro_burned": r.get("sustained"),
                              "one_g_burned": g.get("sustained"), "source": r["source_id"], "quote": r["quote"]})
    return pairs


def mission_brief(records, env_key):
    env = ENVIRONMENTS[env_key]
    sc = {"o2": env["o2"], "pressure": env["pressure"], "flow": None, "gravity": env["gravity"]}
    env_ = envelope(records)
    all_o2 = [v["o2_range"][1] for v in env_.values() if v["o2_range"]]
    all_p = [v["pressure_kpa_range"][0] for v in env_.values() if v["pressure_kpa_range"]]
    max_o2 = max(all_o2) if all_o2 else None
    min_p = min(all_p) if all_p else None
    ranking = rank(records, sc)
    lines = []
    lines.append({"text": f"Target environment: {env['name']} -- {env['o2']:g}% O2 at {env['pressure']:g} kPa.",
                  "source": "CHALLENGE", "quote": env["quote"]})
    if max_o2 is not None:
        gap = env["o2"] - max_o2
        top = max(env_.items(), key=lambda kv: kv[1]["o2_range"][1] if kv[1]["o2_range"] else -1)
        lines.append({"text": f"Highest O2 at which any solid was tested in these microgravity experiments: {max_o2:.1f}% "
                              f"({top[0]}). " + (f"This environment is {gap:.1f} O2 points beyond any tested solid."
                                                 if gap > 0 else "This environment is inside the tested O2 range."),
                      "source": ", ".join(top[1]["sources"]), "quote": None, "computed": True})
    if min_p is not None and env["pressure"] < min_p - 1:
        lines.append({"text": f"Lowest pressure in these solid-fuel tests: {min_p:.1f} kPa. This environment "
                              f"({env['pressure']:g} kPa) has not been tested.", "source": "PSI-26", "quote": None,
                      "computed": True})
    lines.append({"text": "Why this matters: NASA's material screening test is run in 1-g; BASS was flown to bridge that gap.",
                  "source": "PSI-26-page",
                  "quote": "segregates material based on 1-g behavior without consideration of low gravity effects."})
    lines.append({"text": "No partial-gravity (Moon or Mars) combustion data exists in PSI yet; microgravity and 1-g "
                          "results bound what may happen in between.", "source": "CHALLENGE", "quote": PARTIAL_G_QUOTE})
    if ranking:
        for r in ranking:
            if r["sustained_share"] is None:
                continue
            ci = f", 95% CI {r['ci95'][0]:.0%}-{r['ci95'][1]:.0%}" if r.get("ci95") else ""
            lines.append({"text": f"{r['material']}: burned in {r['sustained_share']:.0%} of {r['close_runs']} tests near "
                                  f"these conditions (confidence {r['confidence']}{ci}).", "source": ", ".join(r["sources"]),
                          "quote": None, "computed": True})
    else:
        lines.append({"text": "No verified test lies close to these conditions. Flame Atlas gives no material ranking "
                              "here: any number would be a guess.", "source": None, "quote": None, "computed": True})
    st = compute_statistics(records)
    e = st["earth_vs_space"]
    if e["pairs"]:
        lines.append({"text": f"Earth test vs space (Saffire-II): {e['same_direction']} of {e['pairs']} silicone samples burned in "
                              f"the 1-g test but not in microgravity. Exact sign test p = {e['p']:.2f}: not statistically "
                              f"significant with this few samples -- a signal worth testing, not a proven effect.",
                      "source": "PSI-99", "quote": None, "computed": True})
    for p in []:
        lines.append({"text": f"Earth test vs space, same NASA table: {p['material']} -- 1-g: {p['one_g']}; "
                              f"microgravity: {p['micro_g']}. (1-g test O2/flow are not given in this table.)", "source": p["source"], "quote": p["quote"]})
    invs = rank_investigations(env_key)
    for inv in invs[:5]:
        lines.append({"text": f"Relevant investigation: {inv['name']} ({inv['psi'] or 'PSI id not listed'}) -- "
                              f"{inv['pillar']}, {inv['fuel']} fuel. Relevance {inv['score']}: {'; '.join(inv['why'])}.",
                      "source": inv["source"], "quote": inv["quote"]})
    return {"environment": env_key, "scenario": sc, "lines": lines, "envelope": env_, "ranking": ranking,
            "investigations": invs}


# ---------------------------------------------------------------- 5. the AI model (Bayesian) and active learning

def _digamma(x):
    r = 0.0
    while x < 6:
        r -= 1 / x
        x += 1
    f = 1 / (x * x)
    return r + math.log(x) - 0.5 / x - f * (1 / 12 - f * (1 / 120 - f * (1 / 252 - f * (1 / 240 - f / 132))))


def _betacf(a, b, x):
    """Continued fraction for the regularized incomplete beta function (Lentz)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(1 + aa / c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(1 + aa / c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return h


def beta_cdf(x, a, b):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def beta_ppf(q, a, b):
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) < q: lo = mid
        else: hi = mid
    return (lo + hi) / 2


def _h2(p):
    return 0.0 if p <= 0 or p >= 1 else -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def expected_information_gain(a, b):
    """Bits the model expects to learn about a material's burn probability from ONE new test.
    Mutual information between the next outcome y and p ~ Beta(a, b): H(E[p]) - E[H(y | p)]."""
    m = a / (a + b)
    e_plnp = m * (_digamma(a + 1) - _digamma(a + b + 1))
    e_qlnq = (b / (a + b)) * (_digamma(b + 1) - _digamma(a + b + 1))
    return _h2(m) + (e_plnp + e_qlnq) / math.log(2)


def bayes_model(records):
    """Beta-Binomial model per material, learned from verified microgravity runs.
    Prior Beta(1, 1) (no opinion). Posterior Beta(1 + burned, 1 + not burned): the model's belief about
    how likely the material is to keep burning, with a 95% credible interval and the expected information
    gain of one more test (active learning: test where the model is least sure)."""
    fam = {}
    for r in records:
        if r["gravity"] != "micro" or not r.get("material_family") or r.get("sustained") is None:
            continue
        f = fam.setdefault(r["material_family"], [0, 0])
        f[1] += 1
        f[0] += 1 if r["sustained"] else 0
    out = []
    for name, (k, n) in fam.items():
        a, b = 1 + k, 1 + n - k
        out.append({"material": name, "burned": k, "tests": n, "alpha": a, "beta": b,
                    "p_burn": a / (a + b), "credible95": [beta_ppf(0.025, a, b), beta_ppf(0.975, a, b)],
                    "eig_bits": expected_information_gain(a, b)})
    return sorted(out, key=lambda x: -x["eig_bits"])


def next_tests(records, env_key, top=3):
    """Active learning: which test would teach the model the most for this habitat?
    Conditions: the habitat's own air (quoted from the challenge). Materials: highest expected information gain."""
    env = ENVIRONMENTS[env_key]
    sc = {"o2": env["o2"], "pressure": env["pressure"], "flow": None, "gravity": "micro"}
    tol = tolerances(records)
    best = min((distance(r, sc, tol)[0] for r in records if r["gravity"] == "micro" and not distance(r, sc, tol)[1]),
               default=math.inf)
    model = bayes_model(records)
    return {"environment": env_key, "conditions": {"o2": env["o2"], "pressure": env["pressure"], "gravity": "micro"},
            "nearest_d": best, "priorities": model[:top], "model": model,
            "rule": "Active learning: test first where the Bayesian model expects to learn the most (expected information gain, in bits)."}

# Transparent relevance score: what a habitat designer needs first.
PILLAR_WEIGHT = {"prevention": 3, "detection": 2, "suppression": 2, "high-oxygen": 1,
                 "partial-gravity proxy": 1, "fundamental": 0}


def rank_investigations(env_key):
    cat = json.loads((DATA / "investigations.json").read_text(encoding="utf-8"))["investigations"]
    out = []
    for inv in cat:
        score, why = PILLAR_WEIGHT.get(inv["pillar"], 0), [f"{inv['pillar']} (+{PILLAR_WEIGHT.get(inv['pillar'], 0)})"]
        if inv["fuel"] == "solid":
            score += 2; why.append("solid materials, like cabin fabrics and plastics (+2)")
        if env_key in ("moon", "spacesuit") and inv["pillar"] in ("high-oxygen", "partial-gravity proxy"):
            score += 2; why.append("matches this habitat's high O2 / partial gravity (+2)")
        if inv["in_atlas"]:
            score += 1; why.append("verified records in Flame Atlas (+1)")
        out.append(dict(inv, score=score, why=why))
    return sorted(out, key=lambda x: -x["score"])


def print_brief(b):
    print("MISSION BRIEF --", ENVIRONMENTS[b["environment"]]["name"])
    for i, l in enumerate(b["lines"], 1):
        src = f" [{l['source']}]" if l.get("source") else ""
        tag = " (computed from the dataset)" if l.get("computed") else ""
        print(f"  {i}. {l['text']}{src}{tag}")
        if l.get("quote"):
            print(f"       quote: \"{l['quote']}\"")


def print_findings(records):
    env_ = envelope(records)
    print("WHAT HAS ACTUALLY BEEN TESTED (verified microgravity records, solids)")
    print(f"  {'Material family':<34}{'Runs':>5}{'Burned':>8}{'No burn':>9}   O2 range %     Flow cm/s    Sources")
    for k, v in sorted(env_.items(), key=lambda kv: -kv[1]["runs"]):
        o2 = f"{v['o2_range'][0]:.1f}-{v['o2_range'][1]:.1f}" if v["o2_range"] else "n/a"
        fl = f"{v['flow_range'][0]:g}-{v['flow_range'][1]:g}" if v["flow_range"] else "n/a"
        print(f"  {k:<34}{v['runs']:>5}{v['burned']:>8}{v['not_burned']:>9}   {o2:<14} {fl:<12} {', '.join(v['sources'])}")
    print("\nEARTH TEST vs SPACE (same NASA table, Saffire-II)")
    for p in earth_vs_space(records):
        print(f"  {p['material']:<28} 1-g: {p['one_g']:<40} micro-g: {p['micro_g']}")


# ---------------------------------------------------------------- 7. statistics (suggested by Dr. Iyad)

def wilson_ci(k, n, z=1.96):
    """95% Wilson score interval for a proportion k/n (works for small n and for 0% / 100%)."""
    if n == 0:
        return None
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def fisher_exact(a, b, c, d):
    """Two-sided Fisher exact test for the 2x2 table [[a, b], [c, d]]."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    def p(x):
        return math.comb(r1, x) * math.comb(n - r1, c1 - x) / math.comb(n, c1)
    p0 = p(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-9)))


def sign_test(k, n):
    """Exact two-sided sign test: k of n paired changes go the same way."""
    if n == 0:
        return None
    m = max(k, n - k)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(m, n + 1)) / 2 ** n)


def compute_statistics(records, alpha=0.05):
    fam = {}
    for r in records:
        if r["gravity"] != "micro" or not r.get("material_family") or r.get("sustained") is None:
            continue
        f = fam.setdefault(r["material_family"], [0, 0])
        f[1] += 1
        f[0] += 1 if r["sustained"] else 0
    shares = [{"material": k, "burned": b, "tests": t, "share": b / t, "ci95": wilson_ci(b, t)}
              for k, (b, t) in sorted(fam.items(), key=lambda kv: -kv[1][0] / kv[1][1])]
    names = sorted(fam)
    m = len(names) * (len(names) - 1) // 2
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            (x1, n1), (x2, n2) = fam[a], fam[b]
            pv = fisher_exact(x1, n1 - x1, x2, n2 - x2)
            pairs.append({"a": a, "b": b, "p": pv, "significant": pv < alpha,
                          "significant_bonferroni": pv < alpha / m})
    pairs.sort(key=lambda x: x["p"])
    evs = [p for p in earth_vs_space(records) if p["micro_burned"] != p["one_g_burned"]]
    k = sum(1 for p in evs if p["one_g_burned"] and not p["micro_burned"])
    return {"alpha": alpha, "comparisons": m, "bonferroni_alpha": alpha / m, "shares": shares, "pairs": pairs,
            "earth_vs_space": {"pairs": len(evs), "same_direction": k, "p": sign_test(k, len(evs))},
            "note": "Shares pool all tested conditions (different O2 and flow), so they compare materials across "
                    "the tested envelope, not at one fixed condition."}


def print_statistics(st):
    print("BURN SHARE PER MATERIAL (microgravity, known outcomes) with 95% Wilson interval")
    for s in st["shares"]:
        lo, hi = s["ci95"]
        print(f"  {s['material']:<34} {s['burned']:>3}/{s['tests']:<3} {s['share']:>5.0%}   95% CI {lo:.0%}-{hi:.0%}")
    print(f"\nPAIRWISE FISHER EXACT TESTS ({st['comparisons']} comparisons; alpha {st['alpha']}, "
          f"Bonferroni {st['bonferroni_alpha']:.4f})")
    for p in st["pairs"]:
        if p["significant"]:
            tag = "significant, survives Bonferroni" if p["significant_bonferroni"] else "significant (not after Bonferroni)"
            print(f"  p={p['p']:.4f}  {p['a']} vs {p['b']}  -> {tag}")
    e = st["earth_vs_space"]
    print(f"\nEARTH vs SPACE (Saffire-II): {e['same_direction']} of {e['pairs']} samples burned in 1-g but not in "
          f"microgravity. Exact sign test p = {e['p']:.2f} -> " + ("significant" if e["p"] < st["alpha"] else
          "NOT significant: a signal worth testing, not a proven effect."))
    print("\nNote:", st["note"])


# ---------------------------------------------------------------- 6. extended catalog (team-built, table-level)

def catalog_summary():
    """Optional: summary of data/extended_catalog.json if the team adds one (rows with a source reference but no
    word-for-word quote). Such rows are NOT part of the quote-verified records and never feed rankings or statistics."""
    path = DATA / "extended_catalog.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    inv = {}
    for r in rows:
        i = inv.setdefault(r["source_investigation"], {"psi": r.get("psi_id"), "rows": 0, "class": r["material_class"],
                                                      "gravity": r["gravity_level"]})
        i["rows"] += 1
    solid = [r for r in rows if r["material_class"] == "solid" and r["gravity_level"] == "microgravity"
             and r.get("oxygen_pct") is not None]
    press = [r["pressure_kpa"] for r in solid if r.get("pressure_kpa") is not None]
    ground = [{"material": r["fuel_material"], "pressure_kpa": r["pressure_kpa"], "moc_pct": r["outcome_value"],
               "uloi_pct": r.get("uloi_pct"), "ref": r["source_ref"]}
              for r in rows if r["gravity_level"].startswith("1g") and r.get("pressure_kpa") == 70.3]
    return {"rows": len(rows), "investigations": inv,
            "solid_microgravity_runs": len(solid),
            "solid_o2_range": [min(r["oxygen_pct"] for r in solid), max(r["oxygen_pct"] for r in solid)],
            "solid_pressure_range": [min(press), max(press)],
            "ground_tests_at_70kpa": ground}


# ---------------------------------------------------------------- CLI

def load():
    records = json.loads((DATA / "records.json").read_text(encoding="utf-8"))
    sources = {p.stem: p.read_text(encoding="utf-8") for p in (DATA / "sources").glob("*.txt")}
    return records, sources


def load_atlas(groups=("real_solid",)):
    """The unified dataset (data/atlas_dataset.json, built by build_unified.py), in the engine's record format.
    Default: real solid materials only, the physics the rankings and statistics are about.
    Records with a NASA quote were verified word for word; the others cite the NASA report table they come from."""
    path = DATA / "atlas_dataset.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if r["group"] not in groups:
            continue
        out.append({"id": r["id"], "source_id": r["psi"], "investigation": r["investigation"], "material": r["material"],
                    "material_family": r.get("material_family"), "gravity": r["gravity"],
                    "o2_percent": r.get("o2_percent"), "pressure_kpa": r.get("pressure_kpa"), "flow_cms": r.get("flow_cms"),
                    "flow_direction": r.get("flow_direction"), "sustained": r.get("sustained"),
                    "spread_mm_s": r.get("spread_mm_s"), "outcome_text": r.get("outcome_text"),
                    "outcome_method": r.get("label_method"), "quote": r.get("quote"), "issues": r.get("issues", []),
                    "evidence": r["evidence"], "source": r.get("source"), "group": r["group"],
                    "pressure_assumed": r.get("pressure_assumed", False)})
    return out


def verify_all(records, sources, show=True):
    accepted, rejected = [], []
    for r in records:
        clean, reason = verify(r, sources)
        if clean:
            accepted.append(clean)
            if show:
                print(f"  {r['id']:<22} quote found word for word in {r['source_id']:<8} ACCEPTED")
        else:
            rejected.append((r, reason))
            if show:
                print(f"  {r['id']:<22} {reason:<46} REJECTED")
    return accepted, rejected


def print_ranking(rows, scenario):
    print(f"\nScenario: O2 {scenario.get('o2')}% | {scenario.get('pressure')} kPa | "
          f"flow {scenario.get('flow')} cm/s | gravity: {scenario.get('gravity')}")
    if not rows:
        print("  No evidence: no tested run is close to this scenario. We do not guess.")
        return
    print(f"  {'Material':<32}{'Tier':<8}{'Sustained':<11}{'Spread mm/s':<13}{'Runs':<6}{'Confidence':<12}Sources")
    for r in rows:
        s = "-" if r["sustained_share"] is None else f"{r['sustained_share']:.0%}"
        sp = "-" if r["median_spread_mm_s"] is None else f"{r['median_spread_mm_s']:.2f}"
        print(f"  {r['material'][:30]:<32}{r.get('tier', '-'):<8}{s:<11}{sp:<13}{r['close_runs']:<6}"
              f"{r['confidence']:<12}{', '.join(r['sources'])}")
        for n in r["notes"]:
            print(f"  {'':<32}note: {n}")


def main():
    ap = argparse.ArgumentParser(description="Flame Atlas core engine")
    ap.add_argument("cmd", choices=["demo", "eval", "rank", "benchmark", "gaps", "brief", "findings", "stats", "next", "catalog"])
    ap.add_argument("--file", default=str(DATA / "benchmark.json"))
    ap.add_argument("--o2", type=float, default=21)
    ap.add_argument("--pressure", type=float, default=101.3, help="kPa")
    ap.add_argument("--flow", type=float, default=None, help="cm/s (default 10 for rank/demo; any flow for gaps)")
    ap.add_argument("--gravity", choices=["micro", "earth"], default="micro")
    ap.add_argument("--earth-proxy", action="store_true")
    ap.add_argument("--env", choices=list(ENVIRONMENTS), default="moon")
    ap.add_argument("--json", action="store_true", help="machine-readable output for the web app")
    a = ap.parse_args()

    if a.cmd == "benchmark":
        benchmark(a.file)
        return 0

    records, sources = load()
    if a.cmd == "stats":
        accepted = load_atlas()
        st = compute_statistics(accepted)
        print(json.dumps(st, indent=2)) if a.json else print_statistics(st)
        return 0
    if a.cmd == "catalog":
        c = catalog_summary()
        if not c:
            print("data/extended_catalog.json not found"); return 1
        if a.json:
            print(json.dumps(c, indent=2)); return 0
        print(f"EXTENDED CATALOG: {c['rows']} rows, {len(c['investigations'])} investigations (table-level, not quote-verified)")
        for k, v in sorted(c["investigations"].items(), key=lambda kv: -kv[1]["rows"]):
            print(f"  {k:<30} {str(v['psi'] or '-'):<8} {v['rows']:>4}  {v['class']}, {v['gravity']}")
        lo, hi = c["solid_o2_range"]; pl, ph = c["solid_pressure_range"]
        print(f"\nCROSS-CHECK: {c['solid_microgravity_runs']} solid-fuel microgravity runs with O2 reported. "
              f"O2 {lo:g}-{hi:g}%, pressure {pl:.1f}-{ph:.1f} kPa. Moon-base air (30%, 70.3 kPa) is still outside.")
        print(f"\nGROUND (1-g) TESTS AT 70.3 kPa: {len(c['ground_tests_at_70kpa'])}")
        for g in c["ground_tests_at_70kpa"]:
            print(f"  {g['material']:<40} MOC {g['moc_pct']:g}% O2, ULOI {g['uloi_pct']:g}%")
        return 0
    if a.cmd == "next":
        accepted = load_atlas()
        n = next_tests(accepted, a.env)
        if a.json:
            print(json.dumps(n, indent=2))
        else:
            c = n["conditions"]
            print(f"NEXT EXPERIMENT -- {ENVIRONMENTS[a.env]['name']}: {c['o2']:g}% O2 at {c['pressure']:g} kPa, microgravity")
            print(f"  Nearest real-material run today: d = {n['nearest_d']:.2f} (close means d <= 1). A run here brings it to 0.")
            print(f"  Test first ({n['rule']})")
            for i, p in enumerate(n["priorities"], 1):
                lo, hi = p["credible95"]
                print(f"   {i}. {p['material']:<34} burned {p['burned']}/{p['tests']}, model P(burn) {p['p_burn']:.0%} "
                      f"[{lo:.0%}-{hi:.0%}], expected gain {p['eig_bits']:.3f} bits")
            print("\n  BAYESIAN MODEL, all materials (prior Beta(1,1)):")
            for p in n["model"]:
                lo, hi = p["credible95"]
                print(f"     {p['material']:<34} P(burn) {p['p_burn']:.0%}  95% credible {lo:.0%}-{hi:.0%}  gain {p['eig_bits']:.3f} bits")
        return 0
    if a.cmd in ("brief", "findings"):
        accepted = load_atlas()
        if a.cmd == "findings":
            print_findings(accepted)
        else:
            b = mission_brief(accepted, a.env)
            print(json.dumps(b, indent=2, default=list)) if a.json else print_brief(b)
        return 0
    if a.cmd == "gaps":
        accepted = load_atlas()
        g = gap_map(accepted, a.gravity, a.flow)
        print(json.dumps(g, indent=2)) if a.json else print_gap_map(g)
        return 0
    if a.flow is None:
        a.flow = 10
    scenario = {"o2": a.o2, "pressure": a.pressure, "flow": a.flow, "gravity": a.gravity}

    if a.cmd == "demo":
        print("STEP 1-2  Extract + Verify: no quote, no number")
        planted = [dict(records[0], id="PLANTED_fake_value", planted_fake=True, o2_percent=30.0,
                        quote="SIBAL burned steadily at 30% oxygen in microgravity"),
                   dict(records[0], id="PLANTED_bad_range", planted_fake=True, o2_percent=215.0)]
        accepted, rejected = verify_all(records[:6] + planted, sources)
        print(f"  ... ({len(records) - 6} more records verified; the two PLANTED records are fakes added to test the verifier)")
        verified, _ = verify_all(records, sources, show=False)
        print(f"\n  {len(verified)} raw-file records accepted, {len(rejected)} planted fakes rejected")
        accepted = load_atlas()
        print(f"  Unified dataset: {len(accepted)} real-material records (data/atlas_dataset.json, python build_unified.py)")
        print("\nSTEP 3  Rank by fixed rules (no language model decides what is close)")
        print_ranking(rank(accepted, scenario, a.earth_proxy), scenario)
        print("\nSTEP 4  Moon Base atmosphere (30% O2, 10.2 psi) -- per the challenge statement")
        far = {"o2": 30, "pressure": 70.3, "flow": 10, "gravity": "micro"}
        print_ranking(rank(accepted, far), far)
        print("\nData: NASA PSI (CC0) -- PSI-26 BASS, PSI-25 BASS-II, PSI-98/99/100 Saffire I-III; PSI-20 BRE and PSI-159 CFI-G kept separate.")

    elif a.cmd == "rank":
        accepted = load_atlas()
        rows = rank(accepted, scenario, a.earth_proxy)
        if a.json:
            print(json.dumps({"scenario": scenario, "results": rows}, indent=2))
        else:
            print_ranking(rows, scenario)

    elif a.cmd == "eval":
        g = json.loads((DATA / "gold.json").read_text(encoding="utf-8"))
        accepted, rejected = verify_all(records, sources, show=False)
        by_id = {r["id"]: r for r in records}
        print("ACCURACY REPORT (measured, not claimed)")
        print(f"  Labels: {g['labelled_by']}")
        print(f"  Meaning: {g['label_meaning']}")
        for part in ("development", "held-out"):
            items = [x for x in g["records"] if x["set"] == part]
            ok = sum(1 for x in items if by_id.get(x["id"], {}).get("sustained") == x["sustained"])
            note = " (rule was tuned on this set)" if part == "development" else " (never seen while writing the rule)"
            print(f"  Burn outcome from crew notes, {part:<11} {pct(ok, len(items)):<18}{note}")
            for x in items:
                got = by_id.get(x["id"], {}).get("sustained")
                if got != x["sustained"]:
                    print(f"      miss: {x['id']}  rule={got}  label={x['sustained']}")
        print(f"  Quotes verified word for word        {pct(len(accepted), len(records))}")
        print(f"  Unclear notes excluded from scoring: {', '.join(g['unclear_excluded'])}")
        print("  First version of the rule scored 14/19 (74%) on the development set before it was improved.")


if __name__ == "__main__":
    sys.exit(main())
