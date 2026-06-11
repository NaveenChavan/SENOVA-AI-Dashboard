export default function Card({ title, children, className = '' }) {
  return (
    <div className={`card p-6 ${className}`}>
      {title && (
        <h3 className="text-sm font-semibold uppercase tracking-wider mb-5"
          style={{color: 'var(--text-secondary)'}}>
          {title}
        </h3>
      )}
      {children}
    </div>
  )
}
