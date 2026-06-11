import { useState, useMemo } from 'react'

const MAX_VISIBLE = 10

export default function RowErrorsBanner({ errors }) {
  const [expanded, setExpanded] = useState(false)

  if (!errors || errors.length === 0) return null

  const total = errors.length
  const sliced = useMemo(() => errors.slice(0, MAX_VISIBLE), [errors])
  const remainder = total - MAX_VISIBLE

  const grouped = useMemo(() => {
    const map = {}
    for (const e of sliced) {
      const key = e.column
      if (!map[key]) map[key] = []
      map[key].push(e)
    }
    return map
  }, [sliced])

  return (
    <div className="card-gradient rounded-xl border border-amber-500/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 text-left hover:bg-amber-400/5 transition-colors min-h-[52px]"
      >
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-amber-300 text-sm font-semibold">
              {total} row{total > 1 ? 's' : ''} with validation {total > 1 ? 'errors' : 'error'}
            </p>
            <p className="text-slate-500 text-xs mt-0.5">
              Partial success &mdash; showing analytics computed from valid rows only.
            </p>
          </div>
        </div>
        <svg className={`w-4 h-4 text-slate-500 shrink-0 ${expanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-4 sm:px-5 pb-4 border-t border-amber-500/20">
          {Object.entries(grouped).map(([column, colErrors]) => (
            <div key={column} className="mt-3">
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{column}</h4>
              <div className="space-y-1">
                {colErrors.map((err, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-slate-600 font-mono text-xs mt-0.5 shrink-0 w-8">R{err.row}</span>
                    <span className="text-slate-300">{err.error}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {remainder > 0 && (
            <p className="mt-3 text-xs text-slate-500 italic">
              ... and {remainder} more formatting error{remainder > 1 ? 's' : ''}.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
