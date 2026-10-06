import { motion, AnimatePresence } from 'motion/react'

import Button from '../common/Button'
import Icon from '../common/Icon'

/**
 * First-run consent for the AI half of the column-understanding pipeline.
 *
 * Shown before the upload, because consent travels *on* the upload request —
 * a page that asked afterwards could never grant it on the first try. It lists
 * exactly what is sent, because the offer is only meaningful if it is specific:
 * a shopkeeper who is told "we may use AI" learns nothing, whereas one who is
 * shown "these five masked values per column, never your customer names" can
 * actually decide.
 *
 * The list below is the backend's behaviour described in words, and it is kept
 * honest by `test_ai_assurance.test.jsx`, which asserts every claim made here
 * is still backed by the pipeline that ships it.
 */
export default function AiConsentModal({ open, onAccept, onDecline, onClose }) {
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
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-consent-title"
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
                  style={{ background: 'rgba(59,130,246,0.12)' }}
                >
                  <Icon name="spark" className="w-4 h-4" style={{ color: 'var(--accent-blue)' }} />
                </span>
                <div>
                  <h2 id="ai-consent-title" className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Let AI help name your columns?
                  </h2>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                    Your columns are matched on this server first. AI is only asked when the local match is
                    genuinely ambiguous — it never changes a number, only which field a column means.
                  </p>
                </div>
              </div>

              <Disclosure title="What is sent" tone="sent">
                <ul className="space-y-1.5">
                  <Item>Your column headers, e.g. <code>Item Name (Desc)</code>.</Item>
                  <Item>
                    The shape of each column — how much is numeric, how much parses as a date, how unique the
                    values are. Aggregate percentages only, never raw rows.
                  </Item>
                  <Item>
                    Up to 5 sample values per column, capped at 60 characters, with emails, phone numbers and any
                    9-digit-or-longer run replaced by <code>[email]</code>, <code>[phone]</code> and{' '}
                    <code>[number]</code>.
                  </Item>
                </ul>
              </Disclosure>

              <Disclosure title="What is never sent" tone="never">
                <ul className="space-y-1.5">
                  <Item>Values from customer or name-like columns.</Item>
                  <Item>
                    Values from any column we could not identify — a free-text column could be names, addresses or
                    remarks, so it goes as a header and its shape only.
                  </Item>
                  <Item>
                    Your rows, your totals, or any business figure. On the dashboard, AI rewrites the wording of a
                    finding and every figure it writes is checked against the real number before you see it.
                  </Item>
                </ul>
              </Disclosure>

              <p className="note mt-4" data-tone="info">
                <Icon name="lock" className="w-4 h-4 shrink-0 mt-px" />
                <span>
                  Declining costs you nothing. Uploading, the dashboard and every number work exactly the same —
                  ambiguous columns simply stay on your list to map. You can change this later from the upload
                  screen.
                </span>
              </p>

              <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end mt-4">
                <Button type="button" variant="secondary" onClick={onDecline}>
                  Not now
                </Button>
                <Button type="button" onClick={onAccept}>
                  Use AI to match columns
                </Button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Disclosure({ title, tone, children }) {
  return (
    <div
      className="mb-3"
      style={{
        background: 'var(--bg-input)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius)',
        padding: '10px 12px',
      }}
    >
      <p
        className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 mb-2"
        style={{ color: tone === 'never' ? 'var(--accent-green)' : 'var(--text-secondary)' }}
      >
        <Icon name={tone === 'never' ? 'lock' : 'document'} className="w-3.5 h-3.5" />
        {title}
      </p>
      <ul className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {children}
      </ul>
    </div>
  )
}

function Item({ children }) {
  return (
    <li className="flex items-start gap-1.5">
      <Icon name="check" className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color: 'var(--accent-green)' }} />
      <span>{children}</span>
    </li>
  )
}