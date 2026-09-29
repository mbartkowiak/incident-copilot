import type { Hotspot } from '../api'
import { describeSubcategory, formatCount, formatWeek } from '../format'

export function Hotspots({ hotspots }: { hotspots: Hotspot[] }) {
  return (
    <div className="card">
      <h2>Detected spikes</h2>
      <p className="subtle">Weeks where one issue type ran at least 3× its usual volume at a site.</p>
      {hotspots.length === 0 ? (
        <p className="empty">No spikes detected.</p>
      ) : (
        <ol className="hotspots">
          {hotspots.map((h) => (
            <li key={`${h.week}-${h.subcategory}`}>
              <div className="hotspot-main">
                <div className="hotspot-title">{describeSubcategory(h.subcategory)}</div>
                <div className="subtle">
                  Week of {formatWeek(h.week)} · {h.locations.length > 3 ? `${h.locations.length} sites` : h.locations.join(', ')}
                </div>
              </div>
              <div className="hotspot-stats">
                <div className="hotspot-count">{formatCount(h.incidents)}</div>
                <div className="subtle">{h.max_spike_ratio.toFixed(0)}× normal</div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
