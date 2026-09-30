import type { RoutingPrediction, SlaStatus } from './api'
import { formatHours, formatPercent } from './format'

export type Route = { page: string; number?: string }

// #/incidents/INC0017396 opens one ticket; everything else is a top-level page id.
export function parseRoute(hash: string): Route {
  const [page = '', number] = hash.replace(/^#\/?/, '').split('/')
  return number && /^INC\d{7}$/i.test(number) ? { page, number: number.toUpperCase() } : { page }
}

// Timestamps have no timezone: they are the company's local time, shown as-is.
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export type SlaView = { fraction: number; label: string; tone: 'good' | 'bad' | 'neutral' }

export function describeSla(sla: SlaStatus, resolved: boolean): SlaView {
  const fraction = sla.elapsed_hours / sla.target_hours
  const gap = Math.abs(sla.target_hours - sla.elapsed_hours)
  if (sla.breached) {
    return { fraction, tone: 'bad', label: `Breached by ${formatHours(Math.max(gap, 0))}` }
  }
  if (resolved) return { fraction, tone: 'good', label: `Met with ${formatHours(gap)} to spare` }
  return { fraction, tone: 'neutral', label: `${formatHours(gap)} left` }
}

// The champion routing model was trained on tickets opened before this date.
export const ROUTING_TRAIN_CUTOFF = '2026-07-01'

export type RoutingVerdict = { tone: 'good' | 'bad' | 'warning'; message: string }

export function routingVerdict(
  prediction: RoutingPrediction,
  firstTeam: string | null,
  currentTeam: string | null,
  resolved: boolean,
): RoutingVerdict {
  const model = `${prediction.assignment_group} (${formatPercent(prediction.confidence, 0)})`
  const misrouted = firstTeam !== null && firstTeam !== currentTeam
  const modelRight = prediction.assignment_group === currentTeam

  if (misrouted) {
    return modelRight
      ? {
          tone: 'good',
          message: `Sent to ${firstTeam} first, then reassigned. The routing model would have picked ${model} at intake.`,
        }
      : {
          tone: 'bad',
          message: `Sent to ${firstTeam} first, then reassigned. The routing model would also have missed it: ${model}.`,
        }
  }
  if (modelRight) return { tone: 'good', message: `Routed right the first time. The routing model agrees: ${model}.` }
  return resolved
    ? { tone: 'bad', message: `Routed right the first time, but the routing model would have picked ${model}.` }
    : {
        tone: 'warning',
        message: `Check the assignment: the routing model expects ${model}, not ${currentTeam ?? 'the current team'}.`,
      }
}
