import type { Delta } from '../delta'

type Props = {
  label: string
  value: string
  delta?: Delta
  note?: string
}

export function StatTile({ label, value, delta, note }: Props) {
  return (
    <div className="card tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {delta && (
        <div className="tile-delta" data-good={delta.direction === 'flat' ? undefined : delta.good}>
          <span aria-hidden="true">
            {delta.direction === 'up' ? '▲' : delta.direction === 'down' ? '▼' : '■'}
          </span>{' '}
          {delta.text}
        </div>
      )}
      {note && <div className="tile-note">{note}</div>}
    </div>
  )
}
