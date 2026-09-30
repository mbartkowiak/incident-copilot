import { useEffect, useState } from 'react'
import { postJson } from '../api'
import type { IncidentDetail, TicketSummaryResponse, TriageSuggestion, WorkNote } from '../api'
import { formatHours, formatPercent } from '../format'
import { ROUTING_TRAIN_CUTOFF, describeSla, formatDateTime, routingVerdict } from '../incidents'
import { useApi } from '../useApi'

export function IncidentPage({ number }: { number: string }) {
  const ticket = useApi<IncidentDetail>(`/api/incidents/${number}`)
  const t = ticket.data?.number === number ? ticket.data : undefined

  return (
    <>
      <a className="back" href="#/incidents">
        ← All incidents
      </a>
      {ticket.error && (
        <div className="banner" role="alert">
          {ticket.error}
        </div>
      )}
      {!t && !ticket.error && <div className="card empty">Loading {number}…</div>}
      {t && <Ticket key={t.number} t={t} />}
    </>
  )
}

function Ticket({ t }: { t: IncidentDetail }) {
  const resolved = t.resolved_at !== null
  return (
    <>
      <header className="card ticket-head">
        <div className="ticket-id">
          <span className="num">{t.number}</span>
          <span className="badge">{t.state}</span>
          <span className="badge" data-tone={t.priority <= 2 ? 'bad' : undefined}>
            {t.priority_label}
          </span>
        </div>
        <h2 className="ticket-title">{t.short_description}</h2>
        <dl className="facts">
          <Fact label="Team" value={t.assignment_group} />
          <Fact label="Assignee" value={t.assigned_to ?? 'Unassigned'} />
          <Fact label="Site" value={t.location} />
          <Fact label="Configuration item" value={t.cmdb_ci} />
          <Fact label="Category" value={`${t.category ?? ''} / ${t.subcategory ?? ''}`} />
          <Fact label="Channel" value={t.contact_type} />
        </dl>
      </header>

      <div className="ticket">
        <div className="ticket-main">
          <SummaryCard number={t.number} resolved={resolved} />
          <div className="card">
            <h2>Description</h2>
            <p className="prose">{t.description || 'No description.'}</p>
          </div>
          <Journal t={t} />
          {t.close_notes && (
            <div className="card">
              <h2>Resolution</h2>
              <p className="subtle">{t.close_code}</p>
              <p className="prose">{t.close_notes}</p>
            </div>
          )}
        </div>
        <aside className="ticket-side">
          <SlaCard t={t} resolved={resolved} />
          <RoutingCard t={t} resolved={resolved} />
        </aside>
      </div>
    </>
  )
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? '—'}</dd>
    </div>
  )
}

type Entry = { at: string; author?: string; text: string; kind: WorkNote['kind'] | 'milestone' }

function Journal({ t }: { t: IncidentDetail }) {
  const entries: Entry[] = [
    { at: t.opened_at, text: `Opened via ${t.contact_type ?? 'unknown channel'}`, kind: 'milestone' },
    ...t.work_notes,
    ...(t.closed_at ? [{ at: t.closed_at, text: 'Closed automatically after 7 days', kind: 'milestone' as const }] : []),
  ]
  return (
    <div className="card">
      <h2>Work notes</h2>
      <ol className="journal">
        {entries.map((e, i) => (
          <li key={i} data-kind={e.kind}>
            <div className="journal-meta">
              <span className="num">{formatDateTime(e.at)}</span>
              {e.author && <span> · {e.author}</span>}
            </div>
            <div className="journal-text">{e.text}</div>
          </li>
        ))}
      </ol>
      {t.work_notes.length === 0 && <p className="empty">No work notes yet.</p>}
    </div>
  )
}

function SlaCard({ t, resolved }: { t: IncidentDetail; resolved: boolean }) {
  const view = describeSla(t.sla, resolved)
  const { risk } = t
  return (
    <div className="card">
      <h2>SLA</h2>
      <div className="sla-label" data-tone={view.tone}>
        {view.label}
      </div>
      <div className="meter" role="img" aria-label={`${formatPercent(view.fraction, 0)} of the SLA target used`}>
        <div
          className="meter-fill"
          data-tone={view.tone}
          style={{ width: `${Math.min(view.fraction, 1) * 100}%` }}
        />
      </div>
      <div className="subtle sla-numbers">
        {formatHours(t.sla.elapsed_hours)} {resolved ? 'to resolve' : 'open so far'} · target{' '}
        {formatHours(t.sla.target_hours)} · due {formatDateTime(t.sla.due_at)}
      </div>

      <h3 className="side-h3">History for tickets like this</h3>
      <p className="subtle">
        {t.subcategory} tickets at {t.priority_label} breached <strong>{formatPercent(risk.similar_rate, 0)}</strong> of
        the time ({risk.similar_tickets} resolved).
      </p>
      {risk.misrouted_rate !== null && risk.routed_right_rate !== null && t.priority <= 2 && (
        <p className="subtle">
          At this priority, tickets sent to the wrong team first breached {formatPercent(risk.misrouted_rate, 0)} of the
          time, against {formatPercent(risk.routed_right_rate, 0)} when routed right.
        </p>
      )}
    </div>
  )
}

function RoutingCard({ t, resolved }: { t: IncidentDetail; resolved: boolean }) {
  const [suggestion, setSuggestion] = useState<TriageSuggestion>()
  const [error, setError] = useState<string>()

  useEffect(() => {
    if (!t.short_description) return
    const controller = new AbortController()
    const ticket = { short_description: t.short_description, description: t.description ?? '' }
    // The routing model loads in the background after a deploy; give it a few tries.
    const attempt = (triesLeft: number) =>
      postJson<TriageSuggestion>('/api/triage/suggest', ticket, controller.signal)
        .then(setSuggestion)
        .catch((err: unknown) => {
          if (controller.signal.aborted) return
          if (triesLeft > 0) setTimeout(() => void attempt(triesLeft - 1), 5000)
          else setError(err instanceof Error ? err.message : String(err))
        })
    void attempt(3)
    return () => controller.abort()
  }, [t.short_description, t.description])

  const verdict = suggestion && routingVerdict(suggestion.routing, t.initial_group, t.assignment_group, resolved)
  const similar = suggestion?.similar_incidents.filter((s) => s.number !== t.number).slice(0, 3) ?? []

  return (
    <div className="card">
      <h2>Routing check</h2>
      {t.reassignment_count > 0 && (
        <p className="subtle">
          First assigned to {t.initial_group}, reassigned {t.reassignment_count}×.
        </p>
      )}
      {error && <p className="subtle">Routing model unavailable: {error}</p>}
      {!suggestion && !error && <p className="empty">Asking the routing model…</p>}
      {verdict && (
        <div className="verdict" data-tone={verdict.tone} role="status">
          {verdict.message}
        </div>
      )}
      {suggestion && t.opened_at < ROUTING_TRAIN_CUTOFF && (
        <p className="model-note">This ticket predates the model's training cutoff, so the model has seen it.</p>
      )}

      {similar.length > 0 && (
        <>
          <h3 className="side-h3">Similar resolved incidents</h3>
          <ol className="precedents">
            {similar.map((s) => (
              <li key={s.number}>
                <div className="precedent-head">
                  <a href={`#/incidents/${s.number}`}>{s.short_description}</a>
                  <span className="num subtle">{formatPercent(s.score, 0)}</span>
                </div>
                {s.close_notes && <p className="fix">{s.close_notes}</p>}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

function SummaryCard({ number, resolved }: { number: string; resolved: boolean }) {
  const [result, setResult] = useState<TicketSummaryResponse>()
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(false)

  async function summarize() {
    setLoading(true)
    setError(undefined)
    try {
      setResult(await postJson<TicketSummaryResponse>(`/api/incidents/${number}/summary`, {}))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const title = resolved ? 'AI recap' : 'AI handoff note'
  if (!result) {
    return (
      <div className="card agent-cta">
        <div>
          <h2>{title}</h2>
          <p className="subtle">
            Claude reads the ticket, SLA position and work notes and writes a {resolved ? 'recap' : 'handoff note'} for
            the next person.
          </p>
          {error && (
            <div className="banner" role="alert">
              {error}
            </div>
          )}
        </div>
        <button type="button" className="primary" disabled={loading} onClick={() => void summarize()}>
          {loading ? 'Summarizing…' : 'Summarize'}
        </button>
      </div>
    )
  }

  const s = result.summary
  return (
    <div className="card summary">
      <h2>{title}</h2>
      <p className="draft-summary">{s.headline}</p>
      <p className="subtle">{s.status}</p>
      <h3>What was done</h3>
      <ol className="questions">
        {s.actions_taken.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ol>
      <h3>{resolved ? 'Follow-up' : 'Next step'}</h3>
      <p>{s.next_step}</p>
      {s.watch_outs.length > 0 && (
        <>
          <h3>Watch out for</h3>
          <ul className="questions">
            {s.watch_outs.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </>
      )}
      <div className="model-note">
        {result.model} · {result.cached ? 'cached' : `${result.latency_s.toFixed(0)} s · $${result.cost_usd.toFixed(3)}`}
      </div>
    </div>
  )
}
