import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Card from '../components/common/Card'
import SummaryStats from '../components/dashboard/SummaryStats'
import ChartStudio from '../components/charts/ChartStudio'
import FilterPanel from '../components/dashboard/FilterPanel'

/**
 * Layout / design-system contract tests.
 *
 * The visual complaints these guard against are specific: controls of differing
 * heights on one row, cards taller than the viewport, and charts big enough to
 * need scrolling. jsdom can't measure pixels, but it *can* prove that every
 * component opts into the shared tokens instead of hardcoding its own sizes —
 * which is what keeps the layout aligned and compact at every breakpoint.
 */

vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts')
  const React = await import('react')
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => (
      <div style={{ width: 800, height: 400 }}>
        {React.isValidElement(children) ? React.cloneElement(children, { width: 800, height: 400 }) : children}
      </div>
    ),
  }
})

const css = readFileSync(resolve(__dirname, '../index.css'), 'utf8')

describe('design tokens (index.css)', () => {
  it('defines the sizing tokens every component reads', () => {
    for (const token of ['--control-h', '--card-pad', '--chart-h', '--gap', '--page-max', '--radius']) {
      expect(css).toContain(`${token}:`)
    }
  })

  it('uses a stepped base font size, not a viewport-fluid one', () => {
    // A vw-based clamp scaled every card, control and chart together on
    // desktop, which is what made whole panels overflow the screen.
    expect(css).toMatch(/html\s*\{[^}]*font-size:\s*15px/)
    expect(css).not.toMatch(/font-size:\s*clamp\([^)]*vw/)
  })

  it('scales the canvas and chart height up for 4K and 8K screens', () => {
    expect(css).toContain('@media (min-width: 2560px)')
    expect(css).toContain('@media (min-width: 3840px)')
  })

  it('keeps a 40px control height on touch and tightens it for a mouse', () => {
    expect(css).toMatch(/--control-h:\s*40px/)
    expect(css).toMatch(/@media \(hover: hover\) and \(pointer: fine\)[^}]*\{[^}]*--control-h:\s*36px/s)
  })

  it('raises Tailwind\'s smallest steps so dense text stays readable', () => {
    // text-xs at the default 0.75rem was 11.25px against a 15px root; the
    // override in tailwind.config.js lifts it to a readable 13px.
    const config = readFileSync(resolve(__dirname, '../../tailwind.config.js'), 'utf8')
    expect(config).toMatch(/xs:\s*\['0\.8125rem'/)
    expect(config).toMatch(/base:\s*\['0\.9375rem'/)
  })

  it('still ships the accessibility baseline', () => {
    expect(css).toContain(':focus-visible')
    expect(css).toContain('prefers-reduced-motion')
    expect(css).toContain('.skip-link')
  })
})

describe('Card', () => {
  it('renders a title row and an action slot on one line', () => {
    render(
      <Card title="Daily trend" hint="Solid = actual" action={<button type="button">Toggle</button>}>
        <p>body</p>
      </Card>,
    )

    // Title uses the shared small-caps panel label, so every panel header
    // aligns to the same baseline.
    const title = screen.getByText('Daily trend')
    expect(title.className).toContain('panel-title')
    expect(screen.getByText('Solid = actual').className).toContain('panel-hint')
    expect(screen.getByRole('button', { name: 'Toggle' })).toBeTruthy()
  })

  it('omits the header entirely when there is nothing to put in it', () => {
    const { container } = render(<Card>body</Card>)
    expect(container.querySelector('header')).toBeNull()
  })
})

describe('SummaryStats', () => {
  const summary = {
    revenue: { value: 1840000, trend_percentage: 12.4 },
    profit: { value: 880000, trend_percentage: -3.2 },
    cost: { value: 960000, trend_percentage: 5 },
    units_sold: { value: 4200, trend_percentage: 0 },
    unique_items_sold: { value: 84, trend_percentage: 0 },
  }

  it('renders five tiles showing the complete figure, not an abbreviation', () => {
    const { container } = render(<SummaryStats summary={summary} />)

    expect(container.querySelectorAll('.stat-tile')).toHaveLength(5)
    // The shop owner reads the actual number off the tile: ₹18,40,000 — Indian
    // digit grouping, no ₹18.4L abbreviation, no clipping.
    expect(screen.getByText('₹18,40,000')).toBeTruthy()
    expect(screen.getByText('₹8,80,000')).toBeTruthy()
    expect(screen.getByText('₹9,60,000')).toBeTruthy()
    expect(screen.getByText('4,200')).toBeTruthy()
  })

  it('shows trend as an icon plus the signed percentage, not colour alone', () => {
    render(<SummaryStats summary={summary} />)
    expect(screen.getByTitle('Up 12.4% vs the previous period')).toBeTruthy()
    expect(screen.getByTitle('Down 3.2% vs the previous period')).toBeTruthy()
  })
})

describe('ChartStudio layout', () => {
  const chartData = {
    dimension: 'category',
    dimension_label: 'Category',
    measure: 'revenue',
    measure_label: 'Revenue',
    measure_format: 'currency',
    total: 100,
    group_count: 2,
    pareto_group_count: 1,
    points: [
      {
        label: 'Kurta',
        value: 60,
        revenue: 60,
        cost: 30,
        profit: 30,
        units: 10,
        transactions: 5,
        discount: 0,
        margin_pct: 50,
        avg_price: 6,
        share_pct: 60,
        cumulative_pct: 60,
        is_other: false,
      },
      {
        label: 'Saree',
        value: 40,
        revenue: 40,
        cost: 25,
        profit: 15,
        units: 4,
        transactions: 2,
        discount: 0,
        margin_pct: 37.5,
        avg_price: 10,
        share_pct: 40,
        cumulative_pct: 100,
        is_other: false,
      },
    ],
  }

  it('puts the chart in a tokenised, fixed-height box', () => {
    const { container } = render(
      <ChartStudio chartData={chartData} loading={false} availableDimensions={[]} onQueryChange={() => {}} />,
    )
    // .chart-box === height: var(--chart-h); no per-chart pixel heights.
    expect(container.querySelector('.chart-box')).toBeTruthy()
  })

  it('uses the shared control classes so the toolbar row aligns', () => {
    const { container } = render(
      <ChartStudio chartData={chartData} loading={false} availableDimensions={[]} onQueryChange={() => {}} />,
    )

    expect(container.querySelector('.filter-select')).toBeTruthy()
    expect(container.querySelector('.btn')).toBeTruthy()
    // Chart-type switcher is the same segmented control used by the date
    // presets and the view tabs.
    const tablist = screen.getByRole('tablist', { name: 'Chart type' })
    expect(tablist.className).toContain('seg')
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab.className).toContain('seg__btn')
    }
  })

  it('reserves the chart height while loading instead of collapsing', () => {
    const { container } = render(
      <ChartStudio chartData={null} loading availableDimensions={[]} onQueryChange={() => {}} />,
    )
    const skeleton = container.querySelector('.skeleton')
    expect(skeleton).toBeTruthy()
    expect(skeleton.className).toContain('chart-box')
  })
})

describe('FilterPanel layout', () => {
  it('collapses to a single control row', () => {
    const { container } = render(
      <FilterPanel
        dimensions={[{ key: 'branch', label: 'Branch / Store', values: ['MG Road'], truncated: false }]}
        filters={{ branch: ['MG Road'] }}
        onChange={() => {}}
        dateRange={{ min_date: '2026-01-01', max_date: '2026-03-31', span_days: 90 }}
        customRange={{ start: '', end: '' }}
        onCustomRangeChange={() => {}}
        onClear={() => {}}
      />,
    )

    // Toggle is a shared .btn; the active filter is a shared .chip.
    expect(screen.getByRole('button', { name: /filters/i }).className).toContain('btn')
    expect(container.querySelector('.chip')).toBeTruthy()
    // Nothing expanded means no date inputs in the DOM yet — the row stays one
    // line tall until the user asks for more.
    expect(container.querySelector('input[type="date"]')).toBeNull()
  })
})
