export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export type PeriodStats = {
  opened: number
  resolved: number
  high_priority: number
  avg_mttr_hours: number | null
  sla_breach_rate: number
  reassignment_rate: number
}

export type Overview = {
  as_of: string
  window_days: number
  open_backlog: number
  current: PeriodStats
  previous: PeriodStats
}

export type TrendPoint = { week: string; category: string; incidents: number }
export type Trend = { weeks: number; points: TrendPoint[] }

export type Hotspot = {
  week: string
  category: string
  subcategory: string
  incidents: number
  locations: string[]
  max_spike_ratio: number
  worst_priority: string
}

export type GroupPerformance = {
  assignment_group: string
  incidents: number
  avg_mttr_hours: number
  p90_mttr_hours: number
  sla_breach_rate: number
  reassignment_rate: number
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Request failed (HTTP ${res.status})`)
  }
  return (await res.json()) as T
}
