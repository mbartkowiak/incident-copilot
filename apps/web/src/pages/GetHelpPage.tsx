import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { postForm, postJson } from '../api'
import type { AttachmentReadResponse, IntakeTurnResponse, TicketCreated, TicketDraft } from '../api'
import { SAMPLES } from '../attachments'
import { IMPACT, PERSONAS, URGENCY, attachmentMessage, priorityLabel, toApiMessages } from '../intake'
import type { Persona, Turn } from '../intake'

const GREETING = "Hi! I'm the IT virtual agent. Tell me what isn't working, and attach a screenshot if you have one."

export function GetHelpPage() {
  const [persona, setPersona] = useState<Persona>(PERSONAS[0])
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [pending, setPending] = useState<{ names: string[]; content: string; summary: string }>()
  const [draft, setDraft] = useState<TicketDraft>()
  const [created, setCreated] = useState<TicketCreated>()
  const [busy, setBusy] = useState<'reply' | 'attach' | 'submit'>()
  const [error, setError] = useState<string>()
  const [cost, setCost] = useState(0)
  const end = useRef<HTMLDivElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' })
  }, [turns, draft, busy])

  function restart(next: Persona = persona) {
    setPersona(next)
    setTurns([])
    setText('')
    setPending(undefined)
    setDraft(undefined)
    setCreated(undefined)
    setError(undefined)
    setCost(0)
  }

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const typed = text.trim()
    if ((!typed && !pending) || busy) return
    const content = [pending?.content, typed].filter(Boolean).join('\n\n')
    const display = [pending && `📎 ${pending.names.join(', ')}`, typed].filter(Boolean).join('\n')
    const next: Turn[] = [...turns, { role: 'user', content, display }]
    setTurns(next)
    setText('')
    setPending(undefined)
    setBusy('reply')
    setError(undefined)
    try {
      const res = await postJson<IntakeTurnResponse>('/api/intake/chat', {
        caller: persona.name,
        location: persona.site,
        messages: toApiMessages(next),
      })
      setTurns([...next, { role: 'assistant', content: res.turn.reply }])
      setCost((c) => c + res.cost_usd)
      if (res.turn.ready) setDraft(res.turn.ticket)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(undefined)
    }
  }

  async function attach(files: File[]) {
    if (!files.length) return
    setBusy('attach')
    setError(undefined)
    const form = new FormData()
    for (const f of files) form.append('files', f)
    form.append('description', turns.filter((t) => t.role === 'user').map((t) => t.content).join('\n'))
    try {
      const res = await postForm<AttachmentReadResponse>('/api/triage/attachments', form)
      const names = res.files.map((f) => f.name)
      setPending({ names, content: attachmentMessage(names, res.facts), summary: res.facts.attachment_summary })
      setCost((c) => c + res.cost_usd)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(undefined)
    }
  }

  async function attachSample(sample: (typeof SAMPLES)[number]) {
    const blob = await (await fetch(`/samples/${sample.file}`)).blob()
    await attach([new File([blob], sample.file, { type: sample.type })])
  }

  async function submit() {
    if (!draft) return
    setBusy('submit')
    setError(undefined)
    try {
      setCreated(
        await postJson<TicketCreated>('/api/tickets', {
          caller: persona.name,
          location: persona.site,
          contact_type: 'virtual_agent',
          ...draft,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(undefined)
    }
  }

  return (
    <>
      <div className="page-sub">
        <p className="subtle">
          The employee's side: describe a problem in plain words. The virtual agent asks at most two questions, writes
          the ticket and sets its priority, and the ticket is triaged the moment it's submitted.
        </p>
        <label className="persona">
          Signed in as
          <select
            value={persona.name}
            onChange={(e) => restart(PERSONAS.find((p) => p.name === e.target.value) ?? PERSONAS[0])}
          >
            {PERSONAS.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} · {p.role}, {p.site}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="help">
        <div className="card chat">
          <div className="chat-log" aria-live="polite">
            <div className="bubble" data-role="assistant">
              {GREETING}
            </div>
            {turns.map((t, i) => (
              <div key={i} className="bubble" data-role={t.role}>
                {t.display ?? t.content}
              </div>
            ))}
            {busy === 'reply' && (
              <div className="bubble typing" data-role="assistant">
                Thinking…
              </div>
            )}
            <div ref={end} />
          </div>

          {!draft && !created && (
            <form className="chat-input" onSubmit={(e) => void send(e)}>
              {pending && (
                <div className="pending">
                  📎 {pending.names.join(', ')}: {pending.summary}{' '}
                  <button type="button" className="link-button" onClick={() => setPending(undefined)}>
                    Remove
                  </button>
                </div>
              )}
              <textarea
                rows={2}
                maxLength={2000}
                value={text}
                placeholder={turns.length ? 'Your answer' : 'e.g. My scanner says host not reachable'}
                aria-label="Message"
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) void send(e)
                }}
              />
              <div className="chat-actions">
                <input
                  ref={fileInput}
                  type="file"
                  hidden
                  multiple
                  accept="image/png,image/jpeg,image/gif,image/webp,application/pdf"
                  onChange={(e) => {
                    void attach([...(e.target.files ?? [])])
                    e.target.value = ''
                  }}
                />
                <button type="button" className="ghost" disabled={!!busy} onClick={() => fileInput.current?.click()}>
                  {busy === 'attach' ? 'Reading…' : 'Attach'}
                </button>
                <span className="subtle sample-inline">
                  Samples:{' '}
                  {SAMPLES.map((s) => (
                    <button key={s.file} type="button" className="chip" disabled={!!busy} onClick={() => void attachSample(s)}>
                      {s.label}
                    </button>
                  ))}
                </span>
                <button type="submit" className="primary" disabled={!!busy || (!text.trim() && !pending)}>
                  Send
                </button>
              </div>
            </form>
          )}
          {error && (
            <div className="banner" role="alert">
              {error}
            </div>
          )}
        </div>

        <aside className="help-side">
          {created ? (
            <Confirmation created={created} onNew={() => restart()} />
          ) : draft ? (
            <TicketPreview draft={draft} onChange={setDraft} onSubmit={() => void submit()} submitting={busy === 'submit'} />
          ) : (
            <div className="card">
              <h2>Your ticket</h2>
              <p className="subtle">
                The ticket appears here once the virtual agent knows what's wrong. You review it before anything is
                submitted.
              </p>
              <ul className="questions subtle">
                <li>
                  Signed in as {persona.name}, {persona.site}
                </li>
                <li>Caller and site come from sign-on, so you're never asked</li>
              </ul>
            </div>
          )}
          {cost > 0 && <div className="model-note">AI cost for this conversation: ${cost.toFixed(3)}</div>}
        </aside>
      </div>
    </>
  )
}

function TicketPreview(props: {
  draft: TicketDraft
  onChange: (d: TicketDraft) => void
  onSubmit: () => void
  submitting: boolean
}) {
  const { draft, onChange } = props
  return (
    <div className="card kb-editor ticket-preview">
      <h2>Review your ticket</h2>
      <label>
        Summary
        <input
          value={draft.short_description}
          maxLength={200}
          onChange={(e) => onChange({ ...draft, short_description: e.target.value })}
        />
      </label>
      <label>
        Details
        <textarea
          rows={5}
          maxLength={4000}
          value={draft.description}
          onChange={(e) => onChange({ ...draft, description: e.target.value })}
        />
      </label>
      <label>
        Who is affected
        <select value={draft.impact} onChange={(e) => onChange({ ...draft, impact: Number(e.target.value) as 1 | 2 | 3 })}>
          {([1, 2, 3] as const).map((v) => (
            <option key={v} value={v}>
              {IMPACT[v]}
            </option>
          ))}
        </select>
      </label>
      <label>
        How much it blocks work
        <select value={draft.urgency} onChange={(e) => onChange({ ...draft, urgency: Number(e.target.value) as 1 | 2 | 3 })}>
          {([1, 2, 3] as const).map((v) => (
            <option key={v} value={v}>
              {URGENCY[v]}
            </option>
          ))}
        </select>
      </label>
      {draft.cmdb_ci && <p className="subtle">Device or system: {draft.cmdb_ci}</p>}
      <p>
        Priority: <strong>{priorityLabel(draft.impact, draft.urgency)}</strong>
      </p>
      <button
        type="button"
        className="primary"
        disabled={props.submitting || draft.short_description.trim().length < 3}
        onClick={props.onSubmit}
      >
        {props.submitting ? 'Submitting…' : 'Submit ticket'}
      </button>
    </div>
  )
}

function Confirmation({ created, onNew }: { created: TicketCreated; onNew: () => void }) {
  const t = created.triage
  const confidence = `${Math.round(t.confidence * 100)}%`
  return (
    <div className="card summary">
      <h2>Ticket submitted</h2>
      <p className="draft-summary">
        <a href={`#/incidents/${created.number}`}>{created.number}</a> · {created.priority_label}
      </p>
      {t.mode === 'auto' ? (
        <div className="verdict" data-tone="good" role="status">
          Routed straight to <strong>{created.assignment_group}</strong> by the routing model ({confidence} confident).
        </div>
      ) : (
        <div className="verdict" data-tone="warning" role="status">
          A dispatcher will confirm the team. The routing model suggests {t.suggested_group} ({confidence} confident),
          below the 85% needed to assign it automatically.
        </div>
      )}
      {t.subcategory && (
        <p className="subtle">
          Categorized as {t.category} / {t.subcategory} from a similar past incident ({t.precedent}).
        </p>
      )}
      {created.servicenow_number && (
        <p className="subtle">Also raised in ServiceNow as {created.servicenow_number}.</p>
      )}
      <div className="draft-actions">
        <a className="ghost button-link" href={`#/incidents/${created.number}`}>
          Open the ticket
        </a>
        <button type="button" className="ghost" onClick={onNew}>
          Report another issue
        </button>
      </div>
    </div>
  )
}
