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

  const REASON_MAP = {
    key_invalid: 'The provided AI API key is invalid or unauthorised.',
    model_unavailable: 'The selected AI model could not be found.',
    fallback_used: 'The primary AI model was unavailable, so a fallback model was used.',
    bad_request: 'The AI service rejected the request.',
    rate_limit: 'The AI service is currently rate limited.',
    timeout: 'The AI service timed out.',
    server_error: 'The AI service is currently unavailable.',
    invalid_json: 'The AI returned an unusable response.',
    number_check: 'AI answer failed the number check; original text kept.',
    no_consent: 'AI was not approved for this upload.',
    disabled: 'AI is switched off on this server.',
    key_missing: 'AI needs an API key configured on this server.'
  }

  const message = (notice.reason_code && REASON_MAP[notice.reason_code]) || notice.message

  return (
    <p className="note" data-tone="info" role="status">
      <Icon name="info" className="w-4 h-4 shrink-0 mt-px" style={{ color: 'var(--accent-blue)' }} />
      <span>
        {message}
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
export function getPipelineAiMessage({ timings, aiEnabled, preview }) {
  const ms = (value) => `${Math.round(Number(value) || 0)}ms`
  const tier2Ran = (timings?.tier2_ms ?? 0) > 0
  const reviewCount = (preview?.detected_columns ?? []).filter(
    (column) => column?.needs_review && !column?.recognised_unused,
  ).length

  if (tier2Ran) {
    if (preview?.detected_columns) {
      const unclearCount = preview.detected_columns.filter((c) => c.source !== 'local').length
      const aiCount = preview.detected_columns.filter((c) => c.source === 'gemini').length
      return `AI helped with ${aiCount} of ${unclearCount} unclear columns (${ms(timings.tier2_ms)})`
    }
    return `AI disambiguated ${ms(timings.tier2_ms)} of the unclear columns`
  }

  if (!aiEnabled && !preview) {
    return 'AI is switched off on this server'
  }

  if (reviewCount === 0) return 'AI not needed — every column was clear'
  if (!aiEnabled) {
    return `${reviewCount} column${reviewCount === 1 ? '' : 's'} ${reviewCount === 1 ? 'needs' : 'need'} your help. AI help is off.`
  }
  return `${reviewCount} column${reviewCount === 1 ? '' : 's'} ${reviewCount === 1 ? 'needs' : 'need'} your help. AI help was not approved.`
}

export function PipelineTimingNote({ timings, aiEnabled, preview }) {
  if (!timings) return null

  const ms = (value) => `${Math.round(Number(value) || 0)}ms`
  const aiMessage = getPipelineAiMessage({ timings, aiEnabled, preview })

  return (
    <p className="panel-hint flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <span>Matched on this server in {ms(timings.tier1_ms)}</span>
      <span aria-hidden="true">·</span>
      <span>{aiMessage}</span>
    </p>
  )
}