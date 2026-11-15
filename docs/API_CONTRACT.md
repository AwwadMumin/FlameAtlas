# Mission Lens — API Contract (v0.1.0)

Base URL `http://localhost:8000`. All JSON. OpenAPI: `/openapi.json`, Swagger UI: `/docs`.
**Source of truth = the Pydantic models in `backend/app/models/api.py`** (the OpenAPI schema is generated from them).
Full example responses: `docs/examples/<name>.json` (generated from the real NASA data; `MOCK=1` serves them with no database).

## Conventions
- **Errors**: `{"error": {"code", "message", "details"}}`. `404 not_found`, `422 validation_error` (details = list of `{loc,msg}`),
  `501 not_implemented` (endpoint not built yet and MOCK off), `500 internal_error`. Examples: `error_404.json`, `error_422.json`.
- **No business logic in the UI.** Labels, tier colours, empty-state texts, source URLs, chart arrays are all in the response.
- **null = "not available"**. Show that text; never fill it in.
- **Gravity input** `gravity`: `orbit|microgravity` → µg bucket, `earth|1g` → 1g bucket, `moon|mars` → no data (always `NO_DIRECT_EVIDENCE`).
- CORS origins from env `CORS_ORIGINS` (default `*`).

## Verdict tiers (always show `verdict_label` with `verdict_tier`)
| verdict | verdict_label | verdict_tier |
|---|---|---|
| `EVIDENCE` | Evidence | green |
| `MODEL_ESTIMATE` | Model estimate — not tested | amber |
| `NO_DIRECT_EVIDENCE` | No direct evidence | grey |

`MODEL_ESTIMATE` only appears when a correction model is configured (`backend/app/core/correction_models.yaml`) and the input is in its valid range. Today none is configured, so it is never returned. Shape: `assess_model_estimate_SHAPE_ONLY.json` (no values).

## Rules the UI must follow
1. Show `matched_tolerances.text` next to an `EVIDENCE` verdict.
2. `EvidenceRecord.display_kind`: `result` | `observation` | `threshold` | `tested_at` | `count` | `smoke`. `tested_at` rows are "tested at", **not results**. Never show `smoke` rows as burn evidence (they come only in `smoke_detection`).
3. Show `quality_flags` and `warnings` next to the value they affect (verbatim, including `[PMMA not named in cell; inferred…]`, the FLEX unit note and the ACME "3400%" artifact flag).
4. Every evidence card: "Source ↗" → `source_url`, plus `source_ref`.
5. `test_family`: 1g MOC/ULOI (NASA-STD-6001 Test 1, upward) is a different quantity from LOI (downward, ASTM D2863). Never average or compare them as equal. Van Krevelen results have `estimate.kind = van_krevelen_loi_1g` and `not_a_microgravity_limit = true`.
6. `earth_vs_space.banner` (red) is shown only when non-null (a µg sustained burn below the 1g MOC). `one_g_not_conservative = null` means undetermined (needs confirmed labels).
7. `earth_vs_space.correction_model_status = not_configured` → show `correction_model_message` ("Correction model not configured") and the evidence comparison only.

## Notes (Phase 2)
- `materials/search` matches carry `confident`; show `false` ones as "Did you mean…" only.
- `evidence_groups[].total_in_group` includes `tested_at` rows; `verdict_reason` states the count of rows with an outcome.
- For 1g MOC records `oxygen_pct` is null by design (the MOC is `outcome_value`); show MOC/ULOI as given, never as LOI.

- `scatter_points`: plot `o2` (x) vs `pressure_kpa` (y, may be null = pressure not stated), colour by `gravity`; 1g points are MOC thresholds. Highlight the single point with `is_requested_point`.
- `GET /api/demo-scenarios`: POST each `request` to `/api/assess` as is. Postman: `docs/postman_collection.json`.
- Unknown `preset_id` → 422; blank `material_query` → 422.

## Notes (Phase 5)
- **Labelling workflow:** `GET /api/admin/labels/queue` -> human reads `flame_behavior_notes` -> `POST /api/admin/labels` with a `quote` copied verbatim from the notes. `suggested_label` / `suggested_quote` are hints; show them as "suggested", never as results.
- **Validation:** show `old_method_test.definition`, both strengths separately (strict vs variant-dependent), the `cases[]` with both `*_source_url` links, and `caveats`. `empty_state_message` is set until at least one label is confirmed. Say explicitly that n is small.
- **Coverage grid:** `grids[bucket][pressure_idx][o2_idx]`; axes `o2_axis` (lower edge of each 1% bin) and `pressure_axis`; the last pressure row `"not stated"` holds records without pressure. Draw `preset_overlays[]` as markers at (`o2_index`, `pressure_index`).
- **Next experiments:** always label "Suggested test (not a result)"; `bordering_evidence` = experiment ids to link via `/api/experiments/{id}`.

## Notes (Phase 6)
- `summary_source`: `template` (deterministic, always available) or `llm_checked` (LLM text whose numbers were verified against the retrieved records). Show `summary_fallback_reason` (when present) as a small "LLM text rejected" hint, not as an error.
- Send `"use_llm": false` to skip the LLM (faster; the template is returned in < 100 ms). With the LLM on, expect several extra seconds.

## Notes (1.1.0)
- `earth_vs_space.baseline_1g.moc_values[]` carry `procedure` (`standard` / `non_standard` / `not_stated`) and `configuration`. Show the standard rows first and the other configurations visibly labelled; never present the 1g MOC as a single number unless only one row exists. `procedure_note` explains the rule (source: Hirsch et al. 2011).
- The red banner now says which comparator it used ("standard-procedure" or "lowest (no row states the standard procedure)").
- `/api/validation.old_method_test`: three views, never blended: strict (beyond every row), configuration-dependent (key `*_variant_dependent`), and `n_*_standard_moc` (versus the standard procedure only).

## Endpoints
| Method & path | Response model | Example file(s) |
|---|---|---|
| GET `/api/health` | `HealthResponse` | `health` |
| GET `/api/presets` | `PresetsResponse` (presets with `pressure_kpa` = psia × 6.894757, gravity levels incl. `has_direct_data`) | `presets` |
| GET `/api/materials/search?q=` | `MaterialSearchResponse` (English or Arabic; empty → `empty_state_message`) | `materials_search`, `materials_search_empty` |
| GET `/api/materials/{id}` | `MaterialDetailResponse` (404 if unknown) | `material_detail`, `error_404` |
| GET `/api/materials/{id}/evidence?gravity=&evidence_type=` | `MaterialEvidenceResponse` (grouped by `evidence_type`; `smoke_detection` separate) | `material_evidence` |
| POST `/api/assess` | `AssessResponse` | `assess_evidence`, `assess_no_direct_1g_only`, `assess_no_direct_moon`, `assess_unknown_material`, `assess_unknown_empty`, `assess_model_estimate_SHAPE_ONLY` |
| GET `/api/coverage/{material_id}` | `CoverageResponse` (grid[pressure_idx][o2_idx], axes labelled, preset overlays) | `coverage` (shape; populated in Phase 5) |
| GET `/api/next-experiments?preset=` | `NextExperimentsResponse` ("Suggested test", not a result) | `next_experiments` (shape; Phase 5) |
| GET `/api/validation` | `ValidationResponse` | `validation` |
| GET `/api/admin/labels/queue` | `LabelQueueResponse` | `labels_queue` |
| POST `/api/admin/labels` | body `LabelIn` → `LabelOut` | `label_saved` |
| GET `/api/demo-scenarios` | `DemoScenariosResponse` (each `request` can be POSTed to `/api/assess` as is) | `demo_scenarios` |
| GET `/api/about` | `AboutResponse` (investigations, provenance, licenses, incidents, earth benefits) | `about` |
| GET `/api/experiments/{experiment_id}` | `ExperimentDetailResponse` (full record + card text + source link) | `experiment_detail` |

## `POST /api/assess`
Request (`AssessRequest`):
```json
{ "material_query": "acrylic", "material_variant": null, "preset_id": "iss", "oxygen_pct": 21, "pressure_kpa": 101.3,
  "gravity": "orbit", "airflow_cm_s": null, "thickness_mm": null, "question": "will it self-extinguish?",
  "unknown_material_props": null }
```
`unknown_material_props`: `{polymer_family, char_yield_pct (0-100), known_loi_pct, known_loi_standard, thickness_mm}`.

Response (`AssessResponse`) key fields: `verdict`, `verdict_label`, `verdict_tier`, `verdict_reason`, `empty_state_message`, `material`
(null for unknown), `matched_tolerances`, `evidence_groups[]` (records grouped by `evidence_type`), `smoke_detection[]`,
`earth_vs_space` (`baseline_1g.moc_values[]`, `microgravity_evidence[]`, banner, correction status), `estimate`, `nearest_evidence[]`,
`findings[]` (Researcher's Guide: claim, page, section), `investigations[]`, `scatter_points[]` (chart-ready; the requested point has
`is_requested_point = true`), `summary_text`, `summary_source` (`template` | `llm_checked`), `warnings[]`, `gaps[]`.

### Tier examples
- **EVIDENCE** — `assess_evidence.json` (PMMA, 21 % O2, 101.3 kPa, orbit).
- **NO_DIRECT_EVIDENCE, 1g-only material** — `assess_no_direct_1g_only.json` (PET, orbit).
- **NO_DIRECT_EVIDENCE, outside gravity domain** — `assess_no_direct_moon.json` (nearest µg and 1g evidence in `nearest_evidence`).
- **Unknown material** — `assess_unknown_material.json` (char yield 30 % → 1g LOI 29.5 % O2, labelled "not tested", verdict still `NO_DIRECT_EVIDENCE`); empty state: `assess_unknown_empty.json`.
- **MODEL_ESTIMATE** — shape only until coefficients are entered.

## Changes
See `CHANGELOG.md`. The contract is frozen after Phase 2; later changes must be logged there.
