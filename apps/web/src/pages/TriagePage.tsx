import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { postJson } from '../api'
import type { KbArticle, RoutingPrediction, SimilarIncident, TriageRequest, TriageSuggestion } from '../api'
import { formatHours, formatPercent } from '../format'

const SCENARIOS: { label: string; ticket: TriageRequest }[] = [
  {
    label: 'Scanners down at Memphis',
    ticket: {
      short_description: 'Handheld scanner not syncing',
      description: 'Scanner HH-MEM-015 at receiving keeps saying host not reachable and scans stay pending.',
    },
  },
  {
    label: 'VPN after update',
    ticket: {
      short_description: 'VPN drops after update',
      description: 'Since the GlobalProtect update this morning the VPN connects, then drops after a minute.',
    },
  },
  {
    label: 'SAP at month-end',
    ticket: {
      short_description: 'SAP timing out',
      description: "Finance can't run FBL3N, everything times out and we close the books tomorrow.",
    },
  },
  {
    label: 'Certificate warning',
    ticket: {
      short_description: 'Customers see a security warning',
      description: "Customers get 'Your connection is not private' on the carrier booking portal.",
    },
  },
  {
    label: "Vague: can't log in",
    ticket: { short_description: "Can't log in", description: 'It was working yesterday. Please help.' },
  },
  {
    label: 'Vague: printer',
    ticket: { short_description: 'Printer not working', description: 'Nothing comes out.' },
  },
]

const EMPTY: TriageRequest = { short_description: '', description: '' }

export function TriagePage() {
  const [ticket, setTicket] = useState<TriageRequest>(EMPTY)
  const [result, setResult] = useState<TriageSuggestion>()
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(false)
  const inFlight = useRef<AbortController | null>(null)

  async function run(request: TriageRequest) {
    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller
    setLoading(true)
    setError(undefined)
    try {
      setResult(await postJson<TriageSuggestion>('/api/triage/suggest', request, controller.signal))
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (inFlight.current === controller) setLoading(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void run(ticket)
  }

  function pick(scenario: TriageRequest) {
    setTicket(scenario)
    void run(scenario)
  }

  const canSubmit = ticket.short_description.trim().length >= 3 && !loading

  return (
    <>
      <p className="subtle page-sub">
        Paste a new ticket. The routing model predicts the resolving team, and semantic search finds how
        similar incidents were fixed.
      </p>

      <div className="triage">
        <form className="card triage-form" onSubmit={onSubmit}>
          <label htmlFor="short">Short description</label>
          <input
            id="short"
            value={ticket.short_description}
            maxLength={200}
            placeholder="e.g. Label printer printing garbled text"
            onChange={(e) => setTicket({ ...ticket, short_description: e.target.value })}
          />
          <label htmlFor="desc">Description</label>
          <textarea
            id="desc"
            rows={5}
            maxLength={4000}
            value={ticket.description}
            placeholder="What the caller said"
            onChange={(e) => setTicket({ ...ticket, description: e.target.value })}
          />
          <button type="submit" className="primary" disabled={!canSubmit}>
            {loading ? 'Analyzing…' : 'Suggest triage'}
          </button>

          <div className="scenarios">
            <div className="subtle">Or try a scenario</div>
            {SCENARIOS.map((s) => (
              <button key={s.label} type="button" className="chip" onClick={() => pick(s.ticket)}>
                {s.label}
              </button>
            ))}
          </div>
        </form>

        <div className="triage-results" data-stale={loading && !!result}>
          {error && (
            <div className="banner" role="alert">
              {error}
            </div>
          )}
          {!result && !error && (
            <div className="card empty">{loading ? 'Analyzing…' : 'Results appear here.'}</div>
          )}
          {result && (
            <>
              <RoutingCard routing={result.routing} />
              <SimilarIncidents incidents={result.similar_incidents} />
              <KbArticles articles={result.kb_articles} />
            </>
          )}
        </div>
      </div>
    </>
  )
}

function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div className="meter-cell" aria-label={`${label} ${formatPercent(value, 0)}`}>
      <div className="meter" aria-hidden="true">
        <div className="meter-fill" style={{ width: `${value * 100}%` }} />
      </div>
      <span className="num">{formatPercent(value, 0)}</span>
    </div>
  )
}

function RoutingCard({ routing }: { routing: RoutingPrediction }) {
  return (
    <div className="card">
      <div className="subtle">Suggested resolving team</div>
      <div className="routing-team">{routing.assignment_group}</div>
      <Meter value={routing.confidence} label="Confidence" />
      {routing.needs_review && (
        <div className="review-flag" role="status">
          <span aria-hidden="true">⚠</span> Low confidence. Confirm the team before assigning; the
          ticket may be too vague to route.
        </div>
      )}
      {routing.alternatives.length > 0 && (
        <div className="alternatives">
          <div className="subtle">Also plausible</div>
          {routing.alternatives.map((a) => (
            <div key={a.assignment_group} className="alt-row">
              <span>{a.assignment_group}</span>
              <span className="num subtle">{formatPercent(a.score, 0)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="model-note">
        Routing model v{routing.model_version} · TF-IDF + logistic regression · Unity Catalog @champion
      </div>
    </div>
  )
}

function SimilarIncidents({ incidents }: { incidents: SimilarIncident[] }) {
  return (
    <div className="card">
      <h2>Similar resolved incidents</h2>
      {incidents.length === 0 ? (
        <p className="empty">No close matches.</p>
      ) : (
        <ol className="precedents">
          {incidents.map((i) => (
            <li key={i.number}>
              <div className="precedent-head">
                <strong>{i.short_description}</strong>
                <span className="num subtle">{formatPercent(i.score, 0)} match</span>
              </div>
              <div className="subtle">
                {i.assignment_group}
                {i.occurrences > 1 ? ` · seen ${i.occurrences} times, latest ${i.number}` : ` · ${i.number}`}
                {i.mttr_hours !== null && <> · avg resolution {formatHours(i.mttr_hours)}</>}
              </div>
              {i.close_notes && <p className="fix">{i.close_notes}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function KbArticles({ articles }: { articles: KbArticle[] }) {
  return (
    <div className="card">
      <h2>Knowledge articles</h2>
      {articles.map((a) => (
        <details key={a.number} className="kb">
          <summary>
            <span>
              {a.title} <span className="subtle">({a.number})</span>
            </span>
            <span className="num subtle">{formatPercent(a.score, 0)} match</span>
          </summary>
          <div className="kb-body">{a.text.replace(/^# .*\n+/, '')}</div>
        </details>
      ))}
    </div>
  )
}
