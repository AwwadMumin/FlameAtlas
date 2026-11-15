"use client";
import { assessMaterial, type AssessResult, type BurnPrediction, type EvidenceRecord } from './materials-api';
import { conditionsKey, pct, statusOf, STATUS_LABEL, toAssessBody, type Conditions } from './material-logic';
import { safeSourceUrl } from './safe-url';
import { useKeyed } from './use-keyed';
import s from './MaterialAnswer.module.css';

const TIER = { tested: 'green', estimate: 'amber', none: 'grey' } as const;

export function RecordItem({ r }: { r: EvidenceRecord }) {
  const url = safeSourceUrl(r.source_url);
  return <article className={s.rec}>
    <strong>{r.experiment_id}</strong> · {r.display_text}
    <div className={s.chips}>
      <span className={s.chip}>{r.gravity_bucket === 'microgravity' ? 'µg' : '1g'}</span>
      {r.oxygen_pct !== null && <span className={s.chip}>{r.oxygen_pct}% O₂</span>}
      <span className={s.chip}>{r.pressure_kpa !== null ? `${r.pressure_kpa} kPa` : 'pressure not stated'}</span>
      {r.material_variant && <span className={s.chip}>{r.material_variant}</span>}
    </div>
    {r.quality_flags.length > 0 && <div className={`${s.muted} ${s.flag}`}>⚑ {r.quality_flags.join('; ')}</div>}
    <div className={s.muted}>{r.source_ref ?? 'Source not listed'} {url && <a className={s.link} href={url} target="_blank" rel="noopener noreferrer">Source ↗</a>}</div>
  </article>;
}

function Prediction({ b }: { b: BurnPrediction }) {
  const v = b.validation, estimate = b.role === 'estimate';
  return <>
    {estimate && b.informative !== false && <div className={s.big}>{pct(b.probability_sustained)}<small>chance the flame keeps burning in microgravity (95% interval {pct(b.interval_95[0])}–{pct(b.interval_95[1])})</small></div>}
    {estimate && b.informative === false && <>
      <div className={s.big} style={{ color: 'var(--color-text)' }}>Cannot be determined<small>95% interval {pct(b.interval_95[0])}–{pct(b.interval_95[1])}</small></div>
      <p className={`${s.note} ${s.amber}`}><strong>The model cannot narrow this down.</strong> Its central value is {pct(b.probability_sustained)}, but that mostly reflects PMMA, the reference material the model learned from. It says nothing specific about this material.</p>
    </>}
    {!estimate && <p className={s.note}>Model cross-check (not tested): {pct(b.probability_sustained)} chance of sustained burning (95% interval {pct(b.interval_95[0])}–{pct(b.interval_95[1])}). The tested records above are the evidence.</p>}
    {b.material_group === null && b.informative !== false && <p className={`${s.note} ${s.amber}`}><strong>No data for this material in the model.</strong> The interval includes the full spread between the materials it learned from, so it is wide.</p>}
    {b.airflow_assumption && <p className={s.muted}>{b.airflow_assumption}</p>}
    <p className={`${s.note} ${v.beats_baseline ? s.green : s.amber}`}><strong>Measured error.</strong> {v.statement}</p>
    <details className={s.details}><summary>How this estimate was made and its limits</summary>
      <ul>
        <li>Bayesian logistic regression on {b.trained_on.n_runs} labelled microgravity runs ({Object.entries(b.trained_on.by_investigation).map(([k, n]) => `${k} ${n}`).join(', ')}); oxygen {b.trained_on.o2_range[0]}–{b.trained_on.o2_range[1]}%, airflow {b.trained_on.flow_range_cm_s[0]}–{b.trained_on.flow_range_cm_s[1]} cm/s.</li>
        <li>Each +1 point of O₂ multiplies the odds of sustained burning by {b.oxygen_odds_ratio_per_point[0]} (95% interval {b.oxygen_odds_ratio_per_point[1]}–{b.oxygen_odds_ratio_per_point[2]}).</li>
        {v.per_investigation.map(i => <li key={i.investigation}>Held out {i.investigation} (n={i.n}): Brier {i.model_brier} vs {i.baseline_brier} for a constant guess.</li>)}
        {b.caveats.map(c => <li key={c}>{c}</li>)}
      </ul>
    </details>
  </>;
}

export function AnswerBody({ r }: { r: AssessResult }) {
  const st = statusOf(r), tier = TIER[st];
  const groups = r.evidence_groups.filter(g => g.records.length > 0), total = groups.reduce((n, g) => n + g.total_in_group, 0);
  return <section className={`${s.card} ${s[tier]}`} aria-live="polite">
    <div className={s.head}>
      <div><div className={s.eyebrow}>{st === 'tested' ? 'TESTED EVIDENCE FROM NASA DATA' : st === 'estimate' ? 'MODEL ESTIMATE · NOT TESTED' : 'NO ANSWER · NO DIRECT EVIDENCE'}</div>
        <h3 className={s.title}>{r.material ? r.material.name_en : 'Material not in the NASA data'}</h3></div>
      <span className={`${s.badge} ${s[tier]}`}>{STATUS_LABEL[st]}</span>
    </div>
    <p className={s.reason}>{r.verdict_reason}</p>
    {st === 'estimate' && r.burn_prediction && <Prediction b={r.burn_prediction} />}
    {st === 'tested' && <>
      <div className={s.sub}>{total} MATCHED RECORD{total === 1 ? '' : 'S'} (closest first)</div>
      <div className={s.records}>{groups.flatMap(g => g.records.slice(0, 3)).slice(0, 6).map(rec => <RecordItem key={rec.experiment_id} r={rec} />)}</div>
      {r.earth_vs_space?.comparison_text && <p className={s.note}><strong>Earth test vs microgravity.</strong> {r.earth_vs_space.comparison_text}</p>}
      {r.earth_vs_space?.banner && <p className={`${s.note} ${s.amber}`}><strong>⚠ {r.earth_vs_space.banner}</strong></p>}
      {r.burn_prediction && <details className={s.details}><summary>Model cross-check (not tested)</summary><Prediction b={r.burn_prediction} /></details>}
    </>}
    {st !== 'tested' && r.nearest_evidence.length > 0 && <>
      <div className={s.sub}>NEAREST TESTED RECORDS (CONTEXT ONLY, NOT A PREDICTION)</div>
      <div className={s.records}>{r.nearest_evidence.map(n => <RecordItem key={n.record.experiment_id} r={n.record} />)}</div>
    </>}
    {st === 'none' && <p className={s.note}>NASA has no tested result here, and no model estimate applies. {r.gaps[0] && <><strong>Suggested test (not a result):</strong> {r.gaps[0].reason}</>}</p>}
    {r.warnings.length > 0 && <details className={s.details}><summary>{r.warnings.length} note{r.warnings.length === 1 ? '' : 's'}</summary><ul>{r.warnings.map(w => <li key={w}>{w}</li>)}</ul></details>}
  </section>;
}

export default function MaterialAnswer({ query, conditions }: { query: string; conditions: Conditions }) {
  const key = query.trim() ? `${query.trim()}|${conditionsKey(conditions)}` : null;
  const { data, error, loading } = useKeyed(key, () => assessMaterial(toAssessBody(query, conditions)));
  if (loading) return <section className={`${s.card} ${s.grey}`}><p className={s.muted}>Looking up “{query}”… (the free server can take up to a minute to wake)</p></section>;
  if (error) return <section className={`${s.card} ${s.grey}`}><p className={s.err}>{error}</p></section>;
  return data ? <AnswerBody r={data} /> : null;
}
