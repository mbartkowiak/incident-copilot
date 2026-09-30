import type { IncidentReview, MajorIncident, MajorIncidentDetail } from '../api'
import { AiDraftCard, Bullets } from '../components/AiDraftCard'
import { ColumnChart } from '../components/ColumnChart'
import { Fact, Stat } from '../components/Facts'
import { IncidentTable } from '../components/IncidentTable'
import { describeSubcategory, formatCount, formatDate, formatHours } from '../format'
import { fillHours, formatDateTime } from '../incidents'
import { useApi } from '../useApi'

export function MajorIncidentsPage() {
  const list = useApi<MajorIncident[]>('/api/major-incidents')
  return (
    <>
      <p className="subtle page-sub">
        Outages found in the ticket stream: a subcategory's daily volume jumping to at least 10 tickets and 5× its
        28-day average, scoped to one site when 80% of reports come from it. Computed in the lakehouse on every
        refresh.
      </p>
      {list.error && (
        <div className="banner" role="alert">
          Couldn't load major incidents: {list.error}
        </div>
      )}
      {!list.data && !list.error && <div className="card empty">Loading…</div>}
      <div className="record-grid">
        {list.data?.map((mi) => (
          <a key={mi.mi_id} className="card record-card" href={`#/major-incidents/${mi.mi_id}`}>
            <div className="record-meta">
              <span className="num">{mi.mi_id}</span>
              <span className="badge" data-tone="bad">
                {mi.worst_priority}
              </span>
            </div>
            <h2>
              {describeSubcategory(mi.subcategory)} · {mi.site ?? 'all sites'}
            </h2>
            <p className="subtle">{formatDate(mi.day)}</p>
            <div className="record-stats">
              <Stat value={formatCount(mi.tickets)} label="tickets" />
              <Stat value={`${mi.spike_ratio.toFixed(0)}×`} label="normal volume" />
              <Stat value={mi.restored_at ? outageHours(mi) : '—'} label="to restore" />
            </div>
            {mi.top_fix && <p className="fix">{mi.top_fix}</p>}
          </a>
        ))}
      </div>
    </>
  )
}

export function MajorIncidentPage({ id }: { id: string }) {
  const detail = useApi<MajorIncidentDetail>(`/api/major-incidents/${id}`)
  const d = detail.data?.incident.mi_id === id ? detail.data : undefined
  return (
    <>
      <a className="back" href="#/major-incidents">
        ← All major incidents
      </a>
      {detail.error && (
        <div className="banner" role="alert">
          {detail.error}
        </div>
      )}
      {!d && !detail.error && <div className="card empty">Loading {id}…</div>}
      {d && <MajorIncidentView d={d} />}
    </>
  )
}

function MajorIncidentView({ d }: { d: MajorIncidentDetail }) {
  const mi = d.incident
  const hours = fillHours(d.timeline)
  const peak = Math.max(...hours.map((h) => h.opened))
  const labelEvery = Math.ceil(hours.length / 8)
  return (
    <>
      <header className="card ticket-head">
        <div className="ticket-id">
          <span className="num">{mi.mi_id}</span>
          <span className="badge" data-tone="bad">
            {mi.worst_priority}
          </span>
        </div>
        <h2 className="ticket-title">
          {describeSubcategory(mi.subcategory)} · {mi.site ?? 'all sites'}
        </h2>
        <dl className="facts">
          <Fact label="Tickets" value={`${formatCount(mi.tickets)} (normally ${mi.baseline_daily.toFixed(1)} a day)`} />
          <Fact label="First report" value={formatDateTime(mi.started_at)} />
          <Fact label="Last resolution" value={mi.restored_at ? formatDateTime(mi.restored_at) : 'Open'} />
          <Fact label="Resolving team" value={mi.resolving_groups.join(', ')} />
          <Fact label="Sites reporting" value={mi.locations.join(', ')} />
          <Fact label="SLA breaches" value={String(mi.sla_breaches)} />
        </dl>
      </header>

      <div className="ticket">
        <div className="ticket-main">
          <AiDraftCard<IncidentReview>
            title="Post-incident review"
            description="Claude drafts the review from the detected outage: impact, timeline from the hourly ticket arrivals, root cause and fix from the resolutions, and follow-ups."
            action="Draft review"
            path={`/api/major-incidents/${mi.mi_id}/review`}
            render={(r) => (
              <>
                <p className="draft-summary">{r.headline}</p>
                <p className="subtle">{r.impact}</p>
                <h3>Timeline</h3>
                <Bullets items={r.timeline} />
                <h3>Root cause</h3>
                <p>{r.root_cause}</p>
                <h3>Resolution</h3>
                <p>{r.resolution}</p>
                <h3>Follow-ups</h3>
                <Bullets items={r.follow_ups} ordered />
              </>
            )}
          />
          <div className="card">
            <h2>Tickets in this incident</h2>
            <p className="subtle">Each one links to its own lifecycle page.</p>
            <IncidentTable incidents={d.tickets} showGroup={mi.resolving_groups.length > 1} />
          </div>
        </div>
        <aside className="ticket-side">
          <div className="card">
            <h2>Tickets per hour</h2>
            <p className="subtle">Peak {peak} in one hour.</p>
            <ColumnChart
              label={`Tickets opened per hour for ${mi.mi_id}; peak ${peak}.`}
              columns={hours.map((h, i) => ({
                key: h.hour,
                axisLabel:
                  i % labelEvery === 0
                    ? new Date(h.hour).toLocaleTimeString('en-US', { hour: 'numeric' })
                    : undefined,
                value: h.opened,
                highlight: h.opened === peak,
                tooltip: `${formatDateTime(h.hour)}: ${h.opened} tickets`,
              }))}
            />
          </div>
          <div className="card">
            <h2>Most common fix</h2>
            <p className="fix">{mi.top_fix ?? 'No resolution recorded.'}</p>
            <p className="subtle">Average resolution {formatHours(mi.avg_mttr_hours)} per ticket.</p>
          </div>
        </aside>
      </div>
    </>
  )
}

function outageHours(mi: MajorIncident): string {
  if (!mi.restored_at) return '—'
  return formatHours((new Date(mi.restored_at).getTime() - new Date(mi.started_at).getTime()) / 3_600_000)
}
