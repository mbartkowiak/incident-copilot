import { API_URL } from './api-url'
import { authHeaders, onUnauthorized } from './auth'

export { API_URL }

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

export type TicketDraft = {
  short_description: string
  description: string
  impact: 1 | 2 | 3
  urgency: 1 | 2 | 3
  cmdb_ci: string
}

export type ChatMessage = { role: 'user' | 'assistant'; content: string }

export type IntakeTurnResponse = {
  turn: { reply: string; ready: boolean; ticket: TicketDraft }
  model: string
  cost_usd: number
  latency_s: number
}

export type TicketCreated = {
  number: string
  priority_label: string
  state: string
  assignment_group: string | null
  triage: {
    suggested_group: string
    confidence: number
    mode: 'auto' | 'review'
    category: string | null
    subcategory: string | null
    precedent: string | null
  }
  servicenow_number: string | null
}

export type LiveTicket = {
  number: string
  opened_at: string
  state: string
  caller: string
  location: string
  priority_label: string
  short_description: string
  assignment_group: string | null
  suggested_group: string | null
  triage_confidence: number | null
  triage_mode: string
}

export const CLOSE_CODES = [
  'Solved (Permanently)',
  'Solved Remotely (Permanently)',
  'Solved (Work Around)',
  'Solved Remotely (Work Around)',
  'Not Solved (Not Reproducible)',
  'Closed/Resolved by Caller',
] as const

export type AttachmentFacts = {
  attachment_summary: string
  error_messages: string[]
  device_or_asset: string
  application: string
  site: string
  scope: string
  first_seen: string
  suggested_short_description: string
  description_addendum: string
  sensitive_data: string[]
}

export type AttachmentReadResponse = {
  facts: AttachmentFacts
  files: { name: string; media_type: string; bytes: number }[]
  model: string
  cost_usd: number
  latency_s: number
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
  close_notes?: string | null
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
  major_incident: string | null
  problem: string | null
  source: 'history' | 'live'
  caller_id: string | null
  servicenow_number: string | null
  servicenow_url: string | null
}

export type ServiceNowStatus = {
  enabled: boolean
  instance: string | null
  last_sync: string | null
  last_error: string | null
  imported: number
  pushed: number
  updates_applied: number
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

export type MajorIncident = {
  mi_id: string
  day: string
  subcategory: string
  category: string | null
  site: string | null
  started_at: string
  restored_at: string | null
  tickets: number
  baseline_daily: number
  spike_ratio: number
  worst_priority: string
  locations: string[]
  resolving_groups: string[]
  sla_breaches: number
  avg_mttr_hours: number | null
  top_fix: string | null
}

export type MajorIncidentDetail = {
  incident: MajorIncident
  timeline: { hour: string; opened: number }[]
  tickets: IncidentRow[]
}

export type Evidence = 'strong' | 'moderate' | 'weak'

export type ProblemCandidate = {
  problem_id: string
  subcategory: string
  category: string | null
  first_week: string
  last_week: string
  weeks: number
  tickets: number
  baseline_weekly: number | null
  excess_tickets: number | null
  hours_to_resolve: number | null
  sla_breaches: number
  locations: string[]
  resolving_groups: string[]
  top_fix: string | null
  top_fix_share: number | null
  top_fix_usual_share: number | null
  major_incident: string | null
  evidence: Evidence
}

export type ProblemDetail = {
  problem: ProblemCandidate
  weekly: { week: string; tickets: number }[]
  tickets: IncidentRow[]
}

export type IncidentReview = {
  headline: string
  impact: string
  timeline: string[]
  root_cause: string
  resolution: string
  follow_ups: string[]
}

export type ProblemRecord = {
  title: string
  problem_statement: string
  root_cause_hypothesis: string
  evidence: string[]
  workaround: string
  permanent_fix: string
  next_steps: string[]
}

export type AiDocument<T> = {
  id: string
  document: T
  model: string
  cost_usd: number
  latency_s: number
  cached: boolean
}

export type KbDraft = {
  action: 'none' | 'update' | 'new'
  target_kb: string
  title: string
  symptoms: string
  cause: string
  steps: string[]
  rationale: string
}

export type KbDraftResponse = {
  number: string
  draft: KbDraft
  candidates: KbArticle[]
  model: string
  cost_usd: number
  latency_s: number
  cached: boolean
}

export type KbDecision = {
  source_number: string
  decision: 'approved' | 'rejected'
  action: 'update' | 'new'
  target_kb: string
  title: string
  symptoms: string
  cause: string
  steps: string[]
  model: string
}

export type KbDecisionResult = { status: string; draft_id: string; article: string }

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 401) onUnauthorized()
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null
    const detail = typeof body?.detail === 'string' ? body.detail : undefined
    throw new Error(detail ?? `Request failed (HTTP ${res.status})`)
  }
  return (await res.json()) as T
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return parse<T>(await fetch(`${API_URL}${path}`, { headers: await authHeaders(), signal }))
}

export async function postForm<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  return parse<T>(
    await fetch(`${API_URL}${path}`, { method: 'POST', headers: await authHeaders(), body: form, signal }),
  )
}

export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return parse<T>(
    await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: JSON.stringify(body),
      signal,
    }),
  )
}
