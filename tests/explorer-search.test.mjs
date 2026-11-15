import assert from 'node:assert/strict';
import test from 'node:test';
import { filterExperiments } from '../src/components/explorer-search.ts';

const records = [
  { id: 'bass-ii', program: 'BASS-II', title: 'Burning and Suppression', material: 'Fabric', gravity: 'Microgravity', year: 2017, summary: 'Solid fuel research', source_id: 'NASA-42', source_url: null, oxygen: null, airflow: null },
  { id: 'earth-1', program: 'Ground', title: 'Does it burn?', material: 'Polymer', gravity: 'Earth', year: null, summary: '', source_id: null, source_url: null, oxygen: null, airflow: null },
];

test('search normalizes casing and whitespace', () => {
  assert.deepEqual(filterExperiments(records, '  burning   AND suppression  '), [records[0]]);
  assert.deepEqual(filterExperiments(records, ' \t '), records);
});

test('question marks are literal, not a match-all escape', () => {
  assert.deepEqual(filterExperiments(records, 'unrelated?'), []);
  assert.deepEqual(filterExperiments(records, '?'), [records[1]]);
});

test('search includes record metadata and handles missing fields', () => {
  for (const query of ['bass-ii', 'microgravity', '2017', 'nasa-42', 'solid fuel']) {
    assert.deepEqual(filterExperiments(records, query), [records[0]]);
  }
  assert.deepEqual(filterExperiments(records, 'null'), []);
});

test('query, material, and gravity filters must all match', () => {
  assert.deepEqual(filterExperiments(records, 'burn', 'Fabric', 'Microgravity'), [records[0]]);
  assert.deepEqual(filterExperiments(records, 'burn', 'Fabric', 'Earth'), []);
  assert.deepEqual(filterExperiments(records, '', 'Polymer'), [records[1]]);
  assert.deepEqual(filterExperiments([], ''), []);
});
