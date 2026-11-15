import type { Experiment } from './api';

const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').toLowerCase();

export function filterExperiments(
  records: Experiment[],
  query: string,
  material = 'All materials',
  gravity = 'All gravity',
): Experiment[] {
  const search = normalize(query);
  return records.filter(record => {
    const text = normalize([
      record.id, record.program, record.title, record.material, record.gravity,
      record.year, record.summary, record.source_id,
    ].filter(value => value !== null && value !== undefined).join(' '));
    return (!search || text.includes(search))
      && (material === 'All materials' || record.material === material)
      && (gravity === 'All gravity' || record.gravity === gravity);
  });
}
