export default function Card({ title, children, className = '' }) {
  return (
    <div className={`card p-4 sm:p-6 ${className}`}>
      {title && (
        <h3
          className="text-xs sm:text-sm font-semibold uppercase tracking-wider mb-4 sm:mb-5"
          style={{ color: 'var(--text-secondary)' }}
        >
          {title}
        </h3>
      )}
      {children}
    </div>
  )
}
