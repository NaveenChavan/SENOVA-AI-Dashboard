/**
 * Inline loading state. Deliberately small and centred in the space it
 * occupies — a full-height spinner in a dense dashboard just pushes the
 * content the user is waiting for further down the page.
 */
export default function Loader({ message = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10" role="status" aria-live="polite">
      <svg
        className="animate-spin h-4 w-4"
        style={{ color: 'var(--accent-blue)' }}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        {message}
      </span>
    </div>
  )
}
