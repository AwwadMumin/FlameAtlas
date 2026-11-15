/**
 * Findings from NASA's own Researcher's Guide (NP-2015-10-034-JSC). Paraphrased by the team (never presented as verbatim quotes).
 * ids and pages match docs/flame_in_freefall_knowledge.json (guide_findings). Real sources only: nothing here is invented feedback.
 */
export interface Voice { id: string; page: number; topic: string; text: string }
export const GUIDE = { title: "A Researcher's Guide to: Combustion Science", publisher: 'NASA ISS Program Science Office', document: 'NP-2015-10-034-JSC', year: 2015 };
export const VOICES: Voice[] = [
  { id: 'RG-23', page: 35, topic: 'Spacecraft fire safety', text: 'Three long-held beliefs were shown to be wrong: that a steady fire cannot exist in still microgravity air, that a fire goes out by itself once ventilation stops, and that Earth fire standards are very conservative for space.' },
  { id: 'RG-14', page: 31, topic: 'Material flammability', text: 'BASS results indicate that NASA-STD-6001 Test 1 is not conservative: materials can burn at lower oxygen levels in microgravity than on Earth.' },
  { id: 'RG-17', page: 31, topic: 'Low-stretch flames', text: 'The flammability boundary for solids has a minimum oxygen limit at a gas speed of roughly 10 cm/s, which is also where flame spread is fastest, and that speed is typical of spacecraft ventilation.' },
  { id: 'RG-19', page: 24, topic: 'Exploration atmospheres', text: 'As of 2015 there was no test method designed specifically to determine the fire hazard of materials under exploration-atmosphere conditions.' },
  { id: 'RG-24', page: 35, topic: 'Smoke detection', text: 'Smoke particles from microgravity flames are a very different size, so detectors tuned for Earth smoke would look for the wrong signature.' },
];
