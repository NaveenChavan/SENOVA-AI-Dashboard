import { describe, expect, it } from 'vitest'
import { getPipelineAiMessage } from './AiNoticeBanner'
import { shouldStartTier2 } from './ColumnMappingScreen'

const timings = { tier1_ms: 10, tier2_ms: 0, total_ms: 10 }

describe('AI upload messaging', () => {
  it('shows AI not needed only when no row needs review', () => {
    expect(getPipelineAiMessage({
      timings,
      aiEnabled: true,
      preview: { detected_columns: [{ needs_review: false, recognised_unused: false }] },
    })).toBe('AI not needed — every column was clear')
  })

  it('shows an honest message when review is needed and AI is off', () => {
    expect(getPipelineAiMessage({
      timings,
      aiEnabled: false,
      preview: { detected_columns: [{ needs_review: true, recognised_unused: false }] },
    })).toBe('1 column needs your help. AI help is off.')
  })

  it('shows an honest message when review is needed but consent is missing', () => {
    expect(getPipelineAiMessage({
      timings,
      aiEnabled: true,
      preview: { detected_columns: [{ needs_review: true, recognised_unused: false }] },
    })).toBe('1 column needs your help. AI help was not approved.')
  })
})

describe('Tier 2 trigger', () => {
  it('starts Tier 2 when the preview exposes a gemini route', () => {
    expect(shouldStartTier2({
      ai_enabled: true,
      detected_columns: [{ raw_column: 'Price1', route: 'gemini' }],
    }, true)).toBe(true)
  })

  it('does not start Tier 2 when route is absent or consent is false', () => {
    expect(shouldStartTier2({
      ai_enabled: true,
      detected_columns: [{ raw_column: 'Price1' }],
    }, true)).toBe(false)
    expect(shouldStartTier2({
      ai_enabled: true,
      detected_columns: [{ raw_column: 'Price1', route: 'gemini' }],
    }, false)).toBe(false)
  })
})
