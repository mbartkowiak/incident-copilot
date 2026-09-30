import { useRef, useState } from 'react'
import { describeStep } from '../agentSteps'
import { API_URL, GROUPS, PRIORITIES, postJson } from '../api'
import type { AgentUsage, TriageDraft, TriageFeedback, TriageRequest } from '../api'
import { postSse } from '../sse'

type Step = {
  id: string
  name: string
  input: Record<string, unknown>
  summary?: string
  error?: string
}

type Grounding = { cited: number; ungrounded: string[] }

type RunState =
  | { phase: 'idle' }
  | { phase: 'running' | 'finished'; steps: Step[]; runId?: string; model?: string; draft?: TriageDraft; grounding?: Grounding; usage?: AgentUsage; error?: string }

export function AgentPanel({ ticket }: { ticket: TriageRequest }) {
  const [run, setRun] = useState<RunState>({ phase: 'idle' })
  const controller = useRef<AbortController | null>(null)

  async function start() {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    setRun({ phase: 'running', steps: [] })
    const update = (fn: (r: Extract<RunState, { phase: 'running' | 'finished' }>) => RunState) =>
      setRun((r) => (r.phase === 'idle' ? r : fn(r)))

    try {
      await postSse(
        `${API_URL}/api/triage/agent`,
        ticket,
        ({ event, data }) => {
          const d = JSON.parse(data) as Record<string, unknown>
          if (event === 'status') update((r) => ({ ...r, runId: d.run_id as string, model: d.model as string }))
          if (event === 'tool_call')
            update((r) => ({
              ...r,
              steps: [...r.steps, { id: d.id as string, name: d.name as string, input: d.input as Record<string, unknown> }],
            }))
          if (event === 'tool_result')
            update((r) => ({
              ...r,
              steps: r.steps.map((s) =>
                s.id === d.id ? { ...s, summary: d.summary as string | undefined, error: d.error as string | undefined } : s,
              ),
            }))
          if (event === 'draft')
            update((r) => ({ ...r, draft: d.draft as TriageDraft, grounding: d.grounding as Grounding }))
          if (event === 'usage') update((r) => ({ ...r, usage: d as unknown as AgentUsage }))
          if (event === 'error') update((r) => ({ ...r, error: d.message as string }))
        },
        abort.signal,
      )
    } catch (err) {
      if (!abort.signal.aborted) update((r) => ({ ...r, error: err instanceof Error ? err.message : String(err) }))
    } finally {
      if (controller.current === abort) update((r) => ({ ...r, phase: 'finished' }))
    }
  }

  if (run.phase === 'idle') {
    return (
      <div className="card agent-cta">
        <div>
          <h2>AI triage agent</h2>
          <p className="subtle">
            Claude investigates with the routing model, incident search, the knowledge base and recent-activity
            checks, then drafts a resolution for you to approve.
          </p>
        </div>
        <button type="button" className="primary" onClick={() => void start()}>
          Draft with AI
        </button>
      </div>
    )
  }

  const running = run.phase === 'running'
  return (
    <div className="card">
      <div className="card-head">
        <h2>AI triage agent</h2>
        {!running && (
          <button type="button" className="ghost" onClick={() => void start()}>
            Run again
          </button>
        )}
      </div>

      <ol className="timeline" aria-live="polite">
        <li data-state="done">Read the ticket</li>
        {run.steps.map((s) => (
          <li key={s.id} data-state={s.error ? 'error' : s.summary ? 'done' : 'active'}>
            <div>{describeStep(s.name, s.input)}</div>
            {(s.summary ?? s.error) && <div className="subtle">{s.summary ?? s.error}</div>}
          </li>
        ))}
        {running && !run.draft && run.steps.every((s) => s.summary ?? s.error) && (
          <li data-state="active">{run.steps.length ? 'Writing the draft' : 'Thinking'}</li>
        )}
      </ol>

      {run.error && (
        <div className="banner" role="alert">
          {run.error}
        </div>
      )}

      {run.draft && run.runId && (
        <DraftEditor
          key={run.runId}
          ticket={ticket}
          runId={run.runId}
          model={run.model ?? ''}
          draft={run.draft}
          grounding={run.grounding}
        />
      )}

      {run.usage && (
        <div className="model-note">
          {run.usage.model} · {run.usage.turns} turns · {run.usage.latency_s.toFixed(0)} s · $
          {run.usage.cost_usd.toFixed(3)}
        </div>
      )}
    </div>
  )
}

function DraftEditor(props: {
  ticket: TriageRequest
  runId: string
  model: string
  draft: TriageDraft
  grounding?: Grounding
}) {
  const { ticket, runId, model, draft, grounding } = props
  const originalSteps = draft.resolution_steps.join('\n')
  const [group, setGroup] = useState(draft.assignment_group)
  const [priority, setPriority] = useState(draft.priority)
  const [steps, setSteps] = useState(originalSteps)
  const [saved, setSaved] = useState<string>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  const changed = group !== draft.assignment_group || priority !== draft.priority || steps !== originalSteps
  const ungrounded = new Set(grounding?.ungrounded ?? [])

  async function submit(decision: TriageFeedback['decision']) {
    setSaving(true)
    setError(undefined)
    try {
      await postJson('/api/triage/feedback', {
        run_id: runId,
        decision,
        short_description: ticket.short_description,
        description: ticket.description,
        suggested_group: draft.assignment_group,
        final_group: group,
        priority,
        resolution: steps,
        citations: draft.citations,
        agent_model: model,
      } satisfies TriageFeedback)
      setSaved(
        decision === 'rejected'
          ? 'Rejected. Thanks, this is logged for evaluation.'
          : 'Saved. Approved drafts become searchable precedents after the next knowledge refresh.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="draft">
      <p className="draft-summary">{draft.summary}</p>

      {draft.related_to_active_spike && (
        <div className="review-flag" role="status">
          <span aria-hidden="true">⚠</span> Part of a wider problem: {draft.spike_note}
        </div>
      )}

      <div className="draft-grid">
        <label>
          Team
          <select value={group} onChange={(e) => setGroup(e.target.value)} disabled={!!saved}>
            {GROUPS.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value)} disabled={!!saved}>
            {PRIORITIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="subtle">{draft.routing_rationale}</p>

      <h3>Likely cause</h3>
      <p>{draft.likely_cause}</p>

      <h3>Resolution steps</h3>
      <textarea
        rows={Math.min(10, draft.resolution_steps.length + 2)}
        value={steps}
        onChange={(e) => setSteps(e.target.value)}
        disabled={!!saved}
        aria-label="Resolution steps, one per line"
      />

      {draft.clarifying_questions.length > 0 && (
        <>
          <h3>Ask the caller</h3>
          <ul className="questions">
            {draft.clarifying_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      )}

      {draft.citations.length > 0 && (
        <div className="citations">
          <span className="subtle">Sources</span>
          {draft.citations.map((c) => (
            <span key={c} className="citation" data-grounded={!ungrounded.has(c)}>
              {ungrounded.has(c) ? '✗' : '✓'} {c}
            </span>
          ))}
          {ungrounded.size > 0 && (
            <span className="subtle">✗ = cited but not retrieved; verify before using</span>
          )}
        </div>
      )}

      {saved ? (
        <div className="banner banner-info" role="status">
          {saved}
        </div>
      ) : (
        <div className="draft-actions">
          <button type="button" className="primary" disabled={saving} onClick={() => void submit(changed ? 'edited' : 'accepted')}>
            {changed ? 'Save edits & approve' : 'Approve'}
          </button>
          <button type="button" className="ghost" disabled={saving} onClick={() => void submit('rejected')}>
            Reject
          </button>
        </div>
      )}
      {error && (
        <div className="banner" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}
