import { useState } from 'react'
import type { GroupPerformance, Hotspot, Overview, Trend } from './api'
import { Hotspots } from './components/Hotspots'
import { StatTile } from './components/StatTile'
import { TeamTable } from './components/TeamTable'
import { WeeklyVolume } from './components/WeeklyVolume'
import { pointDelta, relativeDelta } from './delta'
import { formatCount, formatDate, formatHours, formatPercent } from './format'
import { useApi } from './useApi'

const WINDOWS = [30, 90] as const
type WindowDays = (typeof WINDOWS)[number]

function App() {
  const [days, setDays] = useState<WindowDays>(30)
  const overview = useApi<Overview>(`/api/metrics/overview?days=${days}`)
  const groups = useApi<GroupPerformance[]>(`/api/metrics/groups?days=${days}`)
  const trend = useApi<Trend>('/api/metrics/trend?weeks=52')
  const hotspots = useApi<Hotspot[]>('/api/metrics/hotspots?limit=20')

  const error = overview.error ?? groups.error ?? trend.error ?? hotspots.error
  const firstLoad = !overview.data && overview.loading
  const o = overview.data

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Incident Intelligence Copilot</h1>
          <p className="subtle">
            IT operations overview for Meridian Logistics (synthetic data)
            {o && <> · data through {formatDate(o.as_of)}</>}
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Comparison window">
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              aria-pressed={days === w}
              onClick={() => setDays(w)}
            >
              Last {w} days
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="banner" role="alert">
          Couldn't load dashboard data: {error}
        </div>
      )}
      {firstLoad && !error && (
        <div className="banner banner-info" role="status">
          Waking the data warehouse. The first load can take about 20 seconds.
        </div>
      )}

      {o && (
        <section className="tiles" data-stale={overview.loading}>
          <StatTile
            label={`Incidents opened (${days}d)`}
            value={formatCount(o.current.opened)}
            delta={relativeDelta(o.current.opened, o.previous.opened, false)}
            note={`${formatCount(o.current.high_priority)} were P1/P2`}
          />
          <StatTile
            label="Average resolution time"
            value={formatHours(o.current.avg_mttr_hours)}
            delta={relativeDelta(o.current.avg_mttr_hours ?? 0, o.previous.avg_mttr_hours ?? 0, false)}
          />
          <StatTile
            label="SLA breached"
            value={formatPercent(o.current.sla_breach_rate)}
            delta={pointDelta(o.current.sla_breach_rate, o.previous.sla_breach_rate, false)}
          />
          <StatTile
            label="Sent to the wrong team first"
            value={formatPercent(o.current.reassignment_rate)}
            delta={pointDelta(o.current.reassignment_rate, o.previous.reassignment_rate, false)}
            note={`${formatCount(o.open_backlog)} incidents open now`}
          />
        </section>
      )}

      {trend.data && hotspots.data && (
        <section data-stale={trend.loading}>
          <WeeklyVolume points={trend.data.points} hotspots={hotspots.data} />
        </section>
      )}

      <section className="split">
        {hotspots.data && <Hotspots hotspots={hotspots.data} />}
        {groups.data && (
          <div data-stale={groups.loading}>
            <TeamTable groups={groups.data} days={days} />
          </div>
        )}
      </section>
    </div>
  )
}

export default App
