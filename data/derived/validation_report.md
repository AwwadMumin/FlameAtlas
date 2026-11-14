# Mission Lens — validation report

Confirmed human labels: **0** of 121 labelable BASS records.

> No confirmed labels yet. Label BASS crew notes via /api/admin/labels (or scripts/import_labels.py) to produce the old-method error counts. Saffire pairs are shown regardless.

## 1. Test of the old method ("trust the 1g test")

A microgravity (µg) record under-predicts hazard when a confirmed 'sustained_burn' happened at an O2 below the 1g MOC (NASA-STD-6001 Test 1, upward). STRICT = below the LOWEST pressure-compatible MOC row (below every 1g result). VARIANT-DEPENDENT = below the highest but not the lowest row: the 1g result depends on the variant/pressure tested, so this is reported separately and never blended into the strict count. The opposite error is a µg non-burn ('no_ignition' or 'brief_then_self_extinguished') above the 1g MOC (strict = above the HIGHEST row). Pressure-compatible = within the configured tolerance, or either pressure not stated. MOC (upward) is never converted to or compared as LOI (downward).

_No material has both a 1g MOC and a confirmed µg label yet._

## 2. Saffire-II pairs (same sample, µg vs 1g)

| pair | material | microgravity | 1g |
|---|---|---|---|
| PAIR-SAF2-2-1 | silicone | flame_spread_rate = not available (verbatim note: "microgravity burn length: ~ 0; spread: n/a; burn time: Insignificant") — Silicone; O2 21.5% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: Complete; 1g spread: Acceleratory") — Silicone; conditions not recorded. |
| PAIR-SAF2-2-2 | silicone | flame_spread_rate = not available (verbatim note: "microgravity burn length: ~ 0; spread: n/a; burn time: Insignificant") — Silicone; O2 22.1% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = 1.2 [mm/s] — Silicone; conditions not recorded. |
| PAIR-SAF2-2-3 | silicone | flame_spread_rate = not available (verbatim note: "microgravity burn length: ~ 0; spread: n/a; burn time: Insignificant") — Silicone; O2 22.1% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: ~ 0; 1g spread: n/a") — Silicone; conditions not recorded. |
| PAIR-SAF2-2-4 | silicone | flame_spread_rate = not available (verbatim note: "microgravity burn length: ~ 0; spread: n/a; burn time: Insignificant") — Silicone; O2 22.1% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = 0.6 [mm/s] — Silicone; conditions not recorded. |
| PAIR-SAF2-2-5 | sibal | flame_spread_rate = 2.1 [mm/s] — Cotton-Fiberglass (SIBAL); O2 22.1% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: Complete; 1g spread: Acceleratory") — Cotton-Fiberglass (SIBAL); conditions not recorded. |
| PAIR-SAF2-2-6 | None | flame_spread_rate = 2.6 [mm/s] — material not named; O2 22.1% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: Complete; 1g spread: Acceleratory") — material not named; conditions not recorded. |
| PAIR-SAF2-2-7 | None | flame_spread_rate = not available (verbatim note: "microgravity burn length: 5 cm & 0 (note 2); spread: n/a (Nomex); burn time: 140 s") — PMMA & Nomex; O2 22.1% (approximate (~) in source), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: ~ 0 (Nomex); 1g spread: n/a (Nomex)") — PMMA & Nomex; conditions not recorded. |
| PAIR-SAF2-2-8 | pmma | flame_spread_rate = not available (verbatim note: "microgravity burn length: ~ 10 cm (note 3); spread: Note 4; burn time: 600 s") — PMMA; O2 22.05% (midpoint of source range 22.1 to 22.0), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: Complete; 1g spread: Acceleratory") — PMMA; conditions not recorded. |
| PAIR-SAF2-2-9 | None | flame_spread_rate = not available (verbatim note: "microgravity burn length: ~ 10 cm (note 4); spread: Note 4; burn time: 900 s") — material not named; O2 21.95% (midpoint of source range 22.0 to 21.9), flow 20.0 cm/s. | flame_spread_rate = not available (verbatim note: "1g burn length: Complete; 1g spread: Acceleratory") — material not named; conditions not recorded. |

9 pair(s). Source of each row: see `source_ref` in the API.

## 3. Correction model

Correction model not configured. No error figures are reported because no model is configured.

## Caveats

- Outcome labels are human judgements of verbatim crew notes (BASS, PSI-26 as-run workbook); suggestions from keyword rules are excluded.
- Only materials with both a 1g MOC (WSTF) and confirmed µg labels are evaluated. In the current data these can only be PMMA and PEI (BASS crew notes exist for PMMA, wax, SIBAL, Nomex, PEI; wax, SIBAL and Nomex have no 1g MOC), so the evaluated set is small and not a random sample.
- 1g MOC (NASA-STD-6001 Test 1, upward) and LOI (downward, ASTM D2863) are different quantities and are never compared.
- µg records without a stated pressure are compared with MOC rows at all pressures.
- 0 of 121 labelable records are confirmed.
