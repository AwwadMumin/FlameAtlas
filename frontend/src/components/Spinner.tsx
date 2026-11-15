/** Orange loading ring, in the Flame Atlas theme. */
export default function Spinner({ label = 'Loading', size = 44, inline = false }: { label?: string; size?: number; inline?: boolean }) {
  return <span className={inline ? 'fa-spin-inline' : 'fa-spin-wrap'} role="status" aria-live="polite">
    <span className="fa-spinner" style={{ width: size, height: size }} aria-hidden="true" />
    <span className="fa-sr">{label}</span>
  </span>;
}
