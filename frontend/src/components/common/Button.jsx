/**
 * Button primitive.
 *
 * Every variant resolves to the shared `.btn` / `.btn-primary` classes in
 * index.css, so its height matches every select, chip and segmented control on
 * the same toolbar row — one control height is what makes a dense toolbar look
 * aligned rather than assembled.
 */

const VARIANT_CLASS = {
  primary: 'btn-primary',
  secondary: 'btn',
  ghost: 'btn',
  danger: 'btn',
}

const VARIANT_STYLE = {
  // Only the variants that need a colour override carry inline style; the rest
  // inherit the token defaults.
  danger: { background: 'var(--accent-red)', borderColor: 'transparent', color: '#ffffff' },
  ghost: { background: 'transparent', borderColor: 'transparent' },
}

export default function Button({
  children,
  onClick,
  variant = 'primary',
  disabled = false,
  loading = false,
  type = 'button',
  className = '',
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${VARIANT_CLASS[variant] ?? 'btn'} ${className}`}
      style={VARIANT_STYLE[variant]}
    >
      {loading ? (
        <>
          <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading…
        </>
      ) : (
        children
      )}
    </button>
  )
}
