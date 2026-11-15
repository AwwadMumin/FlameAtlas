"use client";
import { Fragment, useEffect, useRef, useState } from 'react';
import ConditionsBar from './ConditionsBar';
import MaterialAnswer, { RecordItem } from './MaterialAnswer';
import { conditionsKey, DEFAULT_CONDITIONS, filterMaterials, pct, recordCount, statusOf, STATUS_LABEL, toAssessBody, type Conditions, type Status } from './material-logic';
import { assessMaterial, listMaterials, listPresets, materialEvidence, type MaterialCard } from './materials-api';
import { useKeyed } from './use-keyed';
import a from './MaterialAnswer.module.css';
import s from './MaterialsPage.module.css';

type Cell = { status: Status; p: number | null; lo: number | null; hi: number | null; n: number } | { error: string };
const WORKERS = 4;

function AllRecords({ id }: { id: string }) {
  const { data, error, loading } = useKeyed(id, () => materialEvidence(id));
  if (loading) return <p className={a.muted}>Loading every record for this material…</p>;
  if (error) return <p className={a.err}>{error}</p>;
  const groups = (data?.groups ?? []).filter(g => g.records.length > 0), n = groups.reduce((t, g) => t + g.total_in_group, 0);
  return <div>
    <h4>ALL NASA RECORDS FOR THIS MATERIAL ({n}{data && data.smoke_detection.length > 0 ? `, plus ${data.smoke_detection.length} smoke/detection` : ''})</h4>
    {groups.length === 0 && <p className={a.muted}>No burn-test records exist for this material in the data.</p>}
    {groups.map(g => <details key={g.evidence_type} className={a.details}><summary>{g.label} ({g.records.length}{g.total_in_group > g.records.length ? ` of ${g.total_in_group}` : ''})</summary>
      <div className={a.records} style={{ marginTop: 10 }}>{g.records.map(r => <RecordItem key={r.experiment_id} r={r} />)}</div></details>)}
    {data && data.smoke_detection.length > 0 && <details className={a.details}><summary>Smoke / detection records ({data.smoke_detection.length}). Not burn evidence.</summary>
      <div className={a.records} style={{ marginTop: 10 }}>{data.smoke_detection.map(r => <RecordItem key={r.experiment_id} r={r} />)}</div></details>}
  </div>;
}

export default function MaterialsPage({ live, onGoLive }: { live: boolean; onGoLive: () => void }) {
  const [cond, setCond] = useState<Conditions>(DEFAULT_CONDITIONS);
  const [text, setText] = useState('');
  const [filter, setFilter] = useState<Status | 'all'>('all');
  const [open, setOpen] = useState<string | null>(null);
  const [cells, setCells] = useState<Record<string, Cell>>({});
  const requested = useRef(new Set<string>());
  const mats = useKeyed(live ? 'materials' : null, listMaterials);
  const presets = useKeyed(live ? 'presets' : null, listPresets);
  const ck = conditionsKey(cond), list = mats.data?.materials;

  useEffect(() => {   // answer every material at the chosen conditions, a few at a time
    if (!list) return;
    const queue = list.filter(m => !requested.current.has(`${ck}|${m.material_id}`));
    queue.forEach(m => requested.current.add(`${ck}|${m.material_id}`));
    const body = (m: MaterialCard) => toAssessBody(m.name_en, cond);
    const work = async () => {
      for (let m = queue.shift(); m; m = queue.shift()) {
        const key = `${ck}|${m.material_id}`;
        try {
          const r = await assessMaterial(body(m));
          const b = r.burn_prediction;
          setCells(prev => ({ ...prev, [key]: { status: statusOf(r), p: b ? b.probability_sustained : null, lo: b ? b.interval_95[0] : null, hi: b ? b.interval_95[1] : null, n: r.evidence_groups.reduce((t, g) => t + g.total_in_group, 0) } }));
        } catch (e) { setCells(prev => ({ ...prev, [key]: { error: e instanceof Error ? e.message : String(e) } })); }
      }
    };
    for (let i = 0; i < WORKERS; i++) void work();
  }, [list, ck, cond]);

  if (!live) return <div className="panel empty"><h3>The Materials page needs live data</h3><p>It answers for every material using the research API.</p><button className="btn primary" onClick={onGoLive}>Switch to Live →</button></div>;
  if (mats.loading) return <div className="panel empty"><h3>Loading materials…</h3><p>The free server can take up to a minute to wake.</p></div>;
  if (mats.error || !list) return <div className="panel empty"><h3>Research API unavailable</h3><small>{mats.error}</small></div>;

  const cell = (m: MaterialCard) => cells[`${ck}|${m.material_id}`];
  const counts = { tested: 0, estimate: 0, none: 0, wait: 0 };
  for (const m of list) { const c = cell(m); if (!c || 'error' in c) counts.wait++; else counts[c.status]++; }
  const shown = filterMaterials(list, text).filter(m => { const c = cell(m); return filter === 'all' || (c && !('error' in c) && c.status === filter); });
  const FILTERS: [Status | 'all', string][] = [['all', 'All'], ['tested', 'Tested evidence'], ['estimate', 'Model estimate'], ['none', 'No direct evidence']];

  return <>
    <section className="panel" style={{ padding: 24 }}>
      <span className="overline">CONDITIONS</span>
      <p className={a.muted} style={{ margin: '6px 0 14px' }}>Every material below is answered for these conditions. Change them and the table updates.</p>
      <ConditionsBar value={cond} onChange={c => { setCond(c); setOpen(null); }} presets={presets.data?.presets ?? []} />
      <div className={s.counters}>
        <div className={s.counter}><strong>{list.length}</strong><span>MATERIALS</span></div>
        <div className={s.counter}><strong style={{ color: '#7fd9a1' }}>{counts.tested}</strong><span>TESTED EVIDENCE</span></div>
        <div className={s.counter}><strong style={{ color: '#f0c36a' }}>{counts.estimate}</strong><span>MODEL ESTIMATE</span></div>
        <div className={s.counter}><strong style={{ color: '#c3c8d0' }}>{counts.none}</strong><span>NO DIRECT EVIDENCE</span></div>
        {counts.wait > 0 && <div className={s.counter}><strong>{counts.wait}</strong><span>STILL LOADING</span></div>}
      </div>
    </section>
    <section className="panel results" style={{ marginTop: 20 }}>
      <div className="panel-title"><div><span className="overline">ALL MATERIALS</span><h2>What NASA data says, and where a model fills in</h2></div><span>{shown.length} of {list.length}</span></div>
      <div className={s.tools} style={{ padding: '0 20px' }}>
        <input className={s.search} value={text} onChange={e => setText(e.target.value)} placeholder="Filter by name (English or Arabic), alias or chemical family" aria-label="Filter materials" />
        {FILTERS.map(([k, label]) => <button key={k} type="button" className={`${s.chip} ${filter === k ? s.chipOn : ''}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>)}
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>MATERIAL</th><th>FAMILY</th><th>DATA IN NASA SET</th><th>ANSWER AT THESE CONDITIONS</th><th aria-label="Details" /></tr></thead>
        <tbody>{shown.map(m => { const c = cell(m), isOpen = open === m.material_id; return <Fragment key={m.material_id}>
          <tr className={isOpen ? s.open : undefined}>
            <td><strong>{m.name_en}</strong><span className={s.sub}>{m.name_ar}</span></td>
            <td>{m.chemical_family ?? '—'}</td>
            <td>{recordCount(m)} records<span className={s.sub}>{m.has_microgravity_evidence ? 'µg ' : ''}{m.has_1g_evidence ? '1g' : ''}{!m.has_microgravity_evidence && !m.has_1g_evidence ? 'no tested outcomes' : ''}</span></td>
            <td>{!c ? <span className={`${s.badge} ${s.wait}`}>loading…</span> : 'error' in c ? <span className={`${s.badge} ${s.wait}`} title={c.error}>unavailable</span>
              : <><span className={`${s.badge} ${s[c.status]}`}>{STATUS_LABEL[c.status]}</span>
                <span className={s.sub}>{c.status === 'tested' ? `${c.n} matched record${c.n === 1 ? '' : 's'}` : c.p !== null && c.lo !== null && c.hi !== null ? `${pct(c.p)} sustained burn (95% ${pct(c.lo)}–${pct(c.hi)})` : 'no estimate applies'}</span></>}</td>
            <td><button className="inline-link" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : m.material_id)}>{isOpen ? 'Hide ↑' : 'Details ↓'}</button></td>
          </tr>
          {isOpen && <tr><td colSpan={5}><div className={s.detail}><MaterialAnswer query={m.name_en} conditions={cond} /><AllRecords id={m.material_id} /></div></td></tr>}
        </Fragment>; })}</tbody>
      </table></div>
      <div className="table-footer"><span>Estimates are never test results. Moon and Mars always show no direct evidence.</span></div>
    </section>
  </>;
}
