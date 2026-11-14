# Changelog
Contract changes after Phase 2 must be listed here and in `docs/API_CONTRACT.md`.

## 0.1.0 — Phase 0
- Contract, Pydantic models, example responses (generated from the real data by `backend/scripts/build_examples.py`), `MOCK=1`, `/api/health`.

## 0.2.0 — Phase 2
- Real implementations: presets, materials (search/detail/evidence), assess, experiments, about. `MOCK=1` still serves examples.
- Added `MaterialMatch.confident` (bool). `false` = suggestion only; /api/assess never auto-resolves on it. Material resolution: exact (EN/AR normalised) -> Mongo text (token-verified) -> vector (auto-resolve only at >= 0.80).
- 1g MOC threshold rows have `oxygen_pct = null`; for matching, their O2 coordinate is the MOC value (`outcome_value`). Stated in `nearest_evidence[].note`.
- `evidence_groups[].total_in_group` counts all rows near the point, including `tested_at` (conditions_only) rows; the `EVIDENCE` verdict counts only rows with an outcome (`verdict_reason`).
