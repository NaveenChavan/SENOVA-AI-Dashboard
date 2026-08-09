import { useState } from 'react'
import Icon from './Icon'
import { checkPasswordStrength } from '../../utils/authValidation'

/**
 * Password input with a show/hide toggle and an optional live strength
 * checklist. Used on signup and password-reset forms; login forms pass
 * `showStrength={false}` since re-checking rules on an existing password
 * serves no purpose.
 */
export default function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete = 'new-password',
  showStrength = false,
  placeholder = '••••••••',
}) {
  const [visible, setVisible] = useState(false)
  const { valid, reasons } = checkPasswordStrength(value)

  return (
    <div>
      <label htmlFor={id} className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          placeholder={placeholder}
          className="field-input pr-10"
          required
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded-md"
          style={{ color: 'var(--text-muted)' }}
          aria-label={visible ? 'Hide password' : 'Show password'}
        >
          <Icon name={visible ? 'eyeOff' : 'eye'} className="w-4 h-4" />
        </button>
      </div>

      {showStrength && value.length > 0 && (
        <ul className="mt-2 space-y-1" aria-live="polite">
          {reasons.length === 0 ? (
            <li className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--accent-green, #16a34a)' }}>
              <Icon name="check" className="w-3.5 h-3.5" />
              Password meets all requirements
            </li>
          ) : (
            reasons.map((reason) => (
              <li key={reason} className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--text-muted)' }} />
                {reason}
              </li>
            ))
          )}
        </ul>
      )}
      {/* Exposed for callers that need the current validity without re-computing it */}
      <span className="sr-only" data-password-valid={valid} />
    </div>
  )
}
