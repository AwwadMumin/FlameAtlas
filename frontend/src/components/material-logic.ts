/** Pure helpers shared by the explorer search and the Materials page (unit-tested in tests/material-logic.test.mjs). */
import type { AssessBody, AssessResult, MaterialCard } from './materials-api';

export interface Conditions { preset: string; gravity: string; oxygen: string; airflow: string }
export const DEFAULT_CONDITIONS: Conditions = { preset: 'iss', gravity: 'orbit', oxygen: '', airflow: '' };
export const GRAVITIES: { key: string; label: string }[] = [
  { key: 'orbit', label: 'Orbit / ISS (microgravity)' }, { key: 'earth', label: 'Earth (1g)' }, { key: 'moon', label: 'Moon (no direct data)' }, { key: 'mars', label: 'Mars (no direct data)' },
];

const num = (v: string): number | null => (v.trim() === '' || Number.isNaN(Number(v)) ? null : Number(v));
export const conditionsKey = (c: Conditions) => JSON.stringify([c.preset, c.gravity, c.oxygen.trim(), c.airflow.trim()]);

export function toAssessBody(query: string, c: Conditions): AssessBody {
  return { material_query: query.trim(), preset_id: c.preset || null, oxygen_pct: num(c.oxygen), gravity: c.gravity, airflow_cm_s: num(c.airflow), use_llm: false };
}

export type Status = 'tested' | 'estimate' | 'none';
export const statusOf = (r: Pick<AssessResult, 'verdict'>): Status => (r.verdict === 'EVIDENCE' ? 'tested' : r.verdict === 'MODEL_ESTIMATE' ? 'estimate' : 'none');
export const STATUS_LABEL: Record<Status, string> = { tested: 'Tested evidence', estimate: 'Model estimate — not tested', none: 'No direct evidence' };
export const pct = (x: number) => `${Math.round(x * 100)}%`;

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ');
export function filterMaterials(list: MaterialCard[], text: string): MaterialCard[] {
  const q = norm(text);
  if (!q) return list;
  return list.filter(m => [m.material_id, m.name_en, m.name_ar ?? '', m.chemical_family ?? '', m.kind ?? '', ...m.aliases].some(v => norm(v).includes(q)));
}
export const recordCount = (m: MaterialCard) => m.variants.reduce((n, v) => n + v.n_records, 0);
