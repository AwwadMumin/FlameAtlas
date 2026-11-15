"use client";

import { useEffect, useRef } from 'react';
import type { Experiment } from './api';
import styles from './ExperimentDetailDrawer.module.css';
import Button from './Button';

type ExperimentDetailDrawerProps = {
  experiment: Experiment;
  selected: boolean;
  onClose: () => void;
  onToggle: () => void;
};

function displayValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === ''
    ? 'Not provided'
    : String(value);
}

function isWebUrl(value: string | null): value is string {
  if (!value) return false;
  try {
    const protocol = new URL(value).protocol;
    return protocol === 'http:' || protocol === 'https:';
  } catch {
    return false;
  }
}

export default function ExperimentDetailDrawer({
  experiment,
  selected,
  onClose,
  onToggle,
}: ExperimentDetailDrawerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const handleClose = () => onCloseRef.current();

    dialog.addEventListener('close', handleClose);
    dialog.showModal();
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    return () => {
      dialog.removeEventListener('close', handleClose);
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, []);

  const sourceUrl = isWebUrl(experiment.source_url) ? experiment.source_url : null;

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby="experiment-drawer-title"
      aria-describedby="experiment-drawer-summary"
      onClick={(event) => {
        if (event.target === event.currentTarget) dialogRef.current?.close();
      }}
    >
      <div className={styles.drawer}>
        <header className={styles.header}>
          <span className={styles.eyebrow}>Experiment record</span>
          <button
            ref={closeButtonRef}
            className={styles.closeButton}
            type="button"
            aria-label="Close experiment details"
            onClick={() => dialogRef.current?.close()}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>

        <div className={styles.content}>
          <p className={styles.program}>{displayValue(experiment.program)}</p>
          <h2 className={styles.title} id="experiment-drawer-title">
            {displayValue(experiment.title)}
          </h2>
          <p className={styles.summary} id="experiment-drawer-summary">
            {displayValue(experiment.summary)}
          </p>

          <section className={styles.section} aria-labelledby="experiment-conditions-heading">
            <div className={styles.sectionHeading}>
              <span className={styles.sectionIndex} aria-hidden="true">01</span>
              <h3 id="experiment-conditions-heading">Experimental conditions</h3>
            </div>
            <dl className={styles.fields}>
              <div className={styles.field}>
                <dt>Material</dt><dd>{displayValue(experiment.material)}</dd>
              </div>
              <div className={styles.field}>
                <dt>Gravity regime</dt><dd>{displayValue(experiment.gravity)}</dd>
              </div>
              <div className={styles.field}>
                <dt>Oxygen concentration</dt><dd>{displayValue(experiment.oxygen)}</dd>
              </div>
              <div className={styles.field}>
                <dt>Airflow velocity</dt><dd>{displayValue(experiment.airflow)}</dd>
              </div>
              <div className={styles.field}>
                <dt>Publication year</dt><dd>{displayValue(experiment.year)}</dd>
              </div>
            </dl>
          </section>

          <section className={styles.section} aria-labelledby="experiment-provenance-heading">
            <div className={styles.sectionHeading}>
              <span className={styles.sectionIndex} aria-hidden="true">02</span>
              <h3 id="experiment-provenance-heading">Source provenance</h3>
            </div>
            <dl className={styles.fields}>
              <div className={styles.field}>
                <dt>Record ID</dt><dd className={styles.mono}>{displayValue(experiment.id)}</dd>
              </div>
              <div className={styles.field}>
                <dt>Source ID</dt><dd className={styles.mono}>{displayValue(experiment.source_id)}</dd>
              </div>
            </dl>
            {sourceUrl ? (
              <a className={styles.sourceLink} href={sourceUrl} target="_blank" rel="noreferrer">
                Open original source <span aria-hidden="true">↗</span>
              </a>
            ) : (
              <p className={styles.missingSource}>Original source link not provided.</p>
            )}
          </section>
        </div>

        <footer className={styles.footer}>
          <p className={styles.footerNote}>
            Missing fields reflect the information supplied with this research record.
          </p>
          <Button
            className={styles.toggleButton}
            type="button"
            aria-pressed={selected}
            onClick={onToggle}
          >
            {selected ? 'Remove from comparison' : 'Add to comparison'}
          </Button>
        </footer>
      </div>
    </dialog>
  );
}
