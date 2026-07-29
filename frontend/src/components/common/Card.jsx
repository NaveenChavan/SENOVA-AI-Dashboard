/**
 * Panel surface: a bordered card with an optional title row and an optional
 * right-hand action slot (a select, a toggle, a link).
 *
 * The title and the action sit on one line at a fixed height so every panel
 * header across the dashboard aligns to the same baseline — that alignment is
 * what makes a dense grid look deliberate rather than assembled.
 *
 * `gradient` opts a single card into the hairline gradient-border treatment
 * (`.card-gradient`) — reserved for the one or two panels per screen that
 * should read as "the engine computed this" (e.g. the forecast summary),
 * never the whole grid at once.
 */
export default function Card({ title, hint, action, children, className = '', bodyClassName = '', gradient = false }) {
  return (
    <section className={`${gradient ? 'card-gradient' : 'card'} ${className}`}>
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
