import Card from '../common/Card'
import ErrorBoundary from '../common/ErrorBoundary'
import BarChart from '../charts/BarChart'

export default function TopItems({ items }) {
  if (!items || items.length === 0) return null

  return (
    <Card title="Top 5 Fast-Moving Items">
      <ErrorBoundary>
        <BarChart data={items} dataKey="quantity" />
      </ErrorBoundary>
    </Card>
  )
}
