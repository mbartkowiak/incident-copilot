import { useState } from 'react'
import { postJson } from '../api'
import type { ServiceNowStatus } from '../api'
import { useApi } from '../useApi'

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  return minutes < 1 ? 'just now' : minutes === 1 ? '1 min ago' : `${minutes} min ago`
}

// Connection state of the ServiceNow connector, with a manual sync.
export function ServiceNowBar() {
  const [version, setVersion] = useState(0)
  const status = useApi<ServiceNowStatus>(`/api/servicenow/status?v=${version}`)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string>()
  const s = status.data

  if (!s?.enabled) return null

  async function sync() {
    setSyncing(true)
    setError(undefined)
    try {
      await postJson('/api/servicenow/sync', {})
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSyncing(false)
    }
  }

  const host = s.instance ? new URL(s.instance).host : ''
  return (
    <div className="card servicenow-bar">
      <span className="badge" data-tone={s.last_error ? 'bad' : 'good'}>
        ServiceNow {s.last_error ? 'error' : 'connected'}
      </span>
      <span className="subtle">
        {host} · {s.last_sync ? `synced ${ago(s.last_sync)}` : 'not synced yet'} · {s.imported} imported ·{' '}
        {s.pushed} sent · {s.updates_applied} updates pulled
      </span>
      {(s.last_error ?? error) && <span className="subtle">{s.last_error ?? error}</span>}
      <button type="button" className="ghost" disabled={syncing} onClick={() => void sync()}>
        {syncing ? 'Syncing…' : 'Sync now'}
      </button>
    </div>
  )
}
