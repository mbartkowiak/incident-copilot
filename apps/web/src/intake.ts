import type { AttachmentFacts, ChatMessage } from './api'

// Demo employees. In production the caller and site come from single sign-on.
export const PERSONAS = [
  { name: 'Jordan Lee', site: 'Memphis DC', role: 'Receiving supervisor' },
  { name: 'Priya Shah', site: 'Remote', role: 'Finance analyst' },
  { name: 'Marcus Chen', site: 'Chicago HQ', role: 'Customer service lead' },
  { name: 'Ana Torres', site: 'Dallas DC', role: 'Shipping clerk' },
] as const
export type Persona = (typeof PERSONAS)[number]

// ServiceNow's impact x urgency lookup, as the API applies it.
const MATRIX: Record<string, number> = { '1,1': 1, '1,2': 2, '1,3': 3, '2,1': 2, '2,2': 3, '2,3': 4, '3,1': 3, '3,2': 4, '3,3': 5 }
const LABELS = ['', '1 - Critical', '2 - High', '3 - Moderate', '4 - Low', '5 - Planning']

export function priorityLabel(impact: number, urgency: number): string {
  return LABELS[MATRIX[`${impact},${urgency}`] ?? 5]
}

export const IMPACT = { 1: 'Many people, a site or customers', 2: 'Several people or a team', 3: 'Just me' } as const
export const URGENCY = { 1: "Work is stopped, no workaround", 2: 'Work is slowed', 3: 'It can wait' } as const

// What the model is sent for an attachment: the facts the attachment reader extracted.
export function attachmentMessage(names: string[], facts: AttachmentFacts): string {
  const parts = [`[Attached ${names.join(', ')}] ${facts.attachment_summary}`]
  if (facts.error_messages.length) parts.push(`Error text: ${facts.error_messages.map((e) => `"${e}"`).join('; ')}`)
  if (facts.device_or_asset) parts.push(`Device: ${facts.device_or_asset}`)
  if (facts.first_seen) parts.push(`Started: ${facts.first_seen}`)
  return parts.join('\n')
}

// A transcript turn shown in the chat; `display` overrides what the employee sees.
export type Turn = ChatMessage & { display?: string }

export function toApiMessages(turns: Turn[]): ChatMessage[] {
  return turns.map(({ role, content }) => ({ role, content }))
}
