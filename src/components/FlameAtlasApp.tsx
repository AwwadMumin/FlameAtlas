"use client";
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { askResearch, compareExperiments, fetchExperiments, type Answer, type ComparisonResult, type Experiment } from './api';
import Atmosphere from './Atmosphere';
import { filterExperiments } from './explorer-search';
import ExperimentDetailDrawer from './ExperimentDetailDrawer';
import ScenarioForm from './ScenarioForm';
import Button from './Button';
import MaterialSearchAnswer from './MaterialSearchAnswer';
import MaterialsPage from './MaterialsPage';
import { safeSourceUrl } from './safe-url';
import { usePathname, useRouter } from 'next/navigation';
import Image from 'next/image';

const subscribeToHydration = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

type Page = 'explore' | 'materials' | 'compare' | 'ask';
const DEMO: Experiment[] = [
  {id:'demo-bass-ii',program:'BASS-II',title:'Burning and Suppression of Solids II',material:'Fabric',gravity:'Microgravity',oxygen:null,airflow:null,year:2017,summary:'Microgravity solid-fuel combustion research program.',source_url:null,source_id:null},
  {id:'demo-bass',program:'BASS',title:'Burning and Suppression of Solids',material:'Fabric',gravity:'Microgravity',oxygen:null,airflow:null,year:2015,summary:'Microgravity burning and suppression experiments.',source_url:null,source_id:null},
  {id:'demo-saffire',program:'SAFFIRE',title:'Spacecraft Fire Experiment',material:'Composite',gravity:'Microgravity',oxygen:null,airflow:null,year:2021,summary:'Large-scale spacecraft fire research program.',source_url:null,source_id:null},
  {id:'demo-mstf',program:'MSTF',title:'Microgravity Solid-Fuel Testing',material:'Polymer',gravity:'Microgravity',oxygen:null,airflow:null,year:null,summary:'Solid-fuel flame-spread research context.',source_url:null,source_id:null},
];
const labels: Record<Page,string> = {explore:'Evidence Explorer',materials:'Materials',compare:'Scenario Ranker',ask:'Ask with Citations'};
const format = (value: string | number | null | undefined, unit='') => value === null || value === undefined || value === '' ? '—' : `${value}${unit}`;

export default function App() {
  const router = useRouter();
  const pathname = usePathname();
  const page: Page = pathname === '/materials' ? 'materials' : pathname === '/ranker' ? 'compare' : pathname === '/ask' ? 'ask' : 'explore';
  const [mode,setMode] = useState<'live'|'demo'>('demo');
  const hydrated = useSyncExternalStore(subscribeToHydration, clientSnapshot, serverSnapshot);
  const [restored,setRestored] = useState(false);
  const [data,setData] = useState<Experiment[]>([]);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState('');
  const [query,setQuery] = useState('');
  const [material,setMaterial] = useState('All materials');
  const [gravity,setGravity] = useState('All gravity');
  const [selected,setSelected] = useState<string[]>([]);
  const [detail,setDetail] = useState<Experiment|null>(null);
  const [comparison,setComparison] = useState<ComparisonResult|null>(null);
  const [compareLoading,setCompareLoading] = useState(false);
  const [question,setQuestion] = useState('');
  const [answer,setAnswer] = useState<Answer|null>(null);
  const [asking,setAsking] = useState(false);
  const [actionError,setActionError] = useState('');

  if (hydrated && !restored) {
    try {
      const savedMode = window.sessionStorage.getItem('flame-atlas-mode');
      if (savedMode === 'live' || savedMode === 'demo') {
        setMode(savedMode);
        setLoading(savedMode === 'live');
      }
      const savedSelected = JSON.parse(window.sessionStorage.getItem('flame-atlas-selected') || '[]');
      if (Array.isArray(savedSelected) && savedSelected.every((v: unknown) => typeof v === 'string')) setSelected(savedSelected);
    } catch { /* Storage can be unavailable in private browsing. */ }
    setRestored(true);
  }
  useEffect(() => { if (!restored) return; try { window.sessionStorage.setItem('flame-atlas-mode', mode); } catch {} }, [mode,restored]);
  useEffect(() => { if (!restored) return; try { window.sessionStorage.setItem('flame-atlas-selected', JSON.stringify(selected)); } catch {} }, [selected,restored]);
  useEffect(()=>{ if(mode !== 'live') return; let active=true;
    fetchExperiments().then(items=>{if(active)setData(items);}).catch(e=>{if(active){setData([]);setError(e.message);}}).finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[mode]);
  const records = mode === 'demo' ? DEMO : data;
  const filtered = useMemo(() => filterExperiments(records, query, material, gravity), [records, query, material, gravity]);
  const chosen = records.filter(r=>selected.includes(r.id));
  const navigate=(p:Page)=>{router.push(p==='explore'?'/explorer':p==='materials'?'/materials':p==='compare'?'/ranker':'/ask');setActionError('');window.scrollTo({top:0,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});};
  const toggle=(id:string)=>setSelected(current=>current.includes(id)?current.filter(x=>x!==id):[...current,id]);
  async function runComparison(){navigate('compare');setComparison(null);if(mode==='demo')return;setCompareLoading(true);try{setComparison(await compareExperiments(selected));}catch(e){setActionError((e as Error).message);}finally{setCompareLoading(false);}}
  async function submitQuestion(e:React.FormEvent){e.preventDefault();const cleanQuestion = question.trim();if(!cleanQuestion){setActionError('Please enter a research question.');return;}if(cleanQuestion.length>1000){setActionError('Your question must be 1000 characters or fewer.');return;}setAnswer(null);setActionError('');if(mode==='demo'){setActionError('AI answers require the research backend. Switch to Live data after your team connects the API.');return;}setAsking(true);try{setAnswer(await askResearch(cleanQuestion,selected));}catch(e){setActionError((e as Error).message);}finally{setAsking(false);}}
  return <div className="shell">
    <Atmosphere />
    <header className="topbar">
      <button className="brand" onClick={()=>navigate('explore')} aria-label="Flame Atlas home"><span className="brand-mark"><Image src="/flame-atlas-logo.png" alt="Flame Atlas logo" width={48} height={48}/></span><span><strong>FLAME ATLAS</strong><small>COMBUSTION RESEARCH INTELLIGENCE</small></span></button>
      <nav aria-label="Main navigation">{(['explore','materials','compare','ask'] as Page[]).map(p=><button key={p} className={page===p?'active':''} aria-current={page===p?'page':undefined} onFocus={event=>{if(window.matchMedia('(max-width: 850px)').matches)event.currentTarget.scrollIntoView({block:'nearest',inline:'nearest',behavior:'auto'});}} onClick={()=>navigate(p)}>{labels[p]}{p==='compare'&&selected.length>0?<em>{selected.length}</em>:null}</button>)}</nav>
      <div className="mode-switch" role="group" aria-label="Data mode"><button className={mode==='live'?'chosen':''} aria-pressed={mode==='live'} onClick={()=>{if(mode==='live')return;setMode('live');setLoading(true);setError('');setSelected([]);setComparison(null);setAnswer(null);}}>Live</button><button className={mode==='demo'?'chosen':''} aria-pressed={mode==='demo'} onClick={()=>{if(mode==='demo')return;setMode('demo');setLoading(false);setError('');setSelected([]);setComparison(null);setAnswer(null);}}>Preview</button></div>
    </header>
    <main className="workspace">
      <div className="workspace-heading"><div><div className="overline">FLAME ATLAS <span>/</span> RESEARCH WORKSPACE</div><h1>{labels[page]}</h1><p>{page==='explore'?'Explore combustion experiments, inspect research conditions, and trace original evidence.':page==='materials'?'Every material in the NASA data: tested evidence where it exists, a labelled model estimate where it does not.':page==='compare'?'Evaluate experimental conditions and compare scientifically compatible evidence.':'Ask research questions and inspect the citations behind every answer.'}</p></div><div className="workspace-status" role="status" aria-live="polite" aria-atomic="true"><span className={mode==='live'?'dot':'dot amber'} aria-hidden="true"/>{mode==='live'?(loading?'Live · Connecting to research API':error?'Live · Research API unavailable':data.length?'Live · Research API connected':'Live · Research API · no records'):'Preview · Example data only'}</div></div>
      {mode==='demo'&&<div className="preview-note">Interface preview uses program-level examples for navigation and layout only. Switch to Live when your team connects the NASA data service.</div>}
      {page==='materials'&&<MaterialsPage live={mode==='live'} onGoLive={()=>{setMode('live');setLoading(true);setError('');}}/>}
      {page==='explore'&&<>
        <section className="panel search-panel"><form onSubmit={e=>{e.preventDefault();}}><label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search experiments, materials, programs or source identifiers" aria-label="Search experiments"/><kbd>SEARCH</kbd></label><div className="filter-row"><label>Material<select value={material} onChange={e=>setMaterial(e.target.value)}><option>All materials</option>{Array.from(new Set(records.map(r=>r.material).filter(Boolean))).map(m=><option key={m}>{m}</option>)}</select></label><label>Gravity regime<select value={gravity} onChange={e=>setGravity(e.target.value)}><option>All gravity</option>{Array.from(new Set(records.map(r=>r.gravity).filter(Boolean))).map(g=><option key={g}>{g}</option>)}</select></label><Button type="button" variant="ghost" onClick={()=>{setQuery('');setMaterial('All materials');setGravity('All gravity');}}>Clear filters</Button><Button type="submit" variant="primary">Search evidence <span>→</span></Button></div></form></section>
        {mode==='live'&&<MaterialSearchAnswer query={query}/>}
        <div className="metrics"><div><span>EXPERIMENT RECORDS</span><strong>{loading?'…':records.length}</strong><small>Available in current dataset</small></div><div><span>VISIBLE RESULTS</span><strong>{filtered.length}</strong><small>Matching current filters</small></div><div><span>SELECTED EVIDENCE</span><strong>{selected.length}</strong><small>Ready for comparison</small></div></div>
        <section className="panel results"><div className="panel-title"><div><span className="overline">DATA EXPLORATION</span><h2>Experiment catalog</h2></div><span role="status" aria-live="polite">{filtered.length} {filtered.length===1?'record':'records'}</span></div>
          {loading?<div className="empty"><h3>Loading experiment catalog…</h3><p>Retrieving records from the research service.</p></div>:error&&mode==='live'?<div className="empty"><h3>Connect your NASA research data service</h3><p>The frontend is ready to display real experiments. Configure <code>NEXT_PUBLIC_API_BASE_URL</code> and implement <code>GET /api/experiments</code>.</p><small>{error}</small><Button variant="outline" onClick={()=>setMode('demo')}>Explore interface preview →</Button></div>:filtered.length===0?<div className="empty"><h3>{records.length?'No matching experiments':'No experiment records yet'}</h3><p>Adjust your filters or connect your NASA dataset to begin.</p></div>:<div className="table-wrap"><table><thead><tr><th aria-label="Select"/><th>EXPERIMENT / PROGRAM</th><th>MATERIAL</th><th>GRAVITY</th><th>OXYGEN</th><th>AIRFLOW</th><th>SOURCE</th></tr></thead><tbody>{filtered.map(r=><tr key={r.id} className={selected.includes(r.id)?'row-selected':''}><td><input type="checkbox" aria-label={`Select ${r.title}`} checked={selected.includes(r.id)} onChange={()=>toggle(r.id)}/></td><td><button className="record-link" onClick={()=>setDetail(r)}><strong>{r.title}</strong><small>{r.program} · {format(r.year)}</small></button></td><td>{r.material}</td><td>{r.gravity}</td><td className="numeric">{format(r.oxygen)}</td><td className="numeric">{format(r.airflow)}</td><td><button className="inline-link" onClick={()=>setDetail(r)}>View record ↗</button></td></tr>)}</tbody></table></div>}
          <div className="table-footer"><span>Research records retain source identifiers and units supplied by the backend.</span>{selected.length>0&&<Button variant="primary" onClick={runComparison} disabled={selected.length<2}>Compare {selected.length} selected →</Button>}</div></section>
        <section className="below-grid"><div className="panel insight"><div className="panel-title"><div><span className="overline">RESEARCH WORKFLOW</span><h2>From evidence to insight</h2></div></div><div className="workflow"><span>01 <strong>Find evidence</strong></span><b>→</b><span>02 <strong>Compare conditions</strong></span><b>→</b><span>03 <strong>Ask with citations</strong></span></div><p>Explore NASA source records, select experiments with relevant conditions, and send your evidence context to the AI research assistant.</p></div><div className="panel source-info"><div className="panel-title"><div><span className="overline">SOURCE PROVENANCE</span><h2>Traceable research</h2></div></div><p>Original publications, experiment metadata, source links, and citation identifiers appear alongside results when provided by the data service.</p><button className="inline-link" onClick={()=>navigate('ask')}>Open research assistant ↗</button></div></section>
      </>}
      {page==='compare'&&<><ScenarioForm key={mode} mode={mode}/><section className="panel compare-head"><div><span className="overline">SCENARIO ANALYSIS</span><h2>Selected experiment context</h2><p>Compare materials, gravity conditions, oxygen levels, and airflow before interpreting results.</p></div><button className="btn outline" onClick={()=>navigate('explore')}>← Back to catalog</button></section>{chosen.length===0?<div className="panel empty"><h3>No experiments selected</h3><p>Select two or more records from the Evidence Explorer to begin.</p><button className="btn primary" onClick={()=>navigate('explore')}>Explore evidence →</button></div>:<><div className="panel results"><div className="panel-title"><h2>Conditions matrix</h2><span>{chosen.length} selected</span></div><div className="table-wrap"><table><thead><tr><th>EXPERIMENT</th><th>MATERIAL</th><th>GRAVITY</th><th>OXYGEN</th><th>AIRFLOW</th><th>RECORD</th></tr></thead><tbody>{chosen.map(r=><tr key={r.id}><td><strong>{r.program}</strong><small className="table-sub">{r.title}</small></td><td>{r.material}</td><td>{r.gravity}</td><td className="numeric">{format(r.oxygen)}</td><td className="numeric">{format(r.airflow)}</td><td><button className="inline-link" onClick={()=>setDetail(r)}>Inspect ↗</button></td></tr>)}</tbody></table></div></div><section className="panel analysis"><span className="overline">SCIENTIFIC COMPARABILITY</span><h2>Evidence assessment</h2>{compareLoading?<p>Evaluating source conditions…</p>:comparison?<><p>{comparison.summary}</p><div className="analysis-grid">{comparison.items.map(item=><div key={item.experiment_id}><strong>{item.experiment_id}</strong><span>{item.comparable?'Comparable':'Context only'}</span><p>{item.reason}</p></div>)}</div></>:<p>{mode==='demo'?'Preview records demonstrate the comparison workflow. Source-based scientific assessment becomes available with the research backend.':'Run the comparison service to evaluate whether selected measurements are scientifically compatible.'}</p>}<section className="scientific-limitations" aria-labelledby="limitations-heading"><div className="limitations-heading"><div><span className="overline">RESEARCH TRANSPARENCY</span><h3 id="limitations-heading">Scientific Limitations &amp; Interpretation</h3></div><span className="limitation-count">{comparison?.limitations?.length ?? 0} source-derived limitations</span></div>
{comparison?.limitations?.length ? <div className="limitations-list">{comparison.limitations.map(limit=><article key={limit.id} className="limitation-item"><div className="limitation-meta"><span>{limit.category.replace(/_/g,' ')}</span>{limit.severity&&<span>{limit.severity}</span>}</div><h4>{limit.title}</h4><p>{limit.description}</p>{!!limit.affected_experiment_ids?.length&&<small>Affected records: {limit.affected_experiment_ids.join(', ')}</small>}{!!limit.source_ids?.length&&<small>Evidence IDs: {limit.source_ids.join(', ')}</small>}{!!limit.source_urls?.length&&<div className="limitation-links">{limit.source_urls.filter(url=>safeSourceUrl(url)!==null).map((url,i)=><a key={`${url}-${i}`} href={safeSourceUrl(url)!} target="_blank" rel="noopener noreferrer">View supporting source {i+1} ↗</a>)}</div>}</article>)}</div> : <div className="limitation-empty"><strong>{comparison?'No limitations returned by the comparison service':'Awaiting source-based assessment'}</strong><p>{comparison?'This does not establish that the evidence has no limitations. The research backend must return assessed limitations, or explicitly report that the review is incomplete.':'When experiments are compared, the backend should supply evidence-specific constraints on conditions, coverage, uncertainty, methodology and interpretation.'}</p></div>}
{comparison?.methodology&&<div className="methodology"><strong>Comparison methodology</strong><p>{comparison.methodology}</p></div>}
{comparison?.sources?.length ? <div className="comparison-sources"><strong>Supporting research sources</strong>{comparison.sources.map((source,i)=><div key={`${source.source_id}-${i}`}><span>{source.title} · {source.source_id}</span>{safeSourceUrl(source.url)&&<a href={safeSourceUrl(source.url)!} target="_blank" rel="noopener noreferrer">Original source ↗</a>}</div>)}</div>:null}
{comparison?.generated_at&&<small className="analysis-timestamp">Assessment generated: {comparison.generated_at}</small>}</section><div className="actions"><Button variant="outline" onClick={()=>setSelected([])}>Clear selection</Button><button className="btn primary" onClick={()=>{setQuestion('');navigate('ask');}}>Ask about these records →</button></div>{actionError&&<p className="form-error">{actionError}</p>}</section></>}</>}
      {page==='ask'&&<div className="ask-grid"><section className="panel chat"><div className="panel-title"><div><span className="overline">AI RESEARCH ASSISTANT</span><h2>Research conversation</h2></div><span>Source-linked answers</span></div><div className="chat-content">{!answer?<div className="chat-welcome"><div className="chat-symbol">✳</div><h2>Ask the evidence.</h2><p>Investigate microgravity flame spread, compare experimental conditions, and follow each conclusion back to its source.</p><div className="suggestions">{['How does airflow influence flame spread in microgravity?','What conditions must match for a valid comparison?','Summarize the selected experiments.'].map(q=><button key={q} onClick={()=>setQuestion(q)}>{q} ↗</button>)}</div></div>:<div className="answer"><span className="overline">RESEARCH RESPONSE</span><h3>{question}</h3><p>{answer.answer}</p>{answer.limitations&&<div className="answer-limit"><strong>Interpretation notes</strong><p>{answer.limitations}</p></div>}</div>}</div><form className="chat-form" onSubmit={submitQuestion}><textarea aria-label="Research question" placeholder="Ask a scientific question about the evidence…" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={1000} rows={3}/><div><small>{selected.length} experiments in research context</small><Button type="submit" variant="primary" disabled={!question.trim()||asking}>{asking?'Analyzing…':'Ask Flame Atlas →'}</Button></div></form>{actionError&&<p className="form-error">{actionError}</p>}</section><aside className="panel citations"><div className="panel-title"><div><span className="overline">EVIDENCE CONTEXT</span><h2>Sources & citations</h2></div></div>{answer?.citations?.length?<div className="citation-list">{answer.citations.map((c,i)=><article key={`${c.source_id}-${i}`}><span>[{i+1}]</span><div><strong>{c.title}</strong><small>{c.source_id}</small>{safeSourceUrl(c.url)&&<a href={safeSourceUrl(c.url)!} target="_blank" rel="noopener noreferrer">Open original source ↗</a>}</div></article>)}</div>:chosen.length?<div className="citation-list">{chosen.map((r,i)=><article key={r.id}><span>{String(i+1).padStart(2,'0')}</span><div><strong>{r.title}</strong><small>{r.program}</small>{safeSourceUrl(r.source_url)&&<a href={safeSourceUrl(r.source_url)!} target="_blank" rel="noopener noreferrer">Original source ↗</a>}</div></article>)}</div>:<div className="citation-empty"><strong>Evidence context</strong><p>Select records in Evidence Explorer or ask a question to retrieve cited sources from the research service.</p></div>}</aside></div>}
    </main>
    {detail&&<ExperimentDetailDrawer experiment={detail} selected={selected.includes(detail.id)} onClose={()=>setDetail(null)} onToggle={()=>toggle(detail.id)}/>}
    <footer className="footer"><span>FLAME ATLAS <b>·</b> Microgravity Combustion Research</span><span>NASA Space Apps Challenge · 2026</span></footer>
  </div>;
}

