export type SseMessage = { event: string; data: string }

/** Splits a Server-Sent Events buffer into complete messages plus the unparsed remainder. */
export function parseSse(buffer: string): { messages: SseMessage[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const blocks = normalized.split('\n\n')
  const rest = blocks.pop() ?? ''
  const messages: SseMessage[] = []
  for (const block of blocks) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length) messages.push({ event, data: data.join('\n') })
  }
  return { messages, rest }
}

/** POSTs JSON and calls onMessage for each SSE message as it arrives. */
export async function postSse(
  url: string,
  body: unknown,
  onMessage: (m: SseMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    const detail = (await res.json().catch(() => null)) as { detail?: unknown } | null
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : `Request failed (HTTP ${res.status})`)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = parseSse(buffer + value)
    buffer = parsed.rest
    parsed.messages.forEach(onMessage)
  }
}
