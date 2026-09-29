import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Hotspot, TrendPoint } from '../api'
import { buildWeeks, columnPath, niceTicks } from '../chart'
import { describeSubcategory, formatCount, formatWeek } from '../format'

const PLOT_HEIGHT = 220
const AXIS_BAND = 28
const LABEL_BAND = 18
const MARGIN_LEFT = 44
const MAX_BAR = 24
const GAP = 2

export function WeeklyVolume({ points, hotspots }: { points: TrendPoint[]; hotspots: Hotspot[] }) {
  const weeks = useMemo(() => buildWeeks(points, hotspots), [points, hotspots])
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)
  const [hover, setHover] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [showTable])

  const maxTotal = Math.max(1, ...weeks.map((w) => w.total))
  const ticks = niceTicks(maxTotal)
  const yMax = ticks[ticks.length - 1]
  const plotWidth = Math.max(0, width - MARGIN_LEFT)
  const band = weeks.length ? plotWidth / weeks.length : 0
  const barWidth = Math.max(1, Math.min(MAX_BAR, band - GAP))
  const top = LABEL_BAND
  const y = (v: number) => top + PLOT_HEIGHT - (v / yMax) * PLOT_HEIGHT
  const hovered = hover === null ? null : weeks[hover]
  const spikeCount = weeks.filter((w) => w.spikes.length).length

  return (
    <div className="card chart-card">
      <div className="card-head">
        <div>
          <h2>Weekly incident volume</h2>
          <p className="subtle">
            Last {weeks.length} weeks · {spikeCount} weeks contain a detected spike (3× the trailing
            4-week average at one site)
          </p>
        </div>
        <button type="button" className="ghost" onClick={() => setShowTable((s) => !s)}>
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </div>

      <div className="legend" aria-hidden={showTable}>
        <span className="legend-item">
          <span className="swatch" style={{ background: 'var(--series-2)' }} /> Week with a
          detected spike
        </span>
        <span className="legend-item">
          <span className="swatch" style={{ background: 'var(--series-1)' }} /> Other weeks
        </span>
      </div>

      {showTable ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Week of</th>
                <th className="num">Incidents</th>
                <th>Detected spike</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((w) => (
                <tr key={w.week}>
                  <td>{formatWeek(w.week)}</td>
                  <td className="num">{formatCount(w.total)}</td>
                  <td>{w.spikes.map((s) => describeSubcategory(s.subcategory)).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart" ref={containerRef} onMouseLeave={() => setHover(null)}>
          <svg
            width={width}
            height={top + PLOT_HEIGHT + AXIS_BAND}
            role="img"
            aria-label={`Weekly incidents over the last ${weeks.length} weeks; peak ${maxTotal}. Use "Show table" for values.`}
          >
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={MARGIN_LEFT}
                  x2={width}
                  y1={y(t)}
                  y2={y(t)}
                  className={t === 0 ? 'axis-line' : 'grid-line'}
                />
                <text x={MARGIN_LEFT - 8} y={y(t)} className="tick" textAnchor="end" dy="0.32em">
                  {formatCount(t)}
                </text>
              </g>
            ))}

            {weeks.map((w, i) => {
              const x = MARGIN_LEFT + i * band + (band - barWidth) / 2
              const h = (w.total / yMax) * PLOT_HEIGHT
              const isSpike = w.spikes.length > 0
              const prevMonth = i > 0 ? weeks[i - 1].week.slice(0, 7) : ''
              const showMonth = w.week.slice(0, 7) !== prevMonth
              return (
                <g key={w.week}>
                  <path
                    d={columnPath(x, y(w.total), barWidth, h)}
                    className={isSpike ? 'bar bar-spike' : 'bar'}
                    data-dim={hover !== null && hover !== i}
                  />
                  {isSpike && (
                    <text x={x + barWidth / 2} y={y(w.total) - 6} className="bar-label" textAnchor="middle">
                      {formatCount(w.total)}
                    </text>
                  )}
                  {showMonth && (
                    <text x={x + barWidth / 2} y={top + PLOT_HEIGHT + 18} className="tick" textAnchor="middle">
                      {new Date(`${w.week}T00:00:00`).toLocaleDateString('en-US', { month: 'short' })}
                    </text>
                  )}
                  <rect
                    x={MARGIN_LEFT + i * band}
                    y={top}
                    width={band}
                    height={PLOT_HEIGHT}
                    fill="transparent"
                    onMouseEnter={() => setHover(i)}
                  />
                </g>
              )
            })}
          </svg>

          {hovered && hover !== null && (
            <div
              className="tooltip"
              style={{
                left: Math.min(Math.max(MARGIN_LEFT + (hover + 0.5) * band, 110), width - 110),
                top: 0,
              }}
            >
              <div className="tooltip-title">Week of {formatWeek(hovered.week)}</div>
              <div className="tooltip-row">
                <span>Total</span>
                <strong>{formatCount(hovered.total)}</strong>
              </div>
              {hovered.byCategory.slice(0, 4).map(([cat, n]) => (
                <div className="tooltip-row subtle" key={cat}>
                  <span>{cat}</span>
                  <span>{n}</span>
                </div>
              ))}
              {hovered.spikes.map((s) => (
                <div className="tooltip-spike" key={s.subcategory}>
                  <span className="swatch" style={{ background: 'var(--series-2)' }} />
                  {describeSubcategory(s.subcategory)} · {s.locations.join(', ')}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
