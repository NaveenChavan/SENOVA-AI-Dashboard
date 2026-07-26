import Card from '../common/Card'
import ErrorBoundary from '../common/ErrorBoundary'
import BarChart from '../charts/BarChart'

/**
 * Top fast-moving items, plotted by units sold.
 *
 * Sits in a Card so its header aligns with the dead-stock panel beside it, and
 * uses the tokenised chart height so the two cards in that row are exactly the
 * same height — no ragged bottom edge.
 */
export default function TopItems({ items }) {
  if (!items || items.length === 0) return null

  return (
    <Card title="Top fast-moving items" hint="By units sold in this period">
      <ErrorBoundary>
        <BarChart data={items} dataKey="quantity" valueFormat="number" />
      </ErrorBoundary>
    </Card>
  )
}
