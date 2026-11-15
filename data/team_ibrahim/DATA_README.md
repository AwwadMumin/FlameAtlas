# Microgravity flammability dataset (PSI-20, 25, 26, 98, 99, 100, 159)

Files
- `training_dataset.csv`  514 rows: only rows with a usable label (outcome known, O2 and pressure present). Start here.
- `master_all_records.csv`  567 rows: everything, including rows with no label (Saffire-I/III, 49 BASS-II rows with no comment match). For the website/RAG layer.
- `limit_anchors.csv`  9 published limits and one empirical equation, for sanity checks and for the UI. Not training rows.
- `material_properties.csv`  heat of combustion and heat of gasification for 5 materials (BRE report Table 2).

## Model groups (train SEPARATE models, do not mix)
| model_group | rows | what it is |
|---|---|---|
| solid_fuel | 122 | real solids (PMMA, SIBAL, silicone, Nomex, wax) on ISS: PSI-25, 26, 99 (113 microgravity + 9 at 1 g) |
| emulated_solid_burner | 59 | PSI-20 gas burner emulating a solid; has hc, L, pressure 0.57-1.04 bar, O2 18-40% |
| gaseous_fuel_flame | 333 | PSI-159 spherical cool/hot diffusion flames (ethane, propane, butane). Different physics; keep for completeness only |

## Label
`outcome_class` in {sustained, not_sustained, no_ignition}; `target_sustained` = 1 if sustained.
- PSI-20 and PSI-159: SE (self-extinguished) -> not_sustained; FT (flow terminated while burning) -> sustained.
- PSI-99: from the table; PSI-25 Table 7.1 SIBAL tests: Quenched / Blow-off -> not_sustained, No blowoff / ignited -> sustained, No ignition -> no_ignition (flow = flow at which it happened).
- PSI-25 other tests and PSI-26: derived from appendix comments / paper text by keyword rules.

`label_quality` and `sample_weight`: measured 1.0 | explicit_table 0.7-1.0 | derived_text 0.35-0.5. Use the weight in fitting.

## Known limits (read before modelling)
1. Pressure is constant (1.013 bar, assumed ISS cabin) for every solid_fuel row. A solid-fuel model cannot learn pressure. Only PSI-20 varies it.
2. Gravity is only 0 g and 1 g. No partial-gravity data exists, so Moon predictions are extrapolation: report them as AI estimates with low confidence and show the 0 g and 1 g bounds. Effect of gravity is material dependent (Saffire-II silicone burns at 1 g, not at 0 g).
3. Only 9 solid rows are 1 g, so 1 g -> Moon transfer is not learnable from this data.
4. solid_fuel is imbalanced (86 of 113 microgravity rows are sustained). Use class weights and check recall of not_sustained.
5. O2 coverage: solids 13.6-22.2%; PSI-20 18-40%; Moon-like O2 >= 30% exists only in PSI-20 (burner, not a solid).
6. `conditions_assumed=1` marks rows where O2 (PSI-26) or pressure was assumed.
7. PSI-25 `flow_cm_s` is the STARTING flow; many tests then change flow (full history in `flow_history_raw` in the master, `flow_min/max_cm_s`).
8. Saffire-I and III have no outcome or numeric results in the supplied files (raw sensor Excel files not provided); they are in the master only.
9. Source typos fixed: Saffire-I length/width swapped, thickness unit (mm not cm), BASS-II material class names. Original files untouched.

## Validation
Use leave-one-investigation-out CV (`cv_group`): train without one PSI, test on it. Random k-fold leaks neighbouring tests from the same run and overstates accuracy.
