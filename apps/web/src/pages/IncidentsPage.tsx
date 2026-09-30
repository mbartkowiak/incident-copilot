import { useState } from 'react'
import type { FormEvent } from 'react'
import { GROUPS } from '../api'
import type { IncidentList } from '../api'
import { IncidentTable } from '../components/IncidentTable'
import { formatDate } from '../format'
import { useApi } from '../useApi'

const STATUSES = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'Open' },
  { id: 'resolved', label: 'Resolved' },
] as const
type Status = (typeof STATUSES)[number]['id']

export function IncidentsPage() {
  const [status, setStatus] = useState<Status>('all')
  const [priority, setPriority] = useState(0)
  const [group, setGroup] = useState('')
  const [breached, setBreached] = useState(false)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')

  const params = new URLSearchParams({ status, priority: String(priority), breached: String(breached), q, limit: '100' })
  if (group) params.set('group', group)
  const list = useApi<IncidentList>(`/api/incidents?${params}`)

  function onSearch(e: FormEvent) {
    e.preventDefault()
    setQ(search.trim())
  }

  return (
    <>
      <div className="page-sub">
        <p className="subtle">
          Every ticket through its lifecycle: SLA clock, work-note journal, routing check and an AI handoff summary
          {list.data && <> · data through {formatDate(list.data.as_of)}</>}
        </p>
      </div>

      <form className="card filters" onSubmit={onSearch}>
        <div className="segmented" role="group" aria-label="Status">
          {STATUSES.map((s) => (
            <button key={s.id} type="button" aria-pressed={status === s.id} onClick={() => setStatus(s.id)}>
              {s.label}
            </button>
          ))}
        </div>
        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(Number(e.target.value))}>
            <option value={0}>Any</option>
            <option value={1}>1 - Critical</option>
            <option value={2}>2 - High</option>
            <option value={3}>3 - Moderate</option>
            <option value={4}>4 - Low</option>
            <option value={5}>5 - Planning</option>
          </select>
        </label>
        <label>
          Team
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">Any</option>
            {GROUPS.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={breached} onChange={(e) => setBreached(e.target.checked)} />
          SLA breached
        </label>
        <div className="search">
          <input
            type="search"
            value={search}
            maxLength={100}
            placeholder="INC number or words"
            aria-label="Search incidents"
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit" className="ghost">
            Search
          </button>
        </div>
      </form>

      {list.error && (
        <div className="banner" role="alert">
          Couldn't load incidents: {list.error}
        </div>
      )}
      {!list.data && list.loading && !list.error && (
        <div className="banner banner-info" role="status">
          Waking the data warehouse. The first load can take about 20 seconds.
        </div>
      )}

      {list.data && (
        <div className="card" data-stale={list.loading}>
          <div className="card-head">
            <h2>{list.data.incidents.length === 100 ? 'Latest 100 matching incidents' : `${list.data.incidents.length} incidents`}</h2>
          </div>
          {list.data.incidents.length === 0 ? (
            <p className="empty">No incidents match these filters.</p>
          ) : (
            <IncidentTable incidents={list.data.incidents} />
          )}
        </div>
      )}
    </>
  )
}
