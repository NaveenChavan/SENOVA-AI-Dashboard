export default function Loader({ message = 'Processing analytics…' }) {
  return (
    <div className="flex items-center justify-center py-16 sm:py-24">
      <div className="flex flex-col items-center gap-4">
        <div className="relative">
          <div
            className="absolute inset-0 rounded-full blur-xl"
            style={{ background: 'var(--accent-blue-glow)' }}
          />
          <svg
            className="relative animate-spin h-9 w-9 sm:h-10 sm:w-10"
            style={{ color: 'var(--accent-blue)' }}
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
        <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{message}</span>
      </div>
    </div>
  )
}
