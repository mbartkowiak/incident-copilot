import { describe, expect, it } from 'vitest'
import type { RoutingPrediction } from './api'
import { describeSla, parseRoute, routingVerdict } from './incidents'

describe('parseRoute', () => {
  it('reads a page and an optional ticket number', () => {
    expect(parseRoute('#/incidents')).toEqual({ page: 'incidents' })
    expect(parseRoute('#/incidents/inc0017396')).toEqual({ page: 'incidents', number: 'INC0017396' })
    expect(parseRoute('#/incidents/not-a-ticket')).toEqual({ page: 'incidents' })
    expect(parseRoute('')).toEqual({ page: '' })
  })
})

describe('describeSla', () => {
  const sla = { target_hours: 8, due_at: '2026-08-18T20:00:00', elapsed_hours: 10, breached: true }

  it('labels breached, met and running clocks', () => {
    expect(describeSla(sla, true)).toEqual({ fraction: 1.25, tone: 'bad', label: 'Breached by 2.0 h' })
    expect(describeSla({ ...sla, elapsed_hours: 2, breached: false }, true).label).toBe('Met with 6.0 h to spare')
    expect(describeSla({ ...sla, elapsed_hours: 7.5, breached: false }, false)).toEqual({
      fraction: 0.9375,
      tone: 'neutral',
      label: '30 min left',
    })
  })
})

describe('routingVerdict', () => {
  const predict = (team: string): RoutingPrediction => ({
    assignment_group: team,
    confidence: 0.91,
    alternatives: [],
    needs_review: false,
    model_version: '2',
  })

  it('credits the model when it would have avoided a misroute', () => {
    const v = routingVerdict(predict('Warehouse Systems'), 'Network Operations', 'Warehouse Systems', true)
    expect(v.tone).toBe('good')
    expect(v.message).toContain('would have picked Warehouse Systems (91%)')
  })

  it('reports when the model would also have missed', () => {
    const v = routingVerdict(predict('Service Desk'), 'Network Operations', 'Warehouse Systems', true)
    expect(v.tone).toBe('bad')
  })

  it('flags an open ticket sitting with a team the model disagrees with', () => {
    const v = routingVerdict(predict('Warehouse Systems'), 'Network Operations', 'Network Operations', false)
    expect(v).toEqual({
      tone: 'warning',
      message: 'Check the assignment: the routing model expects Warehouse Systems (91%), not Network Operations.',
    })
  })
})
