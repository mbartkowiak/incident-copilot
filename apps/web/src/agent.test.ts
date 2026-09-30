import { describe, expect, it } from 'vitest'
import { describeStep } from './agentSteps'
import { parseSse } from './sse'

describe('parseSse', () => {
  it('parses complete messages and keeps the partial remainder', () => {
    const { messages, rest } = parseSse(
      'event: status\ndata: {"run_id":"r1"}\n\nevent: tool_call\ndata: {"id":"t1"}\n\nevent: dra',
    )

    expect(messages).toEqual([
      { event: 'status', data: '{"run_id":"r1"}' },
      { event: 'tool_call', data: '{"id":"t1"}' },
    ])
    expect(rest).toBe('event: dra')
  })

  it('reassembles a message split across chunks', () => {
    const first = parseSse('event: draft\ndata: {"a":')
    const second = parseSse(first.rest + '1}\n\n')

    expect(first.messages).toEqual([])
    expect(second.messages).toEqual([{ event: 'draft', data: '{"a":1}' }])
  })

  it('handles CRLF line endings and multi-line data', () => {
    const { messages } = parseSse('event: x\r\ndata: line1\r\ndata: line2\r\n\r\n')

    expect(messages).toEqual([{ event: 'x', data: 'line1\nline2' }])
  })
})

describe('describeStep', () => {
  it('labels each tool in plain language', () => {
    expect(describeStep('predict_team', {})).toBe('Predict the team with the routing model')
    expect(describeStep('search_knowledge_base', { query: 'vpn', limit: 3 })).toBe('Search the knowledge base “vpn”')
    expect(describeStep('check_recent_activity', { subcategory: 'vpn', location: 'any' })).toBe(
      'Check recent vpn activity at all sites',
    )
  })
})
