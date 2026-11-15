/** Material answers from the Mission Lens backend: tested evidence, model estimate, or no direct evidence. */
import { request } from './api';

export type Verdict = 'EVIDENCE' | 'MODEL_ESTIMATE' | 'NO_DIRECT_EVIDENCE';
export interface EvidenceRecord {
  experiment_id: string; source_investigation: string | null; gravity_bucket: 'microgravity' | '1g'; material_id: string | null; material_variant: string | null;
  oxygen_pct: number | null; pressure_kpa: number | null; airflow_cm_s: number | null; display_kind: string; display_text: string;
  quality_flags: string[]; source_ref: string | null; source_url: string | null; doi: string | null; distance: number | null;
}
export interface EvidenceGroup { evidence_type: string; label: string; records: EvidenceRecord[]; total_in_group: number }
export interface MaterialCard {
  material_id: string; name_en: string; name_ar: string | null; kind: string | null; chemical_family: string | null; aliases: string[];
  variants: { variant: string; n_records: number; inferred: boolean }[]; has_microgravity_evidence: boolean; has_1g_evidence: boolean;
}
export interface MaterialMatch { material: MaterialCard; score: number; match_type: string; confident: boolean }
export interface Preset { id: string; name: string; o2_pct: number; pressure_kpa: number }
export interface BurnPrediction {
  label: string; role: 'estimate' | 'cross_check'; basis: 'no_research' | 'smoke_only' | 'earth_only' | 'not_tested_at_these_conditions' | 'tested_here';
  probability_sustained: number; interval_95: [number, number]; informative?: boolean; material_group: string | null; statement: string; airflow_assumption: string | null; caveats: string[];
  oxygen_odds_ratio_per_point: number[];
  trained_on: { n_runs: number; by_investigation: Record<string, number>; o2_range: number[]; flow_range_cm_s: number[] };
  validation: { beats_baseline: boolean; statement: string; model_brier: number; baseline_brier: number; pooled_n: number;
    per_investigation: { investigation: string; n: number; model_brier: number; baseline_brier: number }[] };
}
export interface Nearest { gravity_bucket: 'microgravity' | '1g'; record: EvidenceRecord; delta_o2_pct: number | null; delta_pressure_kpa: number | null; note: string | null }
export interface AssessResult {
  verdict: Verdict; verdict_label: string; verdict_tier: 'green' | 'amber' | 'grey'; verdict_reason: string; summary_text: string;
  material: MaterialCard | null; material_resolved_as: string | null; requested: Record<string, unknown>; evidence_groups: EvidenceGroup[];
  burn_prediction?: BurnPrediction | null; nearest_evidence: Nearest[]; earth_vs_space: { comparison_text: string | null; banner: string | null } | null;
  gaps: { suggested_test: string; reason: string }[]; warnings: string[];
}
export interface AssessBody {
  material_query: string; preset_id?: string | null; oxygen_pct?: number | null; gravity: string; airflow_cm_s?: number | null; use_llm: false;
}
export interface MaterialEvidence { material_id: string; groups: EvidenceGroup[]; smoke_detection: EvidenceRecord[] }

export const listMaterials = () => request<{ materials: MaterialCard[]; total: number }>('/api/materials');
export const listPresets = () => request<{ presets: Preset[] }>('/api/presets');
export const searchMaterials = (q: string) => request<{ query: string; matches: MaterialMatch[]; empty_state_message: string | null }>(`/api/materials/search?q=${encodeURIComponent(q)}`);
export const assessMaterial = (body: AssessBody) => request<AssessResult>('/api/assess', { method: 'POST', body: JSON.stringify(body) });
export const materialEvidence = (id: string) => request<MaterialEvidence>(`/api/materials/${encodeURIComponent(id)}/evidence?limit=200`);
