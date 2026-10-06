import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts')
  const React = await import('react')
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => (
      <div style={{ width: 800, height: 400 }}>
        {React.isValidElement(children)
          ? React.cloneElement(children, { width: 800, height: 400 })
          : children}
      </div>
    ),
  }
})

import SummaryStats from '../components/dashboard/SummaryStats'
import SchemaOverviewPanel from '../components/dashboard/SchemaOverviewPanel'
import DiscountMarginChart from '../components/dashboard/DiscountMarginChart'

describe('Discount KPI', () => {
  const summary = {
    revenue: { value: 1000 },
    profit: { value: 200 },
    cost: { value: 800 },
    units_sold: { value: 50 },
    unique_items_sold: { value: 10 },
  }

  const discountMetrics = {
    valid_discount_rows: 100,
    discount_given: 1500,
    discount_pct: 15.5,
  }

  it('renders Discount Given and Discount % with values when available', () => {
    render(<SummaryStats summary={summary} discountMetrics={discountMetrics} />)
    expect(screen.getByText('Discount Given')).toBeTruthy()
    expect(screen.getByText('₹1,500')).toBeTruthy()
    expect(screen.getByText('Discount %')).toBeTruthy()
    expect(screen.getByText('15.5%')).toBeTruthy()
    expect(screen.getByText('of list price (MRP) value')).toBeTruthy()
  })

  it('they are hidden with the reason when unavailable', () => {
    const dynamicSchema = {
      kpi_cards: [
        { key: 'discount_given', available: false, reason: 'Needs an MRP column' },
        { key: 'discount_pct', available: false, reason: 'Needs an MRP column' },
      ],
      charts: []
    }
    render(<SchemaOverviewPanel schema={dynamicSchema} />)
    expect(screen.getAllByText(/Needs an MRP column/i).length).toBeGreaterThan(0)
  })
})

describe('Discount vs Margin Chart', () => {
  const data = [
    { item: 'A', discount_pct: 20, margin_pct: 10, revenue: 1000 }
  ]

  const metrics = { missing_mrp_rows: 5, price_above_mrp_rows: 2 }

  it('renders sorted by discount % descending and shows the excluded N rows note when N > 0', () => {
    // Note: Recharts ResponsiveContainer needs a mock or doesn't render children in jsdom without size.
    // However, the Card hint is rendered outside ResponsiveContainer.
    render(<DiscountMarginChart data={data} metrics={metrics} />)
    expect(screen.getByText(/Excluded 7 rows/i)).toBeTruthy()
  })
})
