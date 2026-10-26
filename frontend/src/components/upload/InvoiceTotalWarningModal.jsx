import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'motion/react'

import Button from '../common/Button'
import Icon from '../common/Icon'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

function getFocusableElements(container) {
  if (!container) return []
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter((el) => {
    if (el.disabled || el.getAttribute('aria-hidden') === 'true') return false
    return true
  })
}

/**
 * Module 2.4 — non-blocking invoice-total advisory.
 *
 * Shown when the server answers confirm-mapping with HTTP 409
 * (``requires_acknowledgement``): a column the user mapped to Line Total looks
 * like it might be a repeated invoice-level total, which would inflate revenue
 * if summed per line. The user either goes back to fix the mapping, or
 * explicitly acknowledges and proceeds (which retries with
 * ``acknowledge_warnings: true``).
 *
 * A strong-evidence HTTP 400 rejection never reaches this dialog — it is a hard
 * blocking error shown via the page's error banner and cannot be acknowledged.
 *
 * Accessibility (Module 2.4 polish):
 * - Escape dismisses the advisory, equivalent to "Go back and change mapping".
 *   It never acknowledges or submits the mapping.
 * - Focus moves into the dialog on open, Tab / Shift+Tab are trapped inside it,
 *   and focus is restored to the triggering element when it closes.
 * - While an acknowledgement request is in flight (``submitting``), Escape and
 *   backdrop dismissal are suppressed so they cannot interrupt the request or
 *   defeat the existing duplicate-submission protection.
 * - Dismissing never touches mapping or file state; it only calls ``onGoBack``.
 */
export default function InvoiceTotalWarningModal({ open, warnings = [], onGoBack, onAcknowledge, submitting = false }) {
  const dialogRef = useRef(null)
  const previouslyFocusedRef = useRef(null)

  // Keep the latest callback / submitting flag in refs so the keydown handler
  // always reads current values without re-registering the listener (which
  // would otherwise re-run focus-move logic on every submitting change).
  const onGoBackRef = useRef(onGoBack)
  onGoBackRef.current = onGoBack
  const submittingRef = useRef(submitting)
  submittingRef.current = submitting

  // Focus trap, focus containment, and focus restoration.
  useEffect(() => {
    if (!open) return

    // Remember the element that had focus before the dialog opened.
    previouslyFocusedRef.current = document.activeElement

    // Move initial focus inside the dialog to its first focusable element.
    const dialogEl = dialogRef.current
    if (dialogEl) {
      const focusables = getFocusableElements(dialogEl)
      if (focusables.length > 0) {
        focusables[0].focus()
      } else {
        dialogEl.focus()
      }
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        // Submission safety: never let Escape interrupt an in-flight
        // acknowledgement. When idle, Escape is equivalent to "Go back".
        if (submittingRef.current) {
          e.preventDefault()
          return
        }
        e.preventDefault()
        onGoBackRef.current?.()
        return
      }

      if (e.key === 'Tab') {
        const el = dialogRef.current
        if (!el) return

        const focusables = getFocusableElements(el)
        if (focusables.length === 0) {
          e.preventDefault()
          el.focus()
          return
        }

        const firstElement = focusables[0]
        const lastElement = focusables[focusables.length - 1]
        const isInsideFocusables = focusables.includes(document.activeElement)

        if (!isInsideFocusables) {
          e.preventDefault()
          if (e.shiftKey) {
            lastElement.focus()
          } else {
            firstElement.focus()
          }
          return
        }

        if (e.shiftKey) {
          // Shift+Tab on the first focusable wraps to the last.
          if (document.activeElement === firstElement) {
            e.preventDefault()
            lastElement.focus()
          }
        } else {
          // Tab on the last focusable wraps to the first.
          if (document.activeElement === lastElement) {
            e.preventDefault()
            firstElement.focus()
          }
        }
      }
    }

    // Keep focus contained inside the dialog if focus escapes to the document.
    const handleFocusIn = (e) => {
      const el = dialogRef.current
      if (el && !el.contains(e.target)) {
        const focusables = getFocusableElements(el)
        if (focusables.length > 0) {
          focusables[0].focus()
        } else {
          el.focus()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    document.addEventListener('focusin', handleFocusIn)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('focusin', handleFocusIn)

      // When the dialog closes (Escape, Go back, backdrop, or Acknowledge),
      // restore focus to the opener element if it still exists in the DOM.
      const opener = previouslyFocusedRef.current
      if (
        opener &&
        opener !== document.body &&
        typeof opener.focus === 'function' &&
        document.body.contains(opener)
      ) {
        opener.focus()
      }
      previouslyFocusedRef.current = null
    }
  }, [open])

  // Backdrop click dismisses only while idle, matching Escape semantics.
  const handleBackdropClick = submitting ? undefined : onGoBack

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div
            className="absolute inset-0"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={handleBackdropClick}
            aria-hidden="true"
          />
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            tabIndex={-1}
            aria-labelledby="invoice-total-warning-title"
            aria-describedby="invoice-total-warning-desc"
            className="relative w-full rounded-xl overflow-y-auto scroll-x"
            style={{
              maxWidth: 520,
              maxHeight: '88vh',
              background: 'var(--bg-card-solid)',
              border: '1px solid var(--border-subtle)',
              boxShadow: 'var(--shadow-high)',
            }}
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="p-5">
              <div className="flex items-start gap-3 mb-4">
                <span
                  className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center"
                  style={{ background: 'rgba(245,158,11,0.14)' }}
                >
                  <Icon name="alert" className="w-4 h-4" style={{ color: 'var(--accent-amber, #f59e0b)' }} />
                </span>
                <div>
                  <h2
                    id="invoice-total-warning-title"
                    className="text-sm font-semibold"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    This amount might be an invoice total
                  </h2>
                  <p
                    id="invoice-total-warning-desc"
                    className="text-xs mt-1"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    The column you mapped to <strong>Line Total</strong> repeats the same value across the lines of
                    an invoice. If it is a bill-level total rather than a per-line amount, revenue will be counted
                    once for every line and your totals will be inflated.
                  </p>
                </div>
              </div>

              <ul
                className="text-[12.5px] leading-relaxed mb-4 space-y-1.5"
                style={{
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius)',
                  padding: '10px 12px',
                }}
                data-testid="invoice-total-warning-list"
              >
                {warnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <Icon name="alert" className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color: 'var(--accent-amber, #f59e0b)' }} />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>

              <p className="note mb-4" data-tone="info">
                <Icon name="document" className="w-4 h-4 shrink-0 mt-px" />
                <span>
                  If this really is a per-line amount, you can proceed. Otherwise go back and map a genuine per-line
                  amount to Line Total, or map Quantity and Selling Price instead.
                </span>
              </p>

              <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
                <Button type="button" variant="secondary" onClick={onGoBack} disabled={submitting}>
                  Go back and change mapping
                </Button>
                <Button type="button" onClick={onAcknowledge} loading={submitting} disabled={submitting}>
                  Acknowledge and proceed
                </Button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
