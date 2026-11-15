"use client";
import { useState } from 'react';
import ConditionsBar from './ConditionsBar';
import MaterialAnswer from './MaterialAnswer';
import { DEFAULT_CONDITIONS, type Conditions } from './material-logic';
import { listPresets, searchMaterials } from './materials-api';
import Spinner from './Spinner';
import { useKeyed } from './use-keyed';
import s from './MaterialAnswer.module.css';

/** Explorer search → if the text is a material, show its answer: tested evidence, model estimate, or no answer. */
export default function MaterialSearchAnswer({ query }: { query: string }) {
  const q = query.trim();
  const [cond, setCond] = useState<Conditions>(DEFAULT_CONDITIONS);
  const [chosen, setChosen] = useState<{ q: string; name: string } | null>(null);   // user picked a suggestion or asked for an unknown material
  const presets = useKeyed('presets', listPresets);
  const search = useKeyed(q.length >= 2 ? q : null, () => searchMaterials(q), 450);
  if (q.length < 2) return null;
  const matches = search.data?.matches ?? [], top = matches[0];
  const target = chosen && chosen.q === q ? chosen.name : top?.confident ? top.material.name_en : null;
  return <section className="panel" style={{ padding: 24, marginBottom: 20 }} aria-label="Material answer">
    <div className={s.eyebrow}>MATERIAL ANSWER</div>
    {search.loading && <p className={s.muted} style={{ display: 'flex', alignItems: 'center', gap: 12 }}><Spinner inline size={20} label="Searching" /> Checking whether “{q}” is a material…</p>}
    {search.error && <p className={s.err}>{search.error}</p>}
    {search.data && !target && <>
      {matches.length > 0
        ? <p className={s.reason}>No exact material match for “{q}”. Did you mean: {matches.slice(0, 3).map(m => <button key={m.material.material_id} type="button" className="btn ghost" style={{ marginRight: 8 }} onClick={() => setChosen({ q, name: m.material.name_en })}>{m.material.name_en}</button>)}</p>
        : <p className={s.reason}>“{q}” is not in the NASA material catalog. The table below shows any experiment that mentions it.</p>}
      <p className={s.muted}>If “{q}” is a material, the model can still estimate its microgravity burn outcome. It will be labelled “Model estimate — not tested” with a wide interval.</p>
      <button type="button" className="btn outline" onClick={() => setChosen({ q, name: q })}>Treat “{q}” as a material →</button>
    </>}
    {target && <div style={{ marginTop: 14 }}>
      <ConditionsBar value={cond} onChange={setCond} presets={presets.data?.presets ?? []} />
      <div style={{ marginTop: 16 }}><MaterialAnswer query={target} conditions={cond} /></div>
    </div>}
  </section>;
}
