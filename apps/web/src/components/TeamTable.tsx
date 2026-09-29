import type { GroupPerformance } from '../api'
import { formatCount, formatHours, formatPercent } from '../format'

export function TeamTable({ groups, days }: { groups: GroupPerformance[]; days: number }) {
  const sorted = [...groups].sort((a, b) => b.reassignment_rate - a.reassignment_rate)
  const maxRate = Math.max(0.01, ...sorted.map((g) => g.reassignment_rate))

  return (
    <div className="card">
      <h2>Where misrouted tickets land</h2>
      <p className="subtle">
        Share of each team's resolved incidents (last {days} days) that were first assigned to a
        different team. This is the gap the routing model will target.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Resolving team</th>
              <th className="num">Resolved</th>
              <th className="num">Avg resolution</th>
              <th className="num">SLA breached</th>
              <th>Reassigned first</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((g) => (
              <tr key={g.assignment_group}>
                <td>{g.assignment_group}</td>
                <td className="num">{formatCount(g.incidents)}</td>
                <td className="num">{formatHours(g.avg_mttr_hours)}</td>
                <td className="num">{formatPercent(g.sla_breach_rate)}</td>
                <td>
                  <div className="meter-cell">
                    <div className="meter" aria-hidden="true">
                      <div
                        className="meter-fill"
                        style={{ width: `${(g.reassignment_rate / maxRate) * 100}%` }}
                      />
                    </div>
                    <span className="num">{formatPercent(g.reassignment_rate, 0)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
