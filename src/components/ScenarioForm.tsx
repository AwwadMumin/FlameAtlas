"use client";

import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { assessScenario, type AssessmentGravity, type ScenarioAssessment } from './api';
import styles from './ScenarioForm.module.css';
import Button from './Button';

type Props = { mode: 'live' | 'demo' };
type ScenarioFields = {
  material: string;
  gravity: AssessmentGravity;
  oxygen: string;
  pressure: string;
  airflow: string;
};
type ResultState = { mode: Props['mode']; fields: ScenarioFields; response: ScenarioAssessment };

const initialFields: ScenarioFields = {
  material: '',
  gravity: 'orbit',
  oxygen: '',
  pressure: '',
  airflow: '',
};

function optionalNumber(value: string): number | null {
  return value.trim() === '' ? null : Number(value);
}

export default function ScenarioForm({ mode }: Props) {
  const [fields, setFields] = useState<ScenarioFields>(initialFields);
  const [result, setResult] = useState<ResultState | null>(null);
  const [demoNotice, setDemoNotice] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);
  const fieldsKey = JSON.stringify(fields);
  const visibleResult = result?.mode === mode && JSON.stringify(result.fields) === fieldsKey ? result.response : null;

  useEffect(() => () => { requestId.current += 1; }, []);

  function update<K extends keyof ScenarioFields>(key: K, value: ScenarioFields[K]) {
    requestId.current += 1;
    setFields(current => ({ ...current, [key]: value }));
    setResult(null);
    setDemoNotice(false);
    setError('');
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const material = fields.material.trim();
    if (!material) {
      setError('Enter a material or material name before assessing this scenario.');
      return;
    }

    setResult(null);
    setError('');
    if (mode === 'demo') {
      setDemoNotice(true);
      return;
    }

    const id = ++requestId.current;
    setLoading(true);
    try {
      const response = await assessScenario({
        material_query: material,
        gravity: fields.gravity,
        oxygen_pct: optionalNumber(fields.oxygen),
        pressure_kpa: optionalNumber(fields.pressure),
        airflow_cm_s: optionalNumber(fields.airflow),
        use_llm: false,
      });
      if (requestId.current === id) setResult({ mode, fields: { ...fields }, response });
    } catch (cause) {
      if (requestId.current === id) setError(cause instanceof Error ? cause.message : 'The assessment could not be completed.');
    } finally {
      if (requestId.current === id) setLoading(false);
    }
  }

  function reset() {
    requestId.current += 1;
    setFields(initialFields);
    setResult(null);
    setDemoNotice(false);
    setError('');
    setLoading(false);
  }

  return (
    <section className={styles.card} aria-labelledby="scenario-heading">
      <div className={styles.heading}>
        <div>
          <span className={styles.eyebrow}>SCENARIO ASSESSMENT</span>
          <h2 id="scenario-heading">Explore a scenario</h2>
          <p>Enter conditions to request an evidence-based assessment from the research service.</p>
        </div>
        <span className={styles.mode}>{mode === 'live' ? 'LIVE DATA' : 'PREVIEW MODE'}</span>
      </div>

      <form onSubmit={submit}>
        <fieldset className={styles.fields} disabled={loading}>
          <legend className={styles.visuallyHidden}>Scenario inputs</legend>
          <label className={styles.materialField}>
            <span>Material <b aria-hidden="true">*</b></span>
            <input
              type="text"
              value={fields.material}
              onChange={event => update('material', event.target.value)}
              placeholder="e.g. acrylic"
              autoComplete="off"
              required
              aria-required="true"
              aria-describedby="scenario-material-help"
            />
            <small id="scenario-material-help">Enter a material name or query.</small>
          </label>
          <label>
            <span>Gravity regime</span>
            <select value={fields.gravity} onChange={event => update('gravity', event.target.value as AssessmentGravity)}>
              <option value="orbit">Orbit</option>
              <option value="microgravity">Microgravity</option>
              <option value="earth">Earth</option>
              <option value="1g">1g</option>
              <option value="moon">Moon</option>
              <option value="mars">Mars</option>
            </select>
          </label>
          <label>
            <span>Oxygen (%)</span>
            <input type="number" min="0" max="100" step="any" inputMode="decimal" value={fields.oxygen} onChange={event => update('oxygen', event.target.value)} placeholder="Optional" />
          </label>
          <label>
            <span>Pressure (kPa)</span>
            <input type="number" min="0" step="any" inputMode="decimal" value={fields.pressure} onChange={event => update('pressure', event.target.value)} placeholder="Optional" />
          </label>
          <label>
            <span>Airflow (cm/s)</span>
            <input type="number" min="0" step="any" inputMode="decimal" value={fields.airflow} onChange={event => update('airflow', event.target.value)} placeholder="Optional" />
          </label>
        </fieldset>
        <div className={styles.actions}>
          <Button type="button" className={styles.reset} onClick={reset}>Reset</Button>
          <Button type="submit" className={styles.submit} disabled={loading}>{loading ? 'Assessing…' : 'Assess scenario'} <span aria-hidden="true">→</span></Button>
        </div>
      </form>

      {loading && <p className={styles.status} role="status">Requesting an assessment…</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
      {demoNotice && <p className={styles.notice} role="status"><strong>Preview only.</strong> Your scenario has not been sent to the API, and no assessment or ranking was generated. Switch to Live data to request an assessment.</p>}
      {visibleResult && (
        <section className={styles.result} aria-label="Assessment summary" aria-live="polite">
          <div className={styles.resultHeading}>
            <div>
              <span className={styles.eyebrow}>ASSESSMENT SUMMARY · NOT THE FULL EVIDENCE REPORT</span>
              <h3>{visibleResult.verdict_label}</h3>
              <code className={styles.verdict}>{visibleResult.verdict}</code>
            </div>
            <span className={`${styles.tier} ${styles[visibleResult.verdict_tier]}`}>{visibleResult.verdict_tier}</span>
          </div>
          {visibleResult.matched_tolerances?.text && <p className={styles.tolerances}><strong>Matched conditions:</strong> {visibleResult.matched_tolerances.text}</p>}
          <p className={styles.reason}>{visibleResult.verdict_reason}</p>
          <p className={styles.summary}>{visibleResult.summary_text}</p>
          {visibleResult.summary_fallback_reason && <p className={styles.fallback}>Summary note: {visibleResult.summary_fallback_reason}</p>}
          {visibleResult.warnings.length > 0 && <div className={styles.warnings}><strong>Warnings</strong><ul>{visibleResult.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></div>}
          {visibleResult.empty_state_message && <p className={styles.empty}>{visibleResult.empty_state_message}</p>}
        </section>
      )}
    </section>
  );
}
