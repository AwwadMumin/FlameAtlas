import assert from 'node:assert/strict';
import test from 'node:test';
import { toAssessBody, statusOf, filterMaterials, conditionsKey, pct, recordCount, DEFAULT_CONDITIONS } from '../src/components/material-logic.ts';
import { safeSourceUrl } from '../src/components/safe-url.ts';

const mats = [
  { material_id: 'pmma', name_en: 'PMMA (acrylic)', name_ar: 'أكريليك (PMMA)', chemical_family: 'polymethyl methacrylate', kind: 'solid polymer', aliases: ['plexiglas', 'أكريليك'], variants: [{ variant: 'a', n_records: 3 }, { variant: 'b', n_records: 4 }] },
  { material_id: 'pet', name_en: 'PET', name_ar: null, chemical_family: 'polyester', kind: null, aliases: [], variants: [] },
];

test('assess body: blanks become null, text is trimmed, LLM stays off', () => {
  const b = toAssessBody('  acrylic ', { preset: 'iss', gravity: 'orbit', oxygen: ' ', airflow: '' });
  assert.deepEqual(b, { material_query: 'acrylic', preset_id: 'iss', oxygen_pct: null, gravity: 'orbit', airflow_cm_s: null, use_llm: false });
  const c = toAssessBody('PET', { preset: '', gravity: 'earth', oxygen: '23.5', airflow: '10' });
  assert.equal(c.oxygen_pct, 23.5); assert.equal(c.airflow_cm_s, 10); assert.equal(c.preset_id, null);
  assert.equal(toAssessBody('x', { ...DEFAULT_CONDITIONS, oxygen: 'abc' }).oxygen_pct, null);
});

test('the three outcomes map to three statuses', () => {
  assert.equal(statusOf({ verdict: 'EVIDENCE' }), 'tested');
  assert.equal(statusOf({ verdict: 'MODEL_ESTIMATE' }), 'estimate');
  assert.equal(statusOf({ verdict: 'NO_DIRECT_EVIDENCE' }), 'none');
});

test('material filter matches English, Arabic, aliases and family', () => {
  for (const q of ['pmma', 'ACRYLIC', 'أكريليك', 'plexi', 'methacrylate']) assert.deepEqual(filterMaterials(mats, q), [mats[0]], q);
  assert.deepEqual(filterMaterials(mats, ''), mats);
  assert.deepEqual(filterMaterials(mats, 'zzz'), []);
});

test('cache key changes with every condition; helpers', () => {
  assert.notEqual(conditionsKey(DEFAULT_CONDITIONS), conditionsKey({ ...DEFAULT_CONDITIONS, gravity: 'earth' }));
  assert.equal(conditionsKey(DEFAULT_CONDITIONS), conditionsKey({ ...DEFAULT_CONDITIONS, oxygen: ' ' }));
  assert.equal(pct(0.874), '87%'); assert.equal(recordCount(mats[0]), 7); assert.equal(recordCount(mats[1]), 0);
});

test('only http(s) links are rendered', () => {
  assert.equal(safeSourceUrl('https://doi.org/10.1/x'), 'https://doi.org/10.1/x');
  assert.equal(safeSourceUrl('javascript:alert(1)'), null);
  assert.equal(safeSourceUrl(null), null);
});
