import { useState } from 'react'
import type { ReactNode } from 'react'
import { postJson } from '../api'
import type { AiDocument } from '../api'

// A card that asks the API for an AI-written document on demand and renders it.
export function AiDraftCard<T>(props: {
  title: string
  description: string
  action: string
  path: string
  render: (doc: T) => ReactNode
}) {
  const [result, setResult] = useState<AiDocument<T>>()
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    setError(undefined)
    try {
      setResult(await postJson<AiDocument<T>>(props.path, {}))
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
          <h2>{props.title}</h2>
          <p className="subtle">{props.description}</p>
          {error && (
            <div className="banner" role="alert">
              {error}
            </div>
          )}
        </div>
        <button type="button" className="primary" disabled={loading} onClick={() => void run()}>
          {loading ? 'Drafting…' : props.action}
        </button>
      </div>
    )
  }

  return (
    <div className="card summary">
      <h2>{props.title}</h2>
      {props.render(result.document)}
      <div className="model-note">
        Draft for review · {result.model} ·{' '}
        {result.cached ? 'cached' : `${result.latency_s.toFixed(0)} s · $${result.cost_usd.toFixed(3)}`}
      </div>
    </div>
  )
}

export function Bullets({ items, ordered = false }: { items: string[]; ordered?: boolean }) {
  const children = items.map((i) => <li key={i}>{i}</li>)
  return ordered ? <ol className="questions">{children}</ol> : <ul className="questions">{children}</ul>
}
