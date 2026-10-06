import Icon from '../common/Icon'

/**
 * Says what the AI half of the pipeline could not do, so a partially-matched
 * file is never mistaken for a fully-confident one.
 *
 * The reason this is a banner and not a toast is that the failure is *silent by
 * design* — a declined or unavailable AI tier still returns a complete, working
 * mapping. Without a word about it, a column silently sitting unmapped looks
 * like a column we confidently decided was meaningless. It also renders nothing
 * at all when there is no notice, because "everything worked" needs no chrome.
 */
export default function AiNoticeBanner({ notice }) {
  if (!notice?.message) return null

  const affected = notice.affected_columns ?? 0

  return (
    <p className="note" data-tone="info" role="status">
      <Icon name="info" className="w-4 h-4 shrink-0 mt-px" style={{ color: 'var(--accent-blue)' }} />
      <span>
        {notice.message}
        {affected > 0 && (
          <>
            {' '}
            <strong style={{ color: 'var(--text-primary)' }}>
              {affected} column{affected === 1 ? '' : 's'}
            </strong>{' '}
            will need mapping by hand below.
          </>
        )}
      </span>
    </p>
  )
}

/**
 * The measured cost of the pipeline that just ran, in the server's own numbers.
 *
 * Rendering the real stage timings — including a zero for the AI stage when it
 * was skipped — is the honest alternative to a progress animation that implies
 * work is happening. A user can see that their file was classified locally in
 * under a second and that nothing was sent anywhere.
 */
export function PipelineTimingNote({ timings, aiEnabled, preview }) {
  if (!timings) return null

  const ms = (value) => `${Math.round(Number(value) || 0)}ms`
  const tier2Ran = (timings.tier2_ms ?? 0) > 0

  let aiMessage = 'AI not needed — every column was clear'
  if (tier2Ran) {
    if (preview?.detected_columns) {
      const unclearCount = preview.detected_columns.filter((c) => c.source !== 'local').length
      const aiCount = preview.detected_columns.filter((c) => c.source === 'gemini').length
      aiMessage = `AI helped with ${aiCount} of ${unclearCount} unclear columns (${ms(timings.tier2_ms)})`
    } else {
      aiMessage = `AI disambiguated ${ms(timings.tier2_ms)} of the unclear columns`
    }
  } else if (!aiEnabled) {
    aiMessage = 'AI is switched off on this server'
  }

  return (
    <p className="panel-hint flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <span>Matched on this server in {ms(timings.tier1_ms)}</span>
      <span aria-hidden="true">·</span>
      <span>{aiMessage}</span>
    </p>
  )
}