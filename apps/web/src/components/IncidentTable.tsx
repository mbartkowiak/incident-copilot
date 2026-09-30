import type { IncidentRow } from '../api'
import { formatHours } from '../format'
import { formatDateTime } from '../incidents'

export function IncidentTable({ incidents, showGroup = true }: { incidents: IncidentRow[]; showGroup?: boolean }) {
  return (
    <div className="table-scroll table-tall">
      <table className="data-table incident-table">
        <thead>
          <tr>
            <th>Number</th>
            <th>Opened</th>
            <th>Priority</th>
            <th>Short description</th>
            {showGroup && <th>Team</th>}
            <th>Site</th>
            <th>State</th>
            <th>SLA</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <tr key={i.number}>
              <td>
                <a href={`#/incidents/${i.number}`}>{i.number}</a>
              </td>
              <td className="num">{formatDateTime(i.opened_at)}</td>
              <td>{i.priority_label}</td>
              <td className="wrap">{i.short_description}</td>
              {showGroup && <td>{i.assignment_group}</td>}
              <td>{i.location}</td>
              <td>{i.state}</td>
              <td>
                <SlaBadge breached={i.sla_breached} resolved={i.is_resolved} mttr={i.mttr_hours} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SlaBadge({ breached, resolved, mttr }: { breached: boolean; resolved: boolean; mttr: number | null }) {
  if (breached) return <span className="badge" data-tone="bad">Breached</span>
  if (!resolved) return <span className="badge">Running</span>
  return (
    <span className="badge" data-tone="good" title={`Resolved in ${formatHours(mttr)}`}>
      Met
    </span>
  )
}
