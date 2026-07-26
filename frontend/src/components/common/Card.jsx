/**
 * Panel surface: a bordered card with an optional title row and an optional
 * right-hand action slot (a select, a toggle, a link).
 *
 * The title and the action sit on one line at a fixed height so every panel
 * header across the dashboard aligns to the same baseline — that alignment is
 * what makes a dense grid look deliberate rather than assembled.
 */
export default function Card({ title, hint, action, children, className = '', bodyClassName = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header
          className="flex items-center justify-between gap-3 px-[var(--card-pad)]"
          style={{ minHeight: 42, borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="min-w-0">
            {title && <h3 className="panel-title truncate">{title}</h3>}
            {hint && <p className="panel-hint truncate">{hint}</p>}
          </div>
          {action && <div className="shrink-0 flex items-center gap-2">{action}</div>}
        </header>
      )}
      <div className={`card-pad ${bodyClassName}`}>{children}</div>
    </section>
  )
}
