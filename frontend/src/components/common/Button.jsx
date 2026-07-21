const VARIANT_STYLES = {
  primary: {
    background: 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))',
    color: 'var(--text-on-accent)',
    border: '1px solid transparent',
    boxShadow: '0 4px 16px -4px var(--accent-blue-glow)',
  },
  secondary: {
    background: 'var(--bg-input)',
    color: 'var(--text-primary)',
    border: '1px solid var(--border-strong)',
  },
  danger: {
    background: 'var(--accent-red)',
    color: '#ffffff',
    border: '1px solid transparent',
  },
  ghost: {
    background: 'transparent',
    color: 'var(--text-secondary)',
    border: '1px solid transparent',
  },
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
      style={VARIANT_STYLES[variant]}
      className={`px-4 sm:px-5 py-2 rounded-lg font-medium text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 ${className}`}
      onFocus={(e) => (e.currentTarget.style.boxShadow = `0 0 0 3px var(--accent-blue-glow)`)}
      onBlur={(e) => (e.currentTarget.style.boxShadow = VARIANT_STYLES[variant].boxShadow || 'none')}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading…
        </span>
      ) : children}
    </button>
  )
}
