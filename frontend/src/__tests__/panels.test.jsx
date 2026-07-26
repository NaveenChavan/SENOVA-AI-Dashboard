import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import DrillDownPanel from '../components/dashboard/DrillDownPanel'
import FilterPanel from '../components/dashboard/FilterPanel'
import ForecastSummary from '../components/dashboard/ForecastSummary'
import InsightCards from '../components/dashboard/InsightCards'
import InventoryPanel from '../components/dashboard/InventoryPanel'

/**
 * Smoke tests for the four Pro feature panels, driven by payloads shaped exactly
 * like the backend's responses.
 *
 * The assertions deliberately target the *honesty* rules as well as rendering:
 * stock figures must be absent when no stock column was mapped, a forecast must
 * show its refusal reason rather than a chart, and severity must be readable as
 * a word — not just a colour.
 */

describe('InsightCards (Feature 1)', () => {
  const insights = {
    analysed_days: 90,
    anomaly_dates: ['2026-03-02'],
    note: null,
    insights: [
      {
        id: 'anomaly-drop-2026-03-02',
        kind: 'anomaly',
        severity: 'critical',
        title: 'Revenue dropped sharply on 2 Mar',
        message: '2 Mar recorded ₹1,240 — 71% below your normal daily level of ₹4,300.',
        action: 'Check whether the shop was closed that day.',
        metrics: { value: 1240, normal_level: 4300, difference: -3060, z_score: -4.1, impact: 3060 },
        evidence: ['2026-03-02'],
      },
      {
        id: 'margin-leak',
        kind: 'margin',
        severity: 'warning',
        title: "'Clearance Kurta' sells well but earns little",
        message: 'It generated ₹1.2L in revenue but only ₹3,000 in profit (2.4% margin).',
        action: 'Re-check its cost price entry.',
        metrics: { revenue: 120000, profit: 3000, margin_pct: 2.4, impact: 120000 },
        evidence: ['Clearance Kurta'],
      },
    ],
  }

  it('renders one card per finding with severity in words', () => {
    render(<InsightCards insights={insights} loading={false} />)

    expect(screen.getByRole('region', { name: 'Automated insights' })).toBeTruthy()
    expect(screen.getByText('Revenue dropped sharply on 2 Mar')).toBeTruthy()
    // Severity as text, so it survives greyscale printing and colour-blindness.
    expect(screen.getByText('Urgent')).toBeTruthy()
    expect(screen.getByText('Watch')).toBeTruthy()
    expect(screen.getByText('90 day(s) analysed')).toBeTruthy()
  })

  it('formats the supporting figures with Indian conventions', () => {
    render(<InsightCards insights={insights} loading={false} />)
    expect(screen.getByText('₹1,240')).toBeTruthy()
    expect(screen.getByText('₹4,300')).toBeTruthy()
    expect(screen.getByText('₹1,20,000')).toBeTruthy()
  })

  it('explains an empty result instead of showing a blank strip', () => {
    render(
      <InsightCards
        insights={{ insights: [], anomaly_dates: [], analysed_days: 3, note: 'Not enough data yet.' }}
        loading={false}
      />,
    )
    expect(screen.getByText(/no findings for this period/i)).toBeTruthy()
    expect(screen.getByText('Not enough data yet.')).toBeTruthy()
  })
})

describe('InventoryPanel (Feature 3)', () => {
  const item = {
    item: 'Cotton Kurta',
    category: 'Kurta',
    units_sold: 420,
    revenue: 184000,
    profit: 88000,
    margin_pct: 47.8,
    velocity_per_day: 4.67,
    velocity_active: 5.2,
    active_days: 81,
    days_since_last_sale: 1,
    trend_factor: 1.32,
    abc_class: 'A',
    ageing_bucket: 'Fresh',
    reorder_priority: 87.5,
    stock_on_hand: 40,
    days_of_cover: 8.6,
    reorder_flag: false,
    capital_locked: 12000,
  }

  const base = {
    window_days: 90,
    items: [item],
    abc_buckets: [
      { label: 'A — top 80% of revenue', item_count: 2, units: 500, revenue: 280000, revenue_share_pct: 79.5, capital_locked: 24000 },
      { label: 'B — next 15%', item_count: 3, units: 120, revenue: 52000, revenue_share_pct: 14.8, capital_locked: 9000 },
      { label: 'C — long tail', item_count: 4, units: 40, revenue: 20000, revenue_share_pct: 5.7, capital_locked: 4000 },
    ],
    ageing_buckets: [
      { label: 'Fresh — sold within 15 days', item_count: 5, units: 600, revenue: 300000, revenue_share_pct: 85 },
      { label: 'Dead — 60+ days idle', item_count: 1, units: 10, revenue: 8000, revenue_share_pct: 2.3 },
    ],
  }

  it('shows real cover and locked capital in stock-aware mode', () => {
    render(
      <InventoryPanel
        inventory={{ ...base, stock_aware: true, reorder_count: 1, total_capital_locked: 37000, note: null }}
        loading={false}
        forecast={{ item_forecasts: [{ item: 'Cotton Kurta', expected_units: 65, velocity_per_day: 4.67, trend_factor: 1.32 }] }}
      />,
    )

    // Tiles use the compact ₹ form so a tile never grows to fit a big number.
    expect(screen.getByText('Capital in stock')).toBeTruthy()
    expect(screen.getByText('₹37.0K')).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Cover' })).toBeTruthy()
    expect(screen.getByText('8.6d')).toBeTruthy()
    // The per-item demand projection from the forecast is joined in.
    expect(screen.getByText('65')).toBeTruthy()
  })

  it('hides stock figures and explains why in demand-only mode', () => {
    const demandOnly = {
      ...base,
      stock_aware: false,
      reorder_count: 0,
      total_capital_locked: null,
      note: 'This file is a sales register only, so days-of-cover and locked capital can\'t be calculated. Map a stock column (Stock / Closing Stock / Balance Qty) on the column screen to unlock real reorder alerts.',
      items: [{ ...item, stock_on_hand: null, days_of_cover: null, capital_locked: null, reorder_flag: false }],
    }

    render(<InventoryPanel inventory={demandOnly} loading={false} />)

    expect(screen.queryByRole('columnheader', { name: 'Cover' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'Stock' })).toBeNull()
    expect(screen.getByText(/map a stock column/i)).toBeTruthy()
    // Demand ranking is still available.
    expect(screen.getByRole('heading', { name: 'Reorder priority' })).toBeTruthy()
    expect(screen.getByRole('rowheader', { name: /Cotton Kurta/ })).toBeTruthy()
  })
})

describe('ForecastSummary (Feature 2)', () => {
  it('leads with the range and shows the backtested accuracy', () => {
    render(
      <ForecastSummary
        loading={false}
        horizon={14}
        onHorizonChange={() => {}}
        forecast={{
          available: true,
          horizon_days: 14,
          expected_revenue: 62000,
          expected_revenue_lower: 48000,
          expected_revenue_upper: 76000,
          daily_average: 4300,
          trend_per_day: 35.2,
          trend_direction: 'rising',
          accuracy_pct: 88.4,
          seasonality_applied: true,
          weekday_indices: { Mon: 0.9, Sat: 1.4 },
          points: [],
          item_forecasts: [],
        }}
      />,
    )

    // Compact headline with the exact figure beneath it, and the range given
    // equal billing.
    expect(screen.getByText('₹62.0K')).toBeTruthy()
    expect(screen.getByText('₹62,000')).toBeTruthy()
    expect(screen.getByText('₹48.0K – ₹76.0K')).toBeTruthy()
    expect(screen.getByText('88.4% accurate')).toBeTruthy()
    expect(screen.getByText('Rising')).toBeTruthy()
    expect(screen.getByRole('group', { name: 'Forecast horizon' })).toBeTruthy()
  })

  it('refuses to draw a forecast when history is too short', () => {
    render(
      <ForecastSummary
        loading={false}
        horizon={14}
        forecast={{
          available: false,
          reason: 'Only 5 day(s) of sales history here. A forecast needs at least 14 days to be meaningful.',
          horizon_days: 14,
          points: [],
        }}
      />,
    )

    expect(screen.getByText(/forecast not available yet/i)).toBeTruthy()
    expect(screen.getByText(/needs at least 14 days/i)).toBeTruthy()
    // No headline number is invented.
    expect(screen.queryByText(/expected revenue/i)).toBeNull()
  })
})

describe('FilterPanel (Feature 5)', () => {
  const dimensions = [
    { key: 'category', label: 'Category', values: ['Kurta', 'Saree'], truncated: false },
    { key: 'branch', label: 'Branch / Store', values: ['MG Road', 'Station Road'], truncated: false },
  ]

  it('shows active filters as removable chips', () => {
    const onChange = vi.fn()
    render(
      <FilterPanel
        dimensions={dimensions}
        filters={{ branch: ['MG Road'] }}
        onChange={onChange}
        dateRange={{ min_date: '2026-01-01', max_date: '2026-03-31', span_days: 90 }}
        customRange={{ start: '', end: '' }}
        onCustomRangeChange={() => {}}
        onClear={() => {}}
      />,
    )

    const chip = screen.getByRole('button', { name: 'Remove Branch / Store filter' })
    expect(chip).toBeTruthy()
    expect(screen.getByText('MG Road')).toBeTruthy()

    chip.click()
    expect(onChange).toHaveBeenCalledWith({})
  })

  it('offers the file\'s own dimensions and a custom date range when opened', () => {
    render(
      <FilterPanel
        dimensions={dimensions}
        filters={{}}
        onChange={() => {}}
        dateRange={{ min_date: '2026-01-01', max_date: '2026-03-31', span_days: 90 }}
        customRange={{ start: '', end: '' }}
        onCustomRangeChange={() => {}}
        onClear={() => {}}
      />,
    )

    // fireEvent (not node.click) so React's state update is flushed inside act.
    fireEvent.click(screen.getByRole('button', { name: /filters/i }))

    expect(screen.getByText('Custom date range')).toBeTruthy()
    expect(screen.getByText('Category')).toBeTruthy()
    expect(screen.getByText('Branch / Store')).toBeTruthy()
    expect(screen.getByText(/data available 2026-01-01/i)).toBeTruthy()
  })
})

describe('DrillDownPanel (Feature 5)', () => {
  const selection = { label: 'Kurta', revenue: 184000, units: 420, transactions: 210, dimension: 'category' }
  const ledger = {
    page: 1,
    page_size: 25,
    total_rows: 210,
    total_pages: 9,
    entries: [
      {
        row: 4,
        date: '2026-02-14',
        category: 'Kurta',
        item: 'Cotton Kurta',
        quantity: 3,
        selling_price: 750,
        cost_price: 300,
        revenue: 2250,
        profit: 1350,
      },
    ],
  }

  it('renders as a dialog with the transactions behind the number', () => {
    render(<DrillDownPanel selection={selection} ledger={ledger} loading={false} onClose={() => {}} onPageChange={() => {}} />)

    const dialog = screen.getByRole('dialog', { name: 'Transactions for Kurta' })
    expect(dialog).toBeTruthy()
    expect(screen.getByText('Cotton Kurta')).toBeTruthy()
    expect(screen.getByText('₹2.3K')).toBeTruthy()
    expect(screen.getByText(/1 \/ 9 · 210 rows/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Close drill-down' })).toBeTruthy()
  })

  it('renders nothing when no group is selected', () => {
    const { container } = render(<DrillDownPanel selection={null} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })
})
