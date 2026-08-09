import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import SummaryStats from '../components/dashboard/SummaryStats'

/**
 * Mobile-layout contract tests (375px / iPhone SE class devices).
 *
 * jsdom can't measure pixels, so these don't assert "nothing overflows" —
 * they assert the specific structural decisions that stop it from
 * overflowing, so a future edit can't quietly undo them. The visual result
 * still needs a real browser; what's pinned here is the intent.
 */

const css = readFileSync(resolve(__dirname, '../index.css'), 'utf8')
const appSource = readFileSync(resolve(__dirname, '../App.jsx'), 'utf8')
const dashboardSource = readFileSync(resolve(__dirname, '../pages/Dashboard.jsx'), 'utf8')

describe('horizontal overflow guard (index.css)', () => {
  it('clips horizontal overflow on body so one wide child cannot shift the page', () => {
    // The symptom this prevents: a single overflowing element makes the whole
    // document pannable sideways, which looks like the layout sitting
    // off-centre to the left with the header dragged along.
    expect(css).toMatch(/body\s*\{[^}]*overflow-x:\s*clip/s)
  })

  it('uses clip rather than hidden, which would break the sticky header', () => {
    // `overflow: hidden` on body makes body a scroll container, which
    // silently demotes `position: sticky` on the app header to static.
    expect(css).not.toMatch(/body\s*\{[^}]*overflow-x:\s*hidden/s)
  })

  it('still gives wide content its own opt-in scroller', () => {
    // The guard is a safety net, not a replacement for real scrollers —
    // tables and segmented controls must scroll rather than be clipped.
    expect(css).toMatch(/\.scroll-x\s*\{[^}]*overflow-x:\s*auto/s)
    expect(css).toMatch(/\.seg\s*\{[^}]*overflow-x:\s*auto/s)
  })
})

describe('header at phone widths (App.jsx)', () => {
  it('hides the SENOVA wordmark below sm but keeps the logo tile', () => {
    // The wordmark is the redundant brand cue (the logo image is right next
    // to it) and was ~72px of the header overflow at 375px.
    expect(appSource).toMatch(/hidden sm:block[^>]*>\s*SENOVA/)
    expect(appSource).toContain('alt="SENOVA"')
  })

  it('hides the density toggle below sm', () => {
    // Density is a comfort preference for dense desktop tables; the least
    // essential of the header controls on a phone.
    expect(appSource).toMatch(/hidden sm:inline-flex[\s\S]{0,80}<DensityToggle\s*\/>/)
  })

  it('keeps the theme toggle and account button at every width', () => {
    // Neither is inside a `hidden` wrapper — both must survive to mobile.
    expect(appSource).toMatch(/shrink-0">\s*<ThemeToggle\s*\/>/)
    expect(appSource).toContain('aria-label="Account menu"')
  })

  it('lets the header row compress instead of overflowing', () => {
    // min-w-0 is what allows a flex child to shrink below its content width;
    // without it the row grows past the viewport instead of truncating.
    expect(appSource).toMatch(/flex items-center gap-2\.5 min-w-0 shrink/)
    expect(appSource).toMatch(/nav className="seg min-w-0"/)
  })
})

describe('dashboard toolbar at phone widths (Dashboard.jsx)', () => {
  it('gives the date presets their own full-width scrollable row', () => {
    // Sharing one wrapping flex row with the title and export button is what
    // turned this into several stacked rows on a phone.
    expect(dashboardSource).toMatch(
      /className="seg w-full sm:w-auto min-w-0"[\s\S]{0,120}Filter analytics by date range/,
    )
  })

  it('shows Export PDF as icon-only below sm without dropping its label', () => {
    // The visible text collapses, but an accessible name must remain.
    expect(dashboardSource).toMatch(/hidden sm:inline">\{exporting \? 'Generating…' : 'Export PDF'\}/)
    expect(dashboardSource).toMatch(/sr-only sm:hidden">\{exporting \? 'Generating PDF' : 'Export PDF'\}/)
  })

  it('lets the view tablist scroll rather than push the layout wide', () => {
    expect(dashboardSource).toMatch(/className="seg w-full sm:w-auto min-w-0" role="tablist"/)
  })
})

describe('SummaryStats grid on a 2-column phone layout', () => {
  const summary = {
    revenue: { value: 1840000, trend_percentage: 12.4 },
    profit: { value: 880000, trend_percentage: -3.2 },
    cost: { value: 960000, trend_percentage: 5 },
    units_sold: { value: 4200, trend_percentage: 0 },
    unique_items_sold: { value: 84, trend_percentage: 0 },
  }

  it('spans the odd last tile across both columns so no cell is stranded', () => {
    const { container } = render(<SummaryStats summary={summary} />)
    const tiles = container.querySelectorAll('.stat-tile')

    expect(tiles).toHaveLength(5)
    // Five tiles in a 2-column grid would leave the fifth alone in a
    // half-width cell; it spans the full row on mobile and reverts at sm.
    expect(tiles[4].className).toContain('col-span-2')
    expect(tiles[4].className).toContain('sm:col-span-1')
    // The first four must NOT span, or the grid collapses to one column.
    for (const tile of Array.from(tiles).slice(0, 4)) {
      expect(tile.className).not.toContain('col-span-2')
    }
  })

  it('keeps .stat-tile as the tile hook regardless of the span modifier', () => {
    const { container } = render(<SummaryStats summary={summary} />)
    // Guards the selector the other layout tests rely on.
    for (const tile of container.querySelectorAll('.stat-tile')) {
      expect(tile.className.startsWith('stat-tile')).toBe(true)
    }
  })
})
