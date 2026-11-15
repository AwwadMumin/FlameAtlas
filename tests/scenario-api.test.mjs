import assert from 'node:assert/strict';
import test from 'node:test';

const input = { material_query: 'acrylic', gravity: 'orbit', oxygen_pct: null, pressure_kpa: 101.3, airflow_cm_s: 0, use_llm: false };

async function apiFor(base, key) {
  const previous = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (base === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
  else process.env.NEXT_PUBLIC_API_BASE_URL = base;
  try {
    return await import(`../src/components/api.ts?test=${key}`);
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = previous;
  }
}

test('scenario assessment sends documented endpoint and preserves unknown versus zero', async t => {
  const api = await apiFor('https://research.example/', 'request');
  const result = { verdict: 'NO_DIRECT_EVIDENCE', verdict_label: 'No direct evidence' };
  const fetchMock = t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://research.example/api/assess');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), input);
    return new Response(JSON.stringify(result), { status: 200 });
  });
  assert.deepEqual(await api.assessScenario(input), result);
  assert.equal(fetchMock.mock.callCount(), 1);
});

test('scenario assessment reports service failures', async t => {
  const api = await apiFor('https://research.example', 'error');
  t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 422 }));
  await assert.rejects(api.assessScenario(input), /Research API returned 422/);
});

test('missing API configuration never sends a scenario request', async t => {
  const api = await apiFor(undefined, 'missing');
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => { throw new Error('Unexpected request'); });
  await assert.rejects(api.assessScenario(input), /Research API is not configured/);
  assert.equal(fetchMock.mock.callCount(), 0);
});
