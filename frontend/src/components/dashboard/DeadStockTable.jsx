import Card from '../common/Card'
import Icon from '../common/Icon'
import { formatNumber } from '../charts/chartFormat'

/**
 * Slow-moving / dead stock list.
 *
 * Status is a word plus an icon, never a coloured dot on its own — the earlier
 * emoji traffic lights broke the "no emoji as icons" rule and rendered
 * differently on every platform.
 */

function Status({ days }) {
  const tone =
    days > 30
      ? { label: 'Critical', colour: 'var(--accent-red)', icon: 'alert' }
      : days > 14
        ? { label: 'Warning', colour: 'var(--accent-amber)', icon: 'info' }
        : { label: 'Recent', colour: 'var(--accent-green)', icon: 'check' }

  return (
    <span
      className="inline-flex items-center gap-1 text-[12px] font-semibold rounded-full px-2"
      style={{ height: 22, color: tone.colour, background: `${tone.colour}14` }}
    >
      <Icon name={tone.icon} className="w-3 h-3" strokeWidth={2.2} />
      {tone.label}
    </span>
  )
}

export default function DeadStockTable({ items }) {
  if (!items || items.length === 0) return null

  return (
    <Card title="Dead stock / slow movers" hint={`${items.length} item(s) flagged`}>
      {/* Capped height + sticky header: a long list scrolls inside the card
          instead of pushing the rest of the page down. */}
      <div className="scroll-x" style={{ maxHeight: 'var(--chart-h)', overflowY: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Units sold</th>
              <th scope="col">Idle days</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name}>
                <th scope="row" title={item.name}>
                  {item.name}
                </th>
                <td className="font-mono">{formatNumber(item.total_quantity)}</td>
                <td className="font-mono">{formatNumber(item.days_since_last_sale)}</td>
                <td>
                  <Status days={item.days_since_last_sale} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
