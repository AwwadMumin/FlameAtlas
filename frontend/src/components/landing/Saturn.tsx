import styles from '@/app/Landing.module.css';

/** A ringed planet, the same shape as the Flame Atlas logo. Pure CSS, decorative. */
export default function Saturn() {
  return <div className={styles.saturn} role="img" aria-label="Decorative ringed planet, like the Flame Atlas logo">
    <div className={styles.halo} />
    <div className={`${styles.ring} ${styles.ringBack}`} />
    <div className={styles.planet}><span className={styles.bands} /><span className={styles.shade} /></div>
    <div className={`${styles.ring} ${styles.ringFront}`} />
    <div className={styles.moonOrbit}><span className={styles.moon} /></div>
    <span className={`${styles.spark} ${styles.sparkA}`} /><span className={`${styles.spark} ${styles.sparkB}`} />
  </div>;
}
