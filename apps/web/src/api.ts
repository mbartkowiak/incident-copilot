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

// Incident timestamps are the company's local wall-clock time without a timezone.
export type IncidentRow = {
  number: string
  opened_at: string
  state: string
  priority_label: string
  short_description: string | null
  assignment_group: string | null
  subcategory: string | null
  location: string | null
  is_resolved: boolean
  sla_breached: boolean
  mttr_hours: number | null
}

export type IncidentList = { as_of: string; incidents: IncidentRow[] }

export type WorkNote = {
  at: string
  author: string
  text: string
  kind: 'reassignment' | 'hold' | 'resolution' | 'note'
}

export type SlaStatus = { target_hours: number; due_at: string; elapsed_hours: number; breached: boolean }

export type BreachRisk = {
  similar_rate: number
  similar_tickets: number
  priority_rate: number
  misrouted_rate: number | null
  routed_right_rate: number | null
}

export type IncidentDetail = {
  number: string
  state: string
  opened_at: string
  resolved_at: string | null
  closed_at: string | null
  priority: number
  priority_label: string
  short_description: string | null
  description: string | null
  category: string | null
  subcategory: string | null
  cmdb_ci: string | null
  location: string | null
  contact_type: string | null
  assignment_group: string | null
  assigned_to: string | null
  initial_group: string | null
  reassignment_count: number
  reopen_count: number
  close_code: string | null
  close_notes: string | null
  work_notes: WorkNote[]
  sla: SlaStatus
  risk: BreachRisk
  as_of: string
}

export type TicketSummary = {
  headline: string
  status: string
  actions_taken: string[]
  next_step: string
  watch_outs: string[]
}

export type TicketSummaryResponse = {
  number: string
  summary: TicketSummary
  model: string
  cost_usd: number
  latency_s: number
  cached: boolean
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
