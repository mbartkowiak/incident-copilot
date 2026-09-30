import { useState } from 'react'
import { GROUPS, postJson } from '../api'
import type { LiveTicket } from '../api'
import { formatPercent } from '../format'
import { formatDateTime } from '../incidents'
import { useApi } from '../useApi'

// New tickets the routing model wasn't confident enough to assign on its own.
export function ReviewQueue() {
  const [version, setVersion] = useState(0)
  const queue = useApi<LiveTicket[]>(`/api/tickets?view=review&v=${version}`)
  const items = queue.data ?? []

  return (
    <div className="card" data-stale={queue.loading && !!queue.data}>
      <div className="card-head">
        <div>
          <h2>Review queue</h2>
          <p className="subtle">
            New tickets from the virtual agent that the routing model couldn't assign on its own (below 85%
            confidence).
          </p>
        </div>
        <button type="button" className="ghost" onClick={() => setVersion((v) => v + 1)}>
          Refresh
        </button>
      </div>
      {queue.error && <p className="subtle">Couldn't load the queue: {queue.error}</p>}
      {queue.data && items.length === 0 && (
        <p className="empty">Nothing to review. Report an issue on the Get help tab to create one.</p>
      )}
      <ul className="review-list">
        {items.map((t) => (
          <ReviewItem key={t.number} ticket={t} onDone={() => setVersion((v) => v + 1)} />
        ))}
      </ul>
    </div>
  )
}

function ReviewItem({ ticket, onDone }: { ticket: LiveTicket; onDone: () => void }) {
  const [group, setGroup] = useState(ticket.suggested_group ?? GROUPS[0])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  async function assign() {
    setSaving(true)
    setError(undefined)
    try {
      await postJson(`/api/tickets/${ticket.number}/assign`, { group })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <li>
      <div className="precedent-head">
        <span>
          <a href={`#/incidents/${ticket.number}`}>{ticket.number}</a> · <strong>{ticket.short_description}</strong>
        </span>
        <span className="badge">{ticket.priority_label}</span>
      </div>
      <div className="subtle">
        {ticket.caller}, {ticket.location} · {formatDateTime(ticket.opened_at)} · model suggests{' '}
        {ticket.suggested_group} ({formatPercent(ticket.triage_confidence ?? 0, 0)})
      </div>
      <div className="assign-row">
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label={`Team for ${ticket.number}`}>
          {GROUPS.map((g) => (
            <option key={g}>{g}</option>
          ))}
        </select>
        <button type="button" className="primary" disabled={saving} onClick={() => void assign()}>
          {group === ticket.suggested_group ? 'Accept suggestion' : 'Assign'}
        </button>
      </div>
      {error && <p className="subtle">{error}</p>}
    </li>
  )
}
