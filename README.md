# Flame Atlas

**A verified map of what NASA has tested about fire in space, and where that evidence ends.**
Team Orion · NASA Space Apps Challenge 2026 · Challenge: *Flame in Freefall* · Nablus local event, An-Najah National University

- **Story and dashboard:** `index.html` (Mission Brief, Evidence, Gap Map, Proof)
- **Research workspace:** `workspace.html` (Evidence Explorer, Scenario Ranker, Ask with Citations)

Both pages are single files with the data embedded. They run offline and on GitHub Pages; no server, no build step.

## The problem

NASA plans a Moon base with **30% or more oxygen at 10.2 psi (70.3 kPa)**. Richer air makes materials easier to burn.
Has any material been tested in that air?

| | Value | Source |
|---|---|---|
| One dataset | **669 records from 7 NASA PSI investigations** | `data/atlas_dataset.json` |
| Real-material records | **277** (BASS, BASS-II, Saffire I–III) | PSI-26, 25, 98, 99, 100 |
| Highest O₂ any real material was tested at | **22.7%** (Moon base: +7.3 points) | computed |
| Distance from Moon-base air to the nearest real-material run | **d = 7.08** (close means d ≤ 1) | equation below |
| Closest NASA evidence to Moon-base air | **ACME BRE**, a gas burner that emulates a solid: **7 of 13** tests at 24–32% O₂ and 60–80 kPa kept burning | PSI-20 |
| Partial-gravity runs | **0** | challenge statement |

## Which investigations, and why

Five criteria, taken from the challenge text: combustion; flown in microgravity; solid habitat materials; run-level
conditions and outcomes; NASA sources we can cite. The challenge itself names BASS, BASS-II and Saffire-I/II/III for
material flammability. We add ACME BRE (PSI-20), which the challenge describes as a study of materials flammability, and
ACME CFI-G (PSI-159), the highest-oxygen microgravity tests. BRE and CFI-G are gas burners, different physics, so they
are kept in their own groups and never mixed into the ranking of real materials. Ten investigations, across prevention,
detection and suppression, are ranked by relevance per habitat in the Mission Brief.

## One dataset (`python build_unified.py`)

- **148 records** extracted by our code from NASA's raw files (BASS workbook, Saffire tables). Each carries a quote verified word for word.
- **521 records** transcribed by our team from NASA reports (BASS-II Summary Report NASA/TM-20210011385, ACME BRE dissertation Table 3.1, CFI-G records), each citing its table: `data/team_ibrahim/`.
- Where both covered the same test, the raw-file record is kept; 46 duplicates are listed with the reason in `data/excluded.csv`.
- Missing values stay empty; assumed values are flagged (BASS-II pressure is not reported, so it is not used for distance). Each record states how its outcome was read and the weight a model gives it.

## How it works: no quote, no number

1. **Read** NASA's own files and reports.
2. **Extract** each run: material, oxygen, pressure, airflow, gravity, outcome.
3. **Verify**: raw-file values must be found word for word in the NASA source (two planted fakes are rejected in the demo); report values cite their table.
4. **Rank and map**: materials ranked for a habitat's air, gaps mapped, a mission brief where every line has a source.
5. **AI that learns, explains and is checked** (`python models.py`)
   - *Real-material model*: Bayesian logistic regression on 195 labelled microgravity runs (oxygen, airflow, material), weighted by label quality. **Each +1 point of O₂ multiplies the odds of sustained burning by 1.34 (95% CI 1.08–1.66).** It never predicts beyond the tested oxygen range.
   - *Emulated-solid model (ACME BRE)*: Bayesian logistic regression on 59 tests from 18–40% O₂ and 57–104 kPa. Leave-one-out accuracy 95% (baseline 51%). At Moon-base air it gives the probability that a fuel keeps burning, given it ignited.
   - *Active learning*: the next experiment is chosen by expected information gain: Moon-base air in microgravity, testing Ultem, Silicone and Nomex first.
   - *LLM interpreter with a fact-checker*: Gemini explains the evidence; the engine checks every number it writes and flags unsupported numbers or claims.

**Distance.** For a habitat's air *x* and a NASA run *s*:

    d = sqrt( Σ ((x − s) / τ)² ),   τ = max(20% of the tested range, floor: 1 O₂ point, 5 kPa, 2 cm/s)

d ≤ 1 is close, d ≤ 2 is far, beyond that is no evidence. Oxygen is required. Doubling τ still leaves the Moon base at d ≈ 3.5.

**Statistics.** 95% Wilson intervals for burn shares; two-sided Fisher exact tests on all 28 material pairs with Bonferroni correction (α = 0.0018; 6 differences survive); exact sign test for Earth vs space (Saffire-II silicone: 3 of 4 burned on Earth, none in space, p = 0.25: not significant, reported as a signal only).

## Measured quality

- Raw-file quotes found word for word: **148/148**. BASS fields vs NASA's original workbook: **609/610** identical.
- Burn outcome read from crew notes: first rule 74%, improved rule **89.5%** on a held-out set of 19 runs.
- Real-material model, tested on whole investigations it never saw: better calibrated than "always burns" on BASS (Brier 0.093 vs 0.154), not better on BASS-II or Saffire-II. It explains the effects of oxygen and material; it cannot yet predict a new investigation better than the baseline. We report this rather than hide it.
- Problems in NASA's own files are listed in `data/data_issues.json`: shown, never silently fixed.

## Run it

Python 3.9+, standard library only.

```
python flame_atlas.py demo                 # accept / reject, ranking, "no evidence"
python flame_atlas.py brief --env moon     # mission brief: iss | moon | spacesuit
python flame_atlas.py stats                # Wilson intervals, Fisher exact, sign test
python flame_atlas.py gaps                 # conditions nobody has tested
python build_unified.py                    # build the one dataset
python models.py                           # fit and validate the AI models
python flame_atlas.py next --env moon      # Bayesian model + active learning: which test to fly next
python flame_atlas.py eval                 # accuracy on the held-out set
python flame_atlas.py rank --o2 21 --pressure 101.3 --gravity micro
python build_dataset.py raw_nasa raw_nasa/BASS_test_matrix.xlsx   # rebuild data from NASA files
python site/build_site.py                  # rebuild index.html
python site/build_workspace.py             # rebuild workspace.html
```

## Limits

- A triage tool, not a flammability certificate. It does not replace NASA-STD-6001 testing.
- No partial-gravity (Moon or Mars) combustion data exists in PSI yet.
- Saffire tables and the BASS-II report do not give pressure per run; those runs are kept with pressure empty.
- ACME BRE emulates a solid with a gas burner and lists only tests that ignited: its Moon-air probabilities are for an emulated fuel, given ignition.
- Flame spread rate is reported for too few runs to rank by it; materials are compared by burned / not burned.
- Some BASS runs changed airflow during the test; we use the first value and flag it.
- The 20% tolerance is a stated assumption, kept in one constant.
- The Bayesian model pools all tested conditions per material. It does not predict burning at untested air; it ranks where one new test would teach the most.
- Wilson intervals are used for reporting, Bayesian credible intervals for choosing the next test; both are shown with their names.

## Data and references

NASA Physical Sciences Informatics (PSI), CC0: PSI-26 (BASS), PSI-25 (BASS-II), PSI-98, PSI-99, PSI-100 (Saffire-I, II, III), PSI-20 (ACME BRE), PSI-159 (ACME CFI-G). BASS-II Summary Report NASA/TM-20210011385.
Habitat conditions are quoted from the NASA Space Apps 2026 *Flame in Freefall* challenge statement.
Full references and DOIs: `REFERENCES.md`. A public mirror of the raw NASA files was used first, with credit;
every file was then replaced by the copy downloaded directly from psi.nasa.gov.

## Team Orion

Mu'min (lead, backend) · Zayan (AI lead) · Hiba (retrieval, data) · Alaa (interface design; the research workspace is built on her design) · Ibrahim (full-stack; BASS-II, BRE and CFI-G dataset) · Karam (strategy, presentation)

## Use of artificial intelligence

**AI inside the tool:** a Bayesian model with active learning (computed in `flame_atlas.py`, no external service), a text classifier for crew logs, retrieval with citations, and an optional LLM interpreter (Google Gemini, user's own key) whose every number is fact-checked by the engine. Rankings and statistics are computed by code from verified NASA records, never by the language model.

**AI used to build it:** we used Claude (Anthropic) as a coding and writing assistant: for parts of the engine and website code, for drafting the 38 outcome labels in `data/gold.json` (two unclear rows excluded; a team member spot-checked a sample), and for drafting text. The logo was made with AI image tools and is marked as AI-generated where shown.
