# Changelog
Contract changes after Phase 2 must be listed here and in `docs/API_CONTRACT.md`.

## 0.1.0 — Phase 0
- Contract, Pydantic models, example responses (generated from the real data by `backend/scripts/build_examples.py`), `MOCK=1`, `/api/health`.

## 0.2.0 — Phase 2
- Real implementations: presets, materials (search/detail/evidence), assess, experiments, about. `MOCK=1` still serves examples.
- Added `MaterialMatch.confident` (bool). `false` = suggestion only; /api/assess never auto-resolves on it. Material resolution: exact (EN/AR normalised) -> Mongo text (token-verified) -> vector (auto-resolve only at >= 0.80).
- 1g MOC threshold rows have `oxygen_pct = null`; for matching, their O2 coordinate is the MOC value (`outcome_value`). Stated in `nearest_evidence[].note`.
- `evidence_groups[].total_in_group` counts all rows near the point, including `tested_at` (conditions_only) rows; the `EVIDENCE` verdict counts only rows with an outcome (`verdict_reason`).

## 0.3.0 — Phase 3 (no schema changes)
- `earth_vs_space`: red banner / `one_g_not_conservative` computed ONLY from human-confirmed `sustained_burn` labels (data/derived/outcome_labels.json); `null` = undetermined (no confirmed labels), `false` = labels exist and none below the lowest pressure-compatible 1g MOC. `comparison_text` reports the MOC range (min..max with sources), never a cherry-picked value.
- Correction module (`services/correction.py`, `correction_models.yaml`): ships `not_configured`, no coefficients. When configured it needs citation/page/equation/formula/inputs/coefficients/valid_range; evaluates only inside `valid_range`; returns `MODEL_ESTIMATE` only if the leave-one-out error exists in `data/derived/validation.json` (Phase 5). Moon/Mars never get an estimate.
- Unknown material: Van Krevelen 1g LOI (17.5 + 0.40·CR, constants in config) labelled "not tested"; user LOI shown as given (needs a test standard) and never compared to MOC; same-family neighbours' nearest evidence; verdict always `NO_DIRECT_EVIDENCE` (a correction model needs a 1g MOC of the same material).
