import useDensityStore from '../../store/useDensityStore'

/**
 * Density switch — Compact (default) vs Comfortable.
 *
 * A data-dense dashboard should default to showing more, but "more" is a
 * preference, not a truth: on a small laptop the compact scale fits the first
 * screen; on a large display comfortable is easier to read. Only spacing tokens
 * change, so nothing reflows unexpectedly.
 */
export default function DensityToggle() {
  const { density, toggleDensity } = useDensityStore()
  const compact = density === 'compact'

  return (
    <button
      type="button"
      onClick={toggleDensity}
      className="btn-icon"
      aria-pressed={!compact}
      aria-label={compact ? 'Switch to comfortable spacing' : 'Switch to compact spacing'}
      title={compact ? 'Compact rows — switch to comfortable' : 'Comfortable rows — switch to compact'}
    >
      {/* Two distinct glyphs, so the current mode is readable at a glance
          instead of having to be remembered. */}
      <svg
        className="w-4 h-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        aria-hidden="true"
      >
        {compact ? (
          <path d="M4 7h16M4 12h16M4 17h16" />
        ) : (
          <>
            <path d="M4 6h16M4 18h16" opacity="0.4" />
            <path d="M4 12h16" />
          </>
        )}
      </svg>
    </button>
  )
}
