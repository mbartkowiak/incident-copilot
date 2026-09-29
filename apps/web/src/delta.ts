export type Delta = {
  text: string
  direction: 'up' | 'down' | 'flat'
  good: boolean
}

export function relativeDelta(current: number, previous: number, upIsGood: boolean): Delta {
  if (previous === 0) return { text: 'no prior data', direction: 'flat', good: true }
  const change = (current - previous) / previous
  return describe(change, `${Math.abs(change * 100).toFixed(0)}%`, upIsGood)
}

export function pointDelta(current: number, previous: number, upIsGood: boolean): Delta {
  const change = current - previous
  return describe(change, `${Math.abs(change * 100).toFixed(1)} pts`, upIsGood)
}

function describe(change: number, magnitude: string, upIsGood: boolean): Delta {
  if (Math.abs(change) < 0.005) return { text: 'no change vs prior period', direction: 'flat', good: true }
  const direction = change > 0 ? 'up' : 'down'
  return {
    text: `${magnitude} vs prior period`,
    direction,
    good: direction === 'up' ? upIsGood : !upIsGood,
  }
}
