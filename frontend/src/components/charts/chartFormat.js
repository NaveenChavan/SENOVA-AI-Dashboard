/**
 * Shared number/label formatting for every chart and table.
 *
 * All of it is Indian-retail specific on purpose: amounts read as ₹1,24,500
 * (not ₹124,500), big figures collapse to L/Cr rather than K/M, and axis
 * labels stay short enough that a 375px phone doesn't clip them.
 *
 * Formatting lives here rather than in the API so the server sends raw
 * numbers — the same payload can then be re-rendered as currency, a
 * percentage or a plain count when the user switches measure.
 */

/** Compact currency for axis ticks: ₹1.2L, ₹3.4Cr, ₹950. */
export function formatCurrencyCompact(value) {
  const amount = Number(value) || 0
  const sign = amount < 0 ? '-' : ''
  const absolute = Math.abs(amount)
  if (absolute >= 1e7) return `${sign}₹${(absolute / 1e7).toFixed(1)}Cr`
  if (absolute >= 1e5) return `${sign}₹${(absolute / 1e5).toFixed(1)}L`
  if (absolute >= 1e3) return `${sign}₹${(absolute / 1e3).toFixed(1)}K`
  return `${sign}₹${Math.round(absolute)}`
}

/**
 * Full currency with Indian digit grouping — ``₹7,20,126``.
 *
 * Whole rupees by default: a KPI tile or an insight card showing
 * "₹21,992.33" reads like a rounding error rather than a figure. Accounting
 * surfaces (the P&L, the ledger, the register) pass ``digits = 2``, where the
 * paise are the point.
 */
export function formatCurrency(value, digits = 0) {
  const amount = Number(value) || 0
  return `₹${amount.toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

/** Currency to the paisa, for accounting tables. */
export function formatCurrencyExact(value) {
  return formatCurrency(value, 2)
}

/** Plain counts (units, transactions) with Indian digit grouping. */
export function formatNumber(value, digits = 0) {
  const amount = Number(value) || 0
  return amount.toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** Percentages, tolerant of the nulls the API sends for undefined ratios. */
export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toFixed(digits)}%`
}

/**
 * Pick the right formatter for a measure using the ``measure_format`` the
 * API declares, so a chart never has to hardcode "this one is money".
 */
export function formatByMeasure(value, measureFormat, { compact = false } = {}) {
  if (value === null || value === undefined) return '—'
  if (measureFormat === 'percent') return formatPercent(value)
  if (measureFormat === 'number') return formatNumber(value)
  return compact ? formatCurrencyCompact(value) : formatCurrency(value)
}

/** Axis-tick formatter factory (Recharts calls it with the raw value). */
export function tickFormatterFor(measureFormat) {
  if (measureFormat === 'percent') return (v) => `${Math.round(Number(v))}%`
  if (measureFormat === 'number') return (v) => formatNumber(v)
  return (v) => formatCurrencyCompact(v)
}

/**
 * Shorten a long category/item name for an axis label while keeping enough
 * to be recognisable. Full text always remains in the tooltip and the table.
 */
export function truncateLabel(label, max = 14) {
  const text = String(label ?? '')
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

/** "2026-07-14" → "14 Jul" for compact time axes. */
export function formatShortDate(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return String(iso)
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
