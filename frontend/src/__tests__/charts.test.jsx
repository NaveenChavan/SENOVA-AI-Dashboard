import { render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import ChartStudio from '../components/charts/ChartStudio'
import ChartDataTable from '../components/charts/ChartDataTable'
import HeatmapGrid from '../components/charts/HeatmapGrid'
import TrendChart from '../components/charts/TrendChart'

/**
 * Smoke tests for the chart engine.
 *
 * A build passing only proves the code parses; these tests prove each of the
 * seven chart types actually *renders* against a realistic API payload. That is
 * what catches the class of bug a bundler can't see — a chart library handing a
 * custom shape its data in a different shape than expected.
 *
 * Recharts' ResponsiveContainer measures the DOM, and jsdom reports every
 * element as 0×0, so it is replaced with a fixed-size div. Without that, the
 * chart internals would never execute and the tests would pass vacuously.
 */
vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts')
  const React = await import('react')
  return {
    ...actual,
    // Recharts charts render nothing unless they receive a positive width and
    // height — normally injected by ResponsiveContainer after measuring the DOM.
    // jsdom reports 0×0, so the child is cloned with explicit dimensions here.
    ResponsiveContainer: ({ children }) => (
      <div style={{ width: 800, height: 400 }}>
        {React.isValidElement(children)
          ? React.cloneElement(children, { width: 800, height: 400 })
          : children}
      </div>
    ),
  }
})

/** A ChartDataResponse shaped exactly like the backend returns. */
function makeChartData(overrides = {}) {
  const points = [
    {
      label: 'Kurta',
      value: 184000,
      revenue: 184000,
      cost: 96000,
      profit: 88000,
      units: 420,
      transactions: 210,
      discount: 3600,
      margin_pct: 47.8,
      avg_price: 438.1,
      share_pct: 52.1,
      cumulative_pct: 52.1,
      is_other: false,
    },
    {
      label: 'Saree',
      value: 121000,
      revenue: 121000,
      cost: 78000,
      profit: 43000,
      units: 96,
      transactions: 48,
      discount: 2100,
      margin_pct: 35.5,
      avg_price: 1260.4,
      share_pct: 34.3,
      cumulative_pct: 86.4,
      is_other: false,
    },
    {
      label: 'Other (7)',
      value: 48000,
      revenue: 48000,
      cost: 30000,
      profit: 18000,
      units: 150,
      transactions: 70,
      discount: 900,
      margin_pct: 37.5,
      avg_price: 320,
      share_pct: 13.6,
      cumulative_pct: 100,
      is_other: true,
    },
  ]

  return {
    dimension: 'category',
    dimension_label: 'Category',
    measure: 'revenue',
    measure_label: 'Revenue',
    measure_format: 'currency',
    points,
    total: 353000,
    group_count: 9,
    pareto_group_count: 2,
    ...overrides,
  }
}

const heatmapData = {
  rows: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  columns: ['W28', 'W29'],
  column_dates: ['2026-07-06', '2026-07-13'],
  cells: [
    { row: 'Mon', column: 'W28', value: 4200, transactions: 12 },
    { row: 'Sat', column: 'W28', value: 9800, transactions: 26 },
    { row: 'Sat', column: 'W29', value: 10400, transactions: 31 },
  ],
  measure: 'revenue',
  measure_label: 'Revenue',
  min_value: 4200,
  max_value: 10400,
}

beforeAll(() => {
  // color-mix() is used by the heatmap ramp; jsdom doesn't parse it, and its
  // CSS error output would otherwise drown the test log.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('ChartStudio', () => {
  const dimensions = [
    { key: 'category', label: 'Category', values: ['Kurta', 'Saree'], truncated: false },
    { key: 'branch', label: 'Branch / Store', values: ['MG Road'], truncated: false },
  ]

  it('renders the controls and the default bar view', () => {
    render(
      <ChartStudio
        chartData={makeChartData()}
        heatmapData={heatmapData}
        loading={false}
        availableDimensions={dimensions}
        onQueryChange={() => {}}
        onDrillDown={() => {}}
      />,
    )

    expect(screen.getByRole('tablist', { name: 'Chart type' })).toBeTruthy()
    // All seven selectable types (bar, ranking, donut, combo, pareto, bubble,
    // treemap) plus the heatmap are offered.
    expect(screen.getAllByRole('tab')).toHaveLength(8)
    expect(screen.getByLabelText('Measure to plot')).toBeTruthy()
    expect(screen.getByLabelText('Dimension to group by')).toBeTruthy()
    // The footer states the concentration fact in words.
    expect(screen.getByText(/top 2 make 80% of it/i)).toBeTruthy()
  })

  it.each([
    ['bar', 'Bars'],
    ['bar-h', 'Ranking'],
    ['donut', 'Donut'],
    ['combo', 'Combo'],
    ['pareto', 'Pareto'],
    ['scatter', 'Bubble'],
    ['treemap', 'Treemap'],
  ])('renders the %s view without crashing', (type, label) => {
    // Preference persistence is how the studio remembers the chart type, so
    // seeding it selects the view under test on first render.
    window.localStorage.setItem(
      'senova.chartStudio.v1',
      JSON.stringify({ chartType: type, measure: 'revenue', dimension: 'category', showTable: false }),
    )

    const { container, unmount } = render(
      <ChartStudio
        chartData={makeChartData()}
        heatmapData={heatmapData}
        loading={false}
        availableDimensions={dimensions}
        onQueryChange={() => {}}
        onDrillDown={() => {}}
      />,
    )

    expect(screen.getByRole('tab', { name: label }).getAttribute('aria-selected')).toBe('true')
    // Something was actually drawn: charts render SVG, the treemap renders rects.
    expect(container.querySelector('svg')).toBeTruthy()
    unmount()
    window.localStorage.clear()
  })

  it('renders the heatmap grid with a numeric legend', () => {
    window.localStorage.setItem(
      'senova.chartStudio.v1',
      JSON.stringify({ chartType: 'heatmap', measure: 'revenue', dimension: 'category', showTable: false }),
    )

    render(
      <ChartStudio
        chartData={makeChartData()}
        heatmapData={heatmapData}
        loading={false}
        availableDimensions={dimensions}
        onQueryChange={() => {}}
        onDrillDown={() => {}}
      />,
    )

    // Weekday rows exist and the legend prints the actual value range, so
    // colour is never the only carrier of meaning.
    expect(screen.getByRole('rowheader', { name: 'Sat' })).toBeTruthy()
    expect(screen.getByText('₹4.2K')).toBeTruthy()
    expect(screen.getByText('₹10.4K')).toBeTruthy()
    window.localStorage.clear()
  })

  it('shows an empty state instead of a broken chart', () => {
    render(
      <ChartStudio
        chartData={{ ...makeChartData(), points: [], total: 0, group_count: 0 }}
        loading={false}
        availableDimensions={dimensions}
        onQueryChange={() => {}}
      />,
    )
    expect(screen.getByText(/nothing to plot/i)).toBeTruthy()
  })
})

describe('ChartDataTable (accessible alternative)', () => {
  it('lists every group with its supporting measures', () => {
    render(<ChartDataTable data={makeChartData()} onSelect={() => {}} />)

    expect(screen.getByRole('rowheader', { name: 'Kurta' })).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Revenue' })).toBeTruthy()
    // Indian digit grouping, not 184,000.
    expect(screen.getByText('₹1,84,000')).toBeTruthy()
    expect(screen.getByText('47.8%')).toBeTruthy()
  })

  it('drills down when a row is clicked', () => {
    const onSelect = vi.fn()
    render(<ChartDataTable data={makeChartData()} onSelect={onSelect} />)

    screen.getByRole('rowheader', { name: 'Saree' }).closest('tr').click()
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ label: 'Saree' }))
  })
})

describe('HeatmapGrid', () => {
  it('explains itself when there is nothing to show', () => {
    render(<HeatmapGrid data={{ ...heatmapData, cells: [] }} />)
    expect(screen.getByText(/not enough dated rows/i)).toBeTruthy()
  })
})

describe('TrendChart', () => {
  const trend = [
    { date: '2026-07-01', revenue: 4200, profit: 1800 },
    { date: '2026-07-02', revenue: 5100, profit: 2100 },
    { date: '2026-07-03', revenue: 900, profit: 200 },
  ]

  it('renders actuals on their own', () => {
    const { container } = render(<TrendChart trend={trend} />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('renders the forecast continuation and confidence band', () => {
    const forecast = {
      available: true,
      horizon_days: 2,
      points: [
        { date: '2026-07-03', forecast: 900, is_future: false },
        { date: '2026-07-04', forecast: 4800, lower: 3200, upper: 6400, is_future: true },
        { date: '2026-07-05', forecast: 4900, lower: 3100, upper: 6700, is_future: true },
      ],
    }

    render(<TrendChart trend={trend} forecast={forecast} anomalyDates={['2026-07-03']} />)

    // The legend names all three series, and the dashed forecast is labelled —
    // pattern plus colour, not colour alone.
    expect(screen.getByText('Revenue')).toBeTruthy()
    expect(screen.getByText('Forecast')).toBeTruthy()
    expect(screen.getByText('Likely range (80%)')).toBeTruthy()
    // The flagged day is marked on the line itself.
    expect(screen.getByLabelText('Unusual revenue on 2026-07-03')).toBeTruthy()
  })

  it('handles an empty period', () => {
    render(<TrendChart trend={[]} />)
    expect(screen.getByText(/no dated transactions/i)).toBeTruthy()
  })
})
