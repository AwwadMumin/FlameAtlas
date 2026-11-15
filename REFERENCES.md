# References

## NASA PSI data used by Flame Atlas (CC0-1.0)
Fill each DOI from the "Cite this Investigation" button on psi.nasa.gov (PSI requires citation by DOI).

| Investigation | PSI | Investigation page | DOI |
|---|---|---|---|
| Burning and Suppression of Solids (BASS) | PSI-26 | https://psi.nasa.gov/physci/repo/data/investigations/PSI-26 | __FILL__ |
| Spacecraft Fire Experiment-I (SAFFIRE-I) | PSI-98 | https://psi.nasa.gov/physci/repo/data/investigations/PSI-98 | __FILL__ |
| Spacecraft Fire Experiment-II (SAFFIRE-II) | PSI-99 | https://psi.nasa.gov/physci/repo/data/investigations/PSI-99 | 10.60555/2chp-m469 |
| Spacecraft Fire Experiment-III (SAFFIRE-III) | PSI-100 | https://psi.nasa.gov/physci/repo/data/investigations/PSI-100 | __FILL__ |

Files used: PSI-26 BASS_test_matrix.xlsx (sheet "as run matrix") and PSI-26 Experimental table;
PSI-98/99/100 Experimental tables.

## Other investigations in the catalog (data/investigations.json)
Named in the challenge statement; PSI ids as seen in PSI search results / file names -- confirm before citing:
BASS-II PSI-25, SAME PSI-102, SAME-R PSI-101, FLEX PSI-69, FLEX-2 PSI-68, CFI PSI-39, ACME CFI-G PSI-159,
ACME Flame Design PSI-10, SPICE PSI-107, SLICE PSI-106.

## Context
- NASA Space Apps Challenge 2026, "Flame in Freefall" challenge statement (kept as data/sources/CHALLENGE.txt).
- Urban, D. L., et al. Large-scale Spacecraft Fire Safety Tests. NTRS 20150000894.
- Ferkul, P., et al. Results of Large-Scale Spacecraft Flammability Tests. ICES-2017. NTRS 20170008805.
- Bhattacharjee, S., et al. Opposed-flow flame spread: A comparison of microgravity and normal gravity
  experiments to establish the thermal regime. Fire Safety Journal (2015). doi:10.1016/j.firesaf.2015.11.011
- Combustion of Solids in Microgravity: Results from the BASS-II Experiment. NTRS 20160000593.

## Related work (other 2026 teams, ideas only; no code or processed data used)
- AstraFlame (Team Agnishikha): predictive models on PSI data. github.com/Dumbo-programmer/NASA-Space-Apps-2026
  -- its public mirror of raw PSI files was used once to locate files; every file we build from was then
  downloaded from psi.nasa.gov and compared (Saffire identical; BASS 609/610 fields identical).
- SPICA "The 34% Question": 3D lab with coverage verdicts. github.com/eres0045/spica-firelab
