export default function Card({ title, children, className = '' }) {
  return (
    <div className={`card-gradient rounded-xl p-6 ${className}`}>
      {title && <h3 className="text-lg font-semibold text-slate-100 mb-4">{title}</h3>}
      {children}
    </div>
  )
}
