// Production is served behind CloudFront with the API on the same origin under /api.
export const API_URL: string =
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')

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

export type TriageRequest = { short_description: string; description: string }

export type GroupScore = { assignment_group: string; score: number }

export type RoutingPrediction = {
  assignment_group: string
  confidence: number
  alternatives: GroupScore[]
  needs_review: boolean
  model_version: string
}

export type SimilarIncident = {
  number: string
  short_description: string | null
  close_notes: string | null
  category: string | null
  subcategory: string | null
  assignment_group: string | null
  location: string | null
  priority_label: string | null
  mttr_hours: number | null
  kb_reference: string | null
  occurrences: number
  score: number
}

export type KbArticle = {
  number: string
  title: string
  text: string
  kb_category: string | null
  score: number
}

export type TriageSuggestion = {
  routing: RoutingPrediction
  similar_incidents: SimilarIncident[]
  kb_articles: KbArticle[]
}

export const GROUPS = [
  'Service Desk',
  'Identity & Access Management',
  'Network Operations',
  'End User Computing',
  'Messaging & Collaboration',
  'Security Operations',
  'ERP Applications',
  'Database Administration',
  'Cloud Platform',
  'Warehouse Systems',
] as const

export const PRIORITIES = ['1 - Critical', '2 - High', '3 - Moderate', '4 - Low', '5 - Planning'] as const

export type TriageDraft = {
  assignment_group: string
  priority: string
  summary: string
  likely_cause: string
  resolution_steps: string[]
  citations: string[]
  routing_rationale: string
  related_to_active_spike: boolean
  spike_note: string
  clarifying_questions: string[]
}

export type AgentUsage = {
  run_id: string
  model: string
  turns: number
  latency_s: number
  cost_usd: number
}

export type TriageFeedback = {
  run_id: string
  decision: 'accepted' | 'edited' | 'rejected'
  short_description: string
  description: string
  suggested_group: string
  final_group: string
  priority: string
  resolution: string
  citations: string[]
  agent_model: string
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null
    const detail = typeof body?.detail === 'string' ? body.detail : undefined
    throw new Error(detail ?? `Request failed (HTTP ${res.status})`)
  }
  return (await res.json()) as T
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return parse<T>(await fetch(`${API_URL}${path}`, { signal }))
}

export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return parse<T>(
    await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    }),
  )
}
