"use client";
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import styles from '@/app/Landing.module.css';

const QUICK = ['Acrylic (PMMA)', 'Nomex', 'Silicone', 'PET'];

/** One search box: type a material and land on its answer (tested evidence, model estimate, or no direct evidence). */
export default function HeroSearch() {
  const router = useRouter();
  const [q, setQ] = useState('');
  const go = (text: string) => router.push(text.trim() ? `/explorer?q=${encodeURIComponent(text.trim().slice(0, 100))}` : '/explorer');
  const submit = (e: FormEvent) => { e.preventDefault(); go(q); };
  return <div className={styles.search}>
    <form onSubmit={submit} role="search" aria-label="Search a material">
      <label className={styles.searchField}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg>
        <input value={q} onChange={e => setQ(e.target.value)} maxLength={100} placeholder="Search a material, e.g. acrylic, PET, Nomex" aria-label="Material name" />
      </label>
      <button type="submit" className={styles.primaryButton}>Get the answer <span aria-hidden="true">→</span></button>
    </form>
    <div className={styles.quick}><span>Try</span>{QUICK.map(m => <button key={m} type="button" onClick={() => go(m.replace(/ \(.*\)/, ''))}>{m}</button>)}</div>
  </div>;
}
