import { describe, expect, it } from 'vitest'
import type { Hotspot } from './api'
import { buildWeeks, niceTicks } from './chart'
import { pointDelta, relativeDelta } from './delta'

const spike: Hotspot = {
  week: '2026-03-09',
  category: 'network',
  subcategory: 'lan',
  incidents: 84,
  locations: ['Chicago HQ'],
  max_spike_ratio: 84,
  worst_priority: '2 - High',
}

describe('buildWeeks', () => {
  it('totals categories per week, sorts weeks, and attaches spikes', () => {
    const weeks = buildWeeks(
      [
        { week: '2026-03-09', category: 'network', incidents: 90 },
        { week: '2026-03-02', category: 'software', incidents: 40 },
        { week: '2026-03-09', category: 'software', incidents: 35 },
      ],
      [spike],
    )

    expect(weeks.map((w) => w.week)).toEqual(['2026-03-02', '2026-03-09'])
    expect(weeks[1].total).toBe(125)
    expect(weeks[1].byCategory[0]).toEqual(['network', 90])
    expect(weeks[1].spikes).toHaveLength(1)
    expect(weeks[0].spikes).toHaveLength(0)
  })
})

describe('niceTicks', () => {
  it('produces round steps that cover the max', () => {
    expect(niceTicks(260)).toEqual([0, 100, 200, 300])
    expect(niceTicks(180)).toEqual([0, 50, 100, 150, 200])
  })

  it('handles an empty series', () => {
    expect(niceTicks(0)[0]).toBe(0)
  })
})

describe('deltas', () => {
  it('marks a drop in a lower-is-better metric as good', () => {
    expect(relativeDelta(646, 728, false)).toEqual({
      text: '11% vs prior period',
      direction: 'down',
      good: true,
    })
  })

  it('reports rate changes in percentage points', () => {
    const d = pointDelta(0.048, 0.026, false)
    expect(d.text).toBe('2.2 pts vs prior period')
    expect(d.good).toBe(false)
  })

  it('treats tiny changes as flat', () => {
    expect(pointDelta(0.2451, 0.2449, false).direction).toBe('flat')
  })
})
