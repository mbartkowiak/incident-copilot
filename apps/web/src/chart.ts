import type { Hotspot, TrendPoint } from './api'

export type Week = {
  week: string
  total: number
  byCategory: [string, number][]
  spikes: Hotspot[]
}

export function buildWeeks(points: TrendPoint[], hotspots: Hotspot[]): Week[] {
  const map = new Map<string, Map<string, number>>()
  for (const p of points) {
    const cats = map.get(p.week) ?? new Map<string, number>()
    cats.set(p.category, (cats.get(p.category) ?? 0) + p.incidents)
    map.set(p.week, cats)
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([week, cats]) => ({
      week,
      total: [...cats.values()].reduce((a, b) => a + b, 0),
      byCategory: [...cats.entries()].sort((a, b) => b[1] - a[1]),
      spikes: hotspots.filter((h) => h.week === week),
    }))
}

export function niceTicks(max: number, count = 4): number[] {
  const raw = Math.max(max, 1) / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw
  const ticks: number[] = []
  for (let v = 0; v < max + step; v += step) ticks.push(Math.round(v))
  return ticks
}

// Column with a 4px rounded data-end and a square baseline.
export function columnPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, h, w / 2)
  const base = y + h
  return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${base}Z`
}
