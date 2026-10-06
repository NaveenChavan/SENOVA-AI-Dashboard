import Icon from '../common/Icon'

/**
 * Marks one insight card's wording as AI-written rather than computed.
 *
 * Carries its own caveat, and the caveat is the point. The user is being told
 * "this sentence was reworded by AI, and every figure in it was checked against
 * the real number" — not "this finding came from AI". The finding, its severity
 * and its numbers all come from the same untouched engine either way; only the
 * phrasing is borrowed.
 *
 * Only ever rendered for a rewrite the backend verified, so the marker cannot
 * appear on wording that failed the check.
 */
export default function AiNarrativeNotice() {
  return (
    <span
      className="inline-flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wide px-1 py-px rounded-full align-middle"
      style={{ color: 'var(--accent-blue)', border: '1px solid var(--accent-blue)' }}
    >
      <Icon name="spark" className="w-2.5 h-2.5" />
      AI wording, numbers checked
    </span>
  )
}