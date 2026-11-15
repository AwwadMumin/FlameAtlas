"use client";
import { useEffect, useState } from 'react';
import { GUIDE, VOICES } from '@/data/voices';
import { TEAM_FEEDBACK } from '@/data/team-feedback';
import styles from '@/app/Landing.module.css';

const SLIDE_MS = 7000;

/** Auto-advancing, pausable carousel of real NASA findings (and real team feedback, if any is added). */
export default function Voices() {
  const [i, setI] = useState(0), [paused, setPaused] = useState(false);
  const n = VOICES.length;
  useEffect(() => {
    if (paused || n < 2 || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const t = setInterval(() => setI(x => (x + 1) % n), SLIDE_MS);
    return () => clearInterval(t);
  }, [paused, n]);
  const v = VOICES[i];
  return <section id="evidence" className={styles.voices} aria-labelledby="voices-title">
    <div className={styles.sectionHead}>
      <span className={styles.kicker}>FROM NASA&apos;S OWN RESEARCH</span>
      <h2 id="voices-title">What the researchers found.<br /><span>Why this evidence matters.</span></h2>
    </div>
    <div className={styles.voiceStage} onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}>
      <button type="button" className={styles.voiceNav} onClick={() => setI((i + n - 1) % n)} aria-label="Previous finding">←</button>
      <figure key={v.id} className={styles.voiceCard} aria-live="polite">
        <span className={styles.voiceBadge}>{v.id}</span>
        <blockquote>{v.text}</blockquote>
        <figcaption><strong>{v.topic}</strong><span>{GUIDE.publisher} · {GUIDE.title} ({GUIDE.document}, {GUIDE.year}), p. {v.page}</span></figcaption>
      </figure>
      <button type="button" className={styles.voiceNav} onClick={() => setI((i + 1) % n)} aria-label="Next finding">→</button>
    </div>
    <div className={styles.dots} role="tablist" aria-label="Choose a finding">{VOICES.map((x, k) => <button key={x.id} type="button" role="tab" aria-selected={k === i} aria-label={`Finding ${k + 1}`} className={k === i ? styles.dotOn : ''} onClick={() => setI(k)} />)}</div>
    <p className={styles.voiceNote}>Paraphrased by our team from the NASA guide, with the page number so you can check each one.</p>
    {TEAM_FEEDBACK.length > 0 && <div className={styles.feedbackGrid}>{TEAM_FEEDBACK.map(f => <figure key={f.name} className={styles.feedbackCard}><blockquote>{f.quote}</blockquote><figcaption><strong>{f.name}</strong><span>{f.role}</span></figcaption></figure>)}</div>}
  </section>;
}
