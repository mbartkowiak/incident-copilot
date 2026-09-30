import { useState } from 'react'
import { postJson } from '../api'
import type { KbArticle, KbDecision, KbDecisionResult, KbDraftResponse } from '../api'
import { formatPercent } from '../format'

export function KnowledgeCard({ number }: { number: string }) {
  const [result, setResult] = useState<KbDraftResponse>()
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(false)

  async function check() {
    setLoading(true)
    setError(undefined)
    try {
      setResult(await postJson<KbDraftResponse>(`/api/incidents/${number}/kb-draft`, {}))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  if (!result) {
    return (
      <div className="card agent-cta">
        <div>
          <h2>Knowledge</h2>
          <p className="subtle">
            Is this fix documented? Claude compares the resolution with the closest knowledge articles and drafts a
            new or revised article for you to approve.
          </p>
          {error && (
            <div className="banner" role="alert">
              {error}
            </div>
          )}
        </div>
        <button type="button" className="primary" disabled={loading} onClick={() => void check()}>
          {loading ? 'Checking…' : 'Check knowledge base'}
        </button>
      </div>
    )
  }

  const { draft, candidates } = result
  const target = candidates.find((c) => c.number === draft.target_kb)
  const usage = `${result.model} · ${result.cached ? 'cached' : `${result.latency_s.toFixed(0)} s · $${result.cost_usd.toFixed(3)}`}`

  return (
    <div className="card summary">
      <h2>Knowledge</h2>
      {draft.action === 'none' ? (
        <div className="verdict" data-tone="good" role="status">
          Already documented in {target ? <ArticleLabel article={target} /> : draft.target_kb}. {draft.rationale}
        </div>
      ) : (
        <>
          <div className="verdict" data-tone="warning" role="status">
            {draft.action === 'update' ? (
              <>Proposed revision of {target ? <ArticleLabel article={target} /> : draft.target_kb}. </>
            ) : (
              <>No article covers this. Proposed new article. </>
            )}
            {draft.rationale}
          </div>
          <DraftEditor number={number} response={result} />
        </>
      )}
      <Considered candidates={candidates} />
      <div className="model-note">{usage}</div>
    </div>
  )
}

function ArticleLabel({ article }: { article: KbArticle }) {
  return (
    <strong>
      {article.number} “{article.title}”
    </strong>
  )
}

function Considered({ candidates }: { candidates: KbArticle[] }) {
  if (candidates.length === 0) return null
  return (
    <details className="kb considered">
      <summary>Articles compared ({candidates.length})</summary>
      {candidates.map((c) => (
        <details key={c.number} className="kb">
          <summary>
            <span>
              {c.title} <span className="subtle">({c.number})</span>
            </span>
            <span className="num subtle">{formatPercent(c.score, 0)} match</span>
          </summary>
          <div className="kb-body">{c.text.replace(/^# .*\n+/, '')}</div>
        </details>
      ))}
    </details>
  )
}

function DraftEditor({ number, response }: { number: string; response: KbDraftResponse }) {
  const { draft } = response
  const action = draft.action === 'update' ? 'update' : 'new'
  const [title, setTitle] = useState(draft.title)
  const [symptoms, setSymptoms] = useState(draft.symptoms)
  const [cause, setCause] = useState(draft.cause)
  const [steps, setSteps] = useState(draft.steps.join('\n'))
  const [saved, setSaved] = useState<string>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  async function submit(decision: KbDecision['decision']) {
    setSaving(true)
    setError(undefined)
    try {
      const res = await postJson<KbDecisionResult>('/api/knowledge/drafts', {
        source_number: number,
        decision,
        action,
        target_kb: action === 'update' ? draft.target_kb : '',
        title,
        symptoms,
        cause,
        steps: steps.split('\n').map((s) => s.trim()).filter(Boolean),
        model: response.model,
      } satisfies KbDecision)
      setSaved(
        decision === 'rejected'
          ? 'Rejected. Logged so drafting quality can be measured.'
          : `Approved as ${res.article}. It becomes searchable, including by the triage agent, after the next knowledge refresh.`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const locked = saved !== undefined
  return (
    <div className="kb-editor">
      <label>
        Title
        <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} disabled={locked} />
      </label>
      <label>
        Symptoms
        <textarea rows={2} maxLength={2000} value={symptoms} onChange={(e) => setSymptoms(e.target.value)} disabled={locked} />
      </label>
      <label>
        Cause
        <textarea rows={3} maxLength={2000} value={cause} onChange={(e) => setCause(e.target.value)} disabled={locked} />
      </label>
      <label>
        Resolution steps, one per line
        <textarea
          rows={Math.min(10, draft.steps.length + 1)}
          value={steps}
          onChange={(e) => setSteps(e.target.value)}
          disabled={locked}
        />
      </label>
      {saved ? (
        <div className="banner banner-info" role="status">
          {saved}
        </div>
      ) : (
        <div className="draft-actions">
          <button type="button" className="primary" disabled={saving} onClick={() => void submit('approved')}>
            Approve {action === 'update' ? 'revision' : 'article'}
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
