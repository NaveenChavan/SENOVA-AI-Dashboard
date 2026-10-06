import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiConsentModal from '../components/upload/AiConsentModal'
import AiNoticeBanner, { PipelineTimingNote } from '../components/upload/AiNoticeBanner'
import ColumnMappingScreen from '../components/upload/ColumnMappingScreen'
import SchemaOverviewPanel from '../components/dashboard/SchemaOverviewPanel'
import InsightCards from '../components/dashboard/InsightCards'
import { verifiedNarratives, readStoredConsent, writeStoredConsent } from '../store/useSalesStore'

/**
 * Tests for the opt-in AI surface.
 *
 * The theme running through them: the *absence* of AI must be indistinguishable
 * from a normal run. So the assertions are mostly about what a declined or
 * failed tier must NOT leave behind — no extra prompt where nobody can act on
 * it, no silent drop of a column, no unverified number reaching a card.
 *
 * `ColumnMappingScreen` is exercised with both the modern payload and the legacy
 * one, because the legacy `exact|fuzzy|none` string is a live contract: the
 * component has to stay useful against a backend that has never heard of the
 * additive fields.
 */

describe('AiConsentModal', () => {
  const noop = () => {}

  it('states specifically what is sent, so the offer can be judged', () => {
    render(<AiConsentModal open onAccept={noop} onDecline={noop} onClose={noop} />)

    const dialog = screen.getByRole('dialog', { name: /let ai help name your columns/i })
    expect(dialog).toBeTruthy()

    // Sent: headers, aggregate shape, a small masked sample.
    expect(within(dialog).getByText(/column headers/i)).toBeTruthy()
    expect(within(dialog).getByText(/aggregate percentages only, never raw rows/i)).toBeTruthy()
    expect(within(dialog).getByText(/\[email\]/)).toBeTruthy()
    expect(within(dialog).getByText(/\[phone\]/)).toBeTruthy()
    expect(within(dialog).getByText(/9-digit-or-longer/i)).toBeTruthy()

    // Never sent: the three guarantees that make this acceptable at all.
    expect(within(dialog).getByText(/Values from customer or name-like columns/i)).toBeTruthy()
    expect(within(dialog).getByText(/could not identify/i)).toBeTruthy()
    expect(within(dialog).getByText(/Your rows, your totals, or any business figure/i)).toBeTruthy()
  })

  it('offers a refusal that is a real option, not a footnote', () => {
    const onDecline = vi.fn()
    render(<AiConsentModal open onAccept={noop} onDecline={onDecline} onClose={noop} />)

    fireEvent.click(screen.getByRole('button', { name: /not now/i }))
    expect(onDecline).toHaveBeenCalled()

    // And says plainly that declining costs nothing.
    expect(screen.getByText(/Declining costs you nothing/i)).toBeTruthy()
  })

  it('renders nothing when closed, so a settled answer adds no chrome', () => {
    const { container } = render(<AiConsentModal open={false} onAccept={noop} onDecline={noop} onClose={noop} />)
    expect(container.firstChild).toBeNull()
  })
})

describe('AiNoticeBanner', () => {
  it('renders nothing without a notice — the common case is silence', () => {
    const { container } = render(<AiNoticeBanner notice={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('says how many columns now need a human', () => {
    render(<AiNoticeBanner notice={{ message: 'AI matching was unavailable.', tone: 'warning', affected_columns: 3 }} />)

    const banner = screen.getByRole('status')
    expect(within(banner).getByText(/AI matching was unavailable/i)).toBeTruthy()
    expect(within(banner).getByText('3 columns')).toBeTruthy()
    expect(within(banner).getByText(/will need mapping by hand/i)).toBeTruthy()
  })

  it('does not claim columns were dropped when none were', () => {
    render(<AiNoticeBanner notice={{ message: 'AI matching was unavailable.', affected_columns: 0 }} />)
    expect(screen.queryByText(/will need mapping by hand/i)).toBeNull()
  })
})

describe('PipelineTimingNote', () => {
  it('reports the measured local time and admits when AI was not used', () => {
    render(<PipelineTimingNote timings={{ tier1_ms: 241.7, tier2_ms: 0, total_ms: 250 }} aiEnabled />)

    expect(screen.getByText(/Matched on this server in 242ms/)).toBeTruthy()
    expect(screen.getByText(/AI not needed — every column was clear/)).toBeTruthy()
  })

  it('reports the real AI time when the AI stage actually ran', () => {
    const preview = { detected_columns: [{ source: 'gemini' }, { source: 'fallback' }] }
    render(<PipelineTimingNote timings={{ tier1_ms: 90, tier2_ms: 1450 }} aiEnabled preview={preview} />)
    expect(screen.getByText(/AI helped with 1 of 2 unclear columns \(1450ms\)/)).toBeTruthy()
  })

  it('distinguishes "AI off" from "AI not needed" — different facts', () => {
    const { unmount } = render(<PipelineTimingNote timings={{ tier1_ms: 12, tier2_ms: 0 }} aiEnabled={false} />)
    expect(screen.getByText(/AI is switched off on this server/)).toBeTruthy()
    unmount()

    render(<PipelineTimingNote timings={{ tier1_ms: 12, tier2_ms: 0 }} aiEnabled />)
    expect(screen.getByText(/AI not needed/)).toBeTruthy()
  })

  it('renders nothing when the server sent no timings', () => {
    const { container } = render(<PipelineTimingNote timings={null} />)
    expect(container.firstChild).toBeNull()
  })
})

/** The modern payload: every additive field the 2-tier pipeline fills in. */
const MODERN_PREVIEW = {
  file_id: 'f1',
  filename: 'sales.csv',
  row_count: 4,
  required_fields: ['Date', 'Category', 'Item', 'Quantity', 'Selling Price', 'Cost Price'],
  optional_fields: ['Branch'],
  field_help: {},
  sample_rows: [{ 'Item Name (Desc)': 'Cotton Kurta', Rate: '240', MRP: '400' }],
  ai_enabled: true,
  pipeline_timings: { tier1_ms: 88, tier2_ms: 0, pandas_ms: null, total_ms: 95 },
  detected_columns: [
    {
      raw_column: 'Item Name (Desc)',
      suggested_field: 'Item',
      confidence: 'fuzzy',
      confidence_score: 0.62,
      confidence_band: 'medium',
      margin: 0.11,
      source: 'gemini',
      semantic_label: 'product',
      reason: 'Free-text product names look like other items in this file.',
      needs_review: false,
    },
    {
      raw_column: 'Rate',
      suggested_field: 'Selling Price',
      confidence: 'fuzzy',
      confidence_score: 0.41,
      confidence_band: 'low',
      margin: 0.02,
      source: 'fallback',
      semantic_label: 'other',
      reason: 'Could be a cost price or a discount — the values alone cannot say.',
      needs_review: true,
    },
    {
      raw_column: 'MRP',
      suggested_field: null,
      confidence: 'fuzzy',
      confidence_score: 0.9,
      confidence_band: 'high',
      source: 'local',
      semantic_label: 'mrp',
      reason: 'A list price, not a realised selling price, so nothing analyses it.',
      needs_review: false,
    },
  ],
}

describe('ColumnMappingScreen — additive confidence fields', () => {
  it('renders the score, the band and who decided', () => {
    render(<ColumnMappingScreen preview={MODERN_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

    // Band wording, not the raw string, when the band is present.
    expect(screen.getByText('Likely')).toBeTruthy()
    expect(screen.getByText('Check this')).toBeTruthy()
    expect(screen.getByText('Confident')).toBeTruthy()

    expect(screen.getByText('62%')).toBeTruthy()
    expect(screen.getByText('AI')).toBeTruthy()
    expect(screen.getByText('on-device')).toBeTruthy()

    // The sentence the user actually needs in order to judge the guess.
    expect(screen.getByText(/A list price, not a realised selling price/i)).toBeTruthy()
  })

  it('still works against an older backend that sends only the confidence string', () => {
    const legacy = {
      ...MODERN_PREVIEW,
      detected_columns: [
        { raw_column: 'Item', suggested_field: 'Item', confidence: 'exact' },
        { raw_column: 'Qty', suggested_field: 'Quantity', confidence: 'fuzzy' },
        { raw_column: 'Notes', suggested_field: null, confidence: 'none' },
      ],
      sample_rows: [{ Item: 'Cotton Kurta', Qty: 3, Notes: 'gift wrap' }],
    }

    render(<ColumnMappingScreen preview={legacy} onConfirm={() => {}} onCancel={() => {}} />)

    // The original wording, unchanged.
    expect(screen.getByText('Matched')).toBeTruthy()
    expect(screen.getByText('Check this')).toBeTruthy()
    expect(screen.getByText('Not recognised')).toBeTruthy()
    // And nothing invents a score or an author that was not reported.
    expect(screen.queryByText(/\d+%/)).toBeNull()
  })

  it('flags a low-confidence guess even though the select is already pre-filled', () => {
    const { container } = render(
      <ColumnMappingScreen preview={MODERN_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />,
    )

    const rows = Array.from(container.querySelectorAll('tbody tr'))
    const highlighted = rows.filter((row) => row.getAttribute('style'))

    // "Rate" arrives flagged, with a *pre-filled* low-confidence suggestion.
    // That is the row most worth looking at: an unexamined pick at 0.41 is
    // what quietly corrupts every later number, and hiding the highlight
    // because the select happens to be non-empty would defeat the flag.
    expect(highlighted).toHaveLength(1)
    expect(highlighted[0].textContent).toContain('Rate')
  })

  it('stops flagging a row once the user picks the field themselves', () => {
    const { container } = render(
      <ColumnMappingScreen preview={MODERN_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />,
    )

    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    fireEvent.change(rateSelect, { target: { value: 'Cost Price' } })

    const highlighted = Array.from(container.querySelectorAll('tbody tr')).filter((row) =>
      row.getAttribute('style'),
    )
    expect(highlighted).toHaveLength(0)
    // The choice itself is kept.
    expect(rateSelect.value).toBe('Cost Price')
  })
})

describe('SchemaOverviewPanel', () => {
  const schema = {
    kpi_cards: [
      { key: 'revenue', label: 'Revenue', available: true, reason: null, formats: ['currency'] },
      { key: 'profit', label: 'Profit', available: false, reason: 'Map Cost Price to unlock this.' },
      { key: 'days_of_cover', label: 'Days of cover', available: false, reason: 'Map Stock On Hand to unlock this.' },
    ],
    charts: [
      { key: 'daily_trend', label: 'Daily trend', available: true, min_categories: 2 },
      {
        key: 'weekday_heatmap',
        label: 'Weekday pattern',
        available: false,
        distinct_values: 1,
        min_categories: 4,
      },
    ],
    dimensions: [
      { key: 'category', label: 'Category', available: true, column: 'Category' },
      { key: 'branch', label: 'Branch', available: false, reason: 'No branch column in this file.' },
    ],
    measures: [
      { key: 'revenue', label: 'Revenue', available: true, format: 'currency', additive: true },
      { key: 'margin_pct', label: 'Margin %', available: true, format: 'percent', additive: false },
    ],
    mapped_columns: { Item: 'Item' },
    present_columns: ['Date', 'Category', 'Item', 'Quantity', 'Selling Price'],
    missing_required_columns: ['Cost Price'],
    date_range: { min_date: '2026-01-01', max_date: '2026-03-31', span_days: 90 },
  }

  it('separates "not computable" from "zero" in the summary line', () => {
    render(<SchemaOverviewPanel schema={schema} />)

    // This is the whole point of the panel: 1 of 3 computable, not "profit: 0".
    expect(screen.getByText(/1 of 3 headline numbers are computable/i)).toBeTruthy()
    expect(screen.getByText(/still needs Cost Price/i)).toBeTruthy()
    expect(screen.getByText('Revenue')).toBeTruthy()
    expect(screen.getByText('Profit — no')).toBeTruthy()
  })

  it('reveals every unavailable entry with the action that unlocks it', () => {
    render(<SchemaOverviewPanel schema={schema} />)

    fireEvent.click(screen.getByRole('button', { name: /show the detail/i }))

    expect(screen.getByText(/Map Cost Price to unlock this/i)).toBeTruthy()
    expect(screen.getByText(/Map Stock On Hand to unlock this/i)).toBeTruthy()
    expect(screen.getByText(/No branch column in this file/i)).toBeTruthy()
  })

  it('explains a chart that is available but has too few distinct values', () => {
    render(<SchemaOverviewPanel schema={schema} />)
    fireEvent.click(screen.getByRole('button', { name: /show the detail/i }))

    // One bar is not a weekday pattern. Saying "unavailable" with the count is
    // more useful than drawing it, and more honest than hiding the row.
    expect(screen.getByText(/Only 1 distinct value here — needs 4/i)).toBeTruthy()
  })

  it('marks an average measure as not summable', () => {
    render(<SchemaOverviewPanel schema={schema} />)
    fireEvent.click(screen.getByRole('button', { name: /show the detail/i }))
    expect(screen.getByText('average, not sum')).toBeTruthy()
  })

  it('renders nothing when there is no schema yet', () => {
    const { container } = render(<SchemaOverviewPanel schema={null} />)
    expect(container.firstChild).toBeNull()
  })
})

describe('InsightCards — verified AI wording', () => {
  const insights = {
    analysed_days: 90,
    anomaly_dates: [],
    note: null,
    insights: [
      {
        id: 'margin-leak',
        kind: 'margin',
        severity: 'warning',
        title: "'Clearance Kurta' sells well but earns little",
        message: 'It generated ₹1.2L in revenue but only ₹3,000 in profit (2.4% margin).',
        metrics: { revenue: 120000, profit: 3000, margin_pct: 2.4 },
        evidence: ['Clearance Kurta'],
      },
    ],
  }

  it('renders the computed sentence when no AI wording was supplied', () => {
    render(<InsightCards insights={insights} loading={false} />)

    expect(screen.getByText(/It generated/)).toBeTruthy()
    expect(screen.queryByText(/AI wording/)).toBeNull()
  })

  it('swaps in AI wording and says so, with the caveat spelled out', () => {
    render(
      <InsightCards
        insights={insights}
        loading={false}
        aiTextById={{ 'margin-leak': 'Clearance Kurta is a volume seller with almost no margin left in it.' }}
      />,
    )

    expect(screen.getByText(/volume seller with almost no margin/i)).toBeTruthy()
    expect(screen.queryByText(/It generated/)).toBeNull()
    // "numbers checked", not "made by AI" — the figures are still the engine's.
    expect(screen.getByText(/AI wording, numbers checked/i)).toBeTruthy()
  })

  it('keeps the deterministic sentence when the backend sent no verified rewrite', () => {
    render(<InsightCards insights={insights} loading={false} aiTextById={{}} />)
    expect(screen.getByText(/It generated/)).toBeTruthy()
    expect(screen.queryByText(/AI wording/)).toBeNull()
  })
})

describe('verifiedNarratives', () => {
  it('keeps verified rewrites and drops everything else', () => {
    const map = verifiedNarratives([
      { id: 'a', text: 'fine', verified: true },
      { id: 'b', text: 'hallucinated', verified: false, rejected_numbers: ['₹9,99,999'] },
      { id: 'c', text: '', verified: true },
      { id: 'd', text: 'no flag', verified: undefined },
    ])

    expect(map).toEqual({ a: 'fine' })
  })

  it('survives an absent, null or malformed list', () => {
    expect(verifiedNarratives(undefined)).toEqual({})
    expect(verifiedNarratives(null)).toEqual({})
    expect(verifiedNarratives([null, undefined])).toEqual({})
  })

  it('is the only route from a rewrite to the screen, so it must be closed by default', () => {
    // A rewrite that is verified but carries no text is not renderable, and one
    // that is unverified must never survive — the component has no branch that
    // could show it, so the filter is the enforcement point.
    expect(verifiedNarratives([{ id: 'x', text: 't', verified: false }])).toEqual({})
  })
})

describe('consent persistence', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('treats never-asked as unanswered, not as consent', () => {
    expect(readStoredConsent()).toBeNull()
  })

  it('round-trips both answers', () => {
    writeStoredConsent('granted')
    expect(readStoredConsent()).toBe('granted')

    writeStoredConsent('declined')
    expect(readStoredConsent()).toBe('declined')
  })

  it('treats a corrupted or foreign value as unanswered rather than consent', () => {
    window.localStorage.setItem('senova.aiConsent.v1', 'yes please')
    expect(readStoredConsent()).toBeNull()

    window.localStorage.setItem('senova.aiConsent.v1', 'true')
    expect(readStoredConsent()).toBeNull()
  })

  it('clears the answer so the user is asked again', () => {
    writeStoredConsent('granted')
    writeStoredConsent(null)
    expect(readStoredConsent()).toBeNull()
  })
})