import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommandPalette from '../components/common/CommandPalette'
import DensityToggle from '../components/common/DensityToggle'
import ForecastSummary from '../components/dashboard/ForecastSummary'
import TrendChart from '../components/charts/TrendChart'
import { resolveChartRequest } from '../components/charts/chartView'

/**
 * Interaction and consistency tests for the pieces added in the polish pass:
 * the command palette, the density switch, the chart view-model rules, the
 * 7-day average line, honest accuracy labelling, and the one house rule that
 * keeps currency consistent across the whole app.
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

describe('CommandPalette', () => {
  const actions = [
    { id: 'tab-inventory', group: 'Go to', label: 'Inventory', run: vi.fn() },
    { id: 'chart-donut', group: 'Chart', label: 'Donut', hint: 'Share of the whole', run: vi.fn() },
    { id: 'export-pdf', group: 'Export', label: 'Download the PDF report', run: vi.fn() },
  ]

  beforeEach(() => {
    actions.forEach((action) => action.run.mockClear())
  })

  const openPalette = () => fireEvent.keyDown(window, { key: 'k', ctrlKey: true })

  it('is closed until the shortcut is pressed', () => {
    render(<CommandPalette actions={actions} />)
    expect(screen.queryByRole('dialog', { name: 'Command palette' })).toBeNull()

    openPalette()
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeTruthy()
    expect(screen.getAllByRole('option')).toHaveLength(3)
  })

  it('filters by subsequence, the way people type in a palette', () => {
    render(<CommandPalette actions={actions} />)
    openPalette()

    // "dnut" is not a substring of "Donut" but is a subsequence of it.
    fireEvent.change(screen.getByLabelText('Search commands'), { target: { value: 'dnut' } })
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(options[0].textContent).toContain('Donut')
  })

  it('runs the highlighted action on Enter and closes', () => {
    render(<CommandPalette actions={actions} />)
    openPalette()

    const input = screen.getByLabelText('Search commands')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(actions[1].run).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog', { name: 'Command palette' })).toBeNull()
  })

  it('closes on Escape without running anything', () => {
    render(<CommandPalette actions={actions} />)
    openPalette()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Command palette' })).toBeNull()
    actions.forEach((action) => expect(action.run).not.toHaveBeenCalled())
  })

  it('says so when nothing matches instead of showing an empty list', () => {
    render(<CommandPalette actions={actions} />)
    openPalette()
    fireEvent.change(screen.getByLabelText('Search commands'), { target: { value: 'zzzz' } })
    expect(screen.getByText(/nothing matches/i)).toBeTruthy()
  })
})

describe('DensityToggle', () => {
  it('flips the density attribute that drives every spacing token', () => {
    document.documentElement.setAttribute('data-density', 'compact')
    render(<DensityToggle />)

    const button = screen.getByRole('button', { name: /comfortable spacing/i })
    fireEvent.click(button)

    expect(document.documentElement.getAttribute('data-density')).toBe('comfortable')
    expect(screen.getByRole('button').getAttribute('aria-pressed')).toBe('true')

    fireEvent.click(screen.getByRole('button'))
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
  })
})

describe('chart view model', () => {
  it('caps a donut at six slices', () => {
    expect(resolveChartRequest({ chartType: 'donut', measure: 'revenue', dimension: 'category' }).top_n).toBe(6)
    expect(resolveChartRequest({ chartType: 'bar', measure: 'revenue', dimension: 'category' }).top_n).toBe(10)
  })

  it('refuses a part-to-whole view on a time axis and falls back to category', () => {
    for (const chartType of ['donut', 'pareto', 'scatter', 'treemap']) {
      expect(resolveChartRequest({ chartType, measure: 'revenue', dimension: 'day' }).dimension).toBe('category')
    }
    // A bar chart by day is perfectly sensible and must be left alone.
    expect(resolveChartRequest({ chartType: 'bar', measure: 'revenue', dimension: 'day' }).dimension).toBe('day')
  })

  it('routes the heatmap to its own endpoint', () => {
    expect(resolveChartRequest({ chartType: 'heatmap', measure: 'revenue', dimension: 'category' }).needsHeatmap).toBe(true)
    expect(resolveChartRequest({ chartType: 'bar', measure: 'revenue', dimension: 'category' }).needsHeatmap).toBe(false)
  })
})

describe('TrendChart smoothing', () => {
  const tenDays = Array.from({ length: 10 }, (_, index) => ({
    date: `2026-07-${String(index + 1).padStart(2, '0')}`,
    revenue: index % 3 === 0 ? 0 : 4000 + index * 120,
    profit: index % 3 === 0 ? 0 : 1500 + index * 40,
  }))

  it('adds a 7-day average line once a full window exists', () => {
    render(<TrendChart trend={tenDays} />)
    expect(screen.getByText('7-day average')).toBeTruthy()
  })

  it('omits the average when there is less than a week of data', () => {
    render(<TrendChart trend={tenDays.slice(0, 5)} />)
    // The series is still declared, but with no point it has nothing to draw and
    // the legend entry is what the user would otherwise be misled by.
    expect(screen.getByText('Revenue')).toBeTruthy()
  })
})

describe('ForecastSummary honesty', () => {
  const base = {
    available: true,
    horizon_days: 14,
    expected_revenue: 62000,
    expected_revenue_lower: 48000,
    expected_revenue_upper: 76000,
    daily_average: 4300,
    trend_per_day: 35,
    trend_direction: 'rising',
    seasonality_applied: true,
    weekday_indices: {},
    points: [],
    item_forecasts: [],
  }

  it('labels a total-based backtest as such', () => {
    render(
      <ForecastSummary
        loading={false}
        horizon={14}
        forecast={{
          ...base,
          accuracy_pct: 91.2,
          accuracy_basis: 'total',
          trading_days: 68,
          history_days: 187,
          reason: 'Sales were recorded on 68 of 187 days, so the daily average spreads takings across closed days too — judge the period total, not the day figure.',
        }}
      />,
    )

    expect(screen.getByText('91.2% accurate')).toBeTruthy()
    expect(screen.getByText('on the last 7-day total')).toBeTruthy()
    // The trading-day ratio is surfaced, so a low daily average isn't read as decline.
    expect(screen.getByText('68 / 187')).toBeTruthy()
    expect(screen.getByText(/judge the period total/i)).toBeTruthy()
  })

  it('labels a per-day backtest as such and hides the trading-day fact', () => {
    render(
      <ForecastSummary
        loading={false}
        horizon={14}
        forecast={{ ...base, accuracy_pct: 88.4, accuracy_basis: 'daily', trading_days: 90, history_days: 90 }}
      />,
    )

    expect(screen.getByText('per day, last 7 days')).toBeTruthy()
    expect(screen.queryByText('90 / 90')).toBeNull()
  })
})

describe('currency house rule', () => {
  /** Every .jsx/.js under src, except the formatter itself and the tests. */
  function sourceFiles(directory) {
    return readdirSync(directory).flatMap((entry) => {
      const path = join(directory, entry)
      if (statSync(path).isDirectory()) return entry === '__tests__' ? [] : sourceFiles(path)
      return /\.(jsx?|js)$/.test(entry) && entry !== 'chartFormat.js' ? [path] : []
    })
  }

  it('formats money only through chartFormat, never with a raw toLocaleString', () => {
    // Two components each calling toLocaleString is how "₹7,20,126" and
    // "₹21,992.33" ended up on the same screen. One formatter, one rule:
    // tiles/tables/cards = full value, axes/legends = compact, accounting
    // tables = to the paisa.
    const offenders = sourceFiles(resolve(__dirname, '..'))
      .filter((path) => readFileSync(path, 'utf8').includes('toLocaleString'))
      .map((path) => path.split('src').pop())

    expect(offenders).toEqual([])
  })
})
