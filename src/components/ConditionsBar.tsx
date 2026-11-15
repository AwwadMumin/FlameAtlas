"use client";
import { GRAVITIES, type Conditions } from './material-logic';
import type { Preset } from './materials-api';
import styles from './ScenarioForm.module.css';

export default function ConditionsBar({ value, onChange, presets }: { value: Conditions; onChange: (c: Conditions) => void; presets: Preset[] }) {
  const set = (k: keyof Conditions) => (v: string) => onChange({ ...value, [k]: v });
  return <div className={styles.fields} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 12 }}>
    <label>Mission atmosphere<select value={value.preset} onChange={e => set('preset')(e.target.value)}>
      <option value="">Custom (set oxygen)</option>{presets.map(p => <option key={p.id} value={p.id}>{p.name} · {p.o2_pct}% O₂, {p.pressure_kpa} kPa</option>)}</select></label>
    <label>Gravity<select value={value.gravity} onChange={e => set('gravity')(e.target.value)}>{GRAVITIES.map(g => <option key={g.key} value={g.key}>{g.label}</option>)}</select></label>
    <label>Oxygen % (overrides atmosphere)<input inputMode="decimal" value={value.oxygen} onChange={e => set('oxygen')(e.target.value)} placeholder="from atmosphere" /></label>
    <label>Airflow cm/s (optional)<input inputMode="decimal" value={value.airflow} onChange={e => set('airflow')(e.target.value)} placeholder="optional" /></label>
  </div>;
}
