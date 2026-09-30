import { describe, expect, it } from 'vitest'
import type { AttachmentFacts } from './api'
import { attachmentMessage, priorityLabel, toApiMessages } from './intake'

describe('priorityLabel', () => {
  it('follows the impact x urgency matrix', () => {
    expect(priorityLabel(1, 1)).toBe('1 - Critical')
    expect(priorityLabel(2, 1)).toBe('2 - High')
    expect(priorityLabel(3, 1)).toBe('3 - Moderate')
    expect(priorityLabel(3, 3)).toBe('5 - Planning')
  })
})

describe('attachmentMessage', () => {
  it('passes the extracted facts, not the file, to the virtual agent', () => {
    const facts = {
      attachment_summary: 'VPN client error dialog.',
      error_messages: ['Unable to connect to the portal'],
      device_or_asset: '',
      first_seen: 'this morning',
    } as AttachmentFacts

    expect(attachmentMessage(['vpn-error.png'], facts)).toBe(
      '[Attached vpn-error.png] VPN client error dialog.\nError text: "Unable to connect to the portal"\nStarted: this morning',
    )
  })
})

describe('toApiMessages', () => {
  it('drops display-only text', () => {
    expect(toApiMessages([{ role: 'user', content: 'full', display: 'short' }])).toEqual([
      { role: 'user', content: 'full' },
    ])
  })
})
