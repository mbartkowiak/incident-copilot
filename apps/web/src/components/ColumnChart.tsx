import { useLayoutEffect, useRef, useState } from 'react'
import { columnPath, niceTicks } from '../chart'
import { formatCount } from '../format'

export type Column = {
  key: string
  axisLabel?: string // shown under the column when set
  value: number
  highlight: boolean
  tooltip: string
}

const PLOT_HEIGHT = 150
const TOP = 16
const AXIS_BAND = 24
const MARGIN_LEFT = 36
const MAX_BAR = 28
const GAP = 2

export function ColumnChart({ columns, label }: { columns: Column[]; label: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  const [hover, setHover] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const ticks = niceTicks(Math.max(1, ...columns.map((c) => c.value)), 3)
  const yMax = ticks[ticks.length - 1]
  const band = columns.length ? Math.max(0, width - MARGIN_LEFT) / columns.length : 0
  const barWidth = Math.max(1, Math.min(MAX_BAR, band - GAP))
  const y = (v: number) => TOP + PLOT_HEIGHT - (v / yMax) * PLOT_HEIGHT
  const hovered = hover === null ? undefined : columns[hover]

  return (
    <div className="chart" ref={ref} onMouseLeave={() => setHover(null)}>
      <svg width={width} height={TOP + PLOT_HEIGHT + AXIS_BAND} role="img" aria-label={label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={MARGIN_LEFT} x2={width} y1={y(t)} y2={y(t)} className={t === 0 ? 'axis-line' : 'grid-line'} />
            <text x={MARGIN_LEFT - 6} y={y(t)} className="tick" textAnchor="end" dy="0.32em">
              {formatCount(t)}
            </text>
          </g>
        ))}
        {columns.map((c, i) => {
          const x = MARGIN_LEFT + i * band + (band - barWidth) / 2
          return (
            <g key={c.key}>
              {c.value > 0 && (
                <path
                  d={columnPath(x, y(c.value), barWidth, (c.value / yMax) * PLOT_HEIGHT)}
                  className={c.highlight ? 'bar bar-spike' : 'bar'}
                  data-dim={hover !== null && hover !== i}
                />
              )}
              {c.axisLabel && (
                <text x={x + barWidth / 2} y={TOP + PLOT_HEIGHT + 16} className="tick" textAnchor="middle">
                  {c.axisLabel}
                </text>
              )}
              <rect
                x={MARGIN_LEFT + i * band}
                y={TOP}
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
          style={{ left: Math.min(Math.max(MARGIN_LEFT + (hover + 0.5) * band, 110), width - 110), top: 0 }}
        >
          {hovered.tooltip}
        </div>
      )}
    </div>
  )
}
