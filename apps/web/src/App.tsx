import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Health = { status: string; version: string; environment: string }

type ApiState =
  | { kind: 'loading' }
  | { kind: 'ok'; health: Health }
  | { kind: 'error'; message: string }

function App() {
  const [api, setApi] = useState<ApiState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setApi({ kind: 'ok', health: (await res.json()) as Health })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setApi({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="shell">
      <h1>Incident Intelligence Copilot</h1>
      <p>AI-assisted incident triage and analytics on a Databricks Lakehouse.</p>
      <p className="status" data-state={api.kind}>
        API:{' '}
        {api.kind === 'loading' && 'checking…'}
        {api.kind === 'ok' && `${api.health.status} (v${api.health.version}, ${api.health.environment})`}
        {api.kind === 'error' && `unreachable — ${api.message}`}
      </p>
    </main>
  )
}

export default App
