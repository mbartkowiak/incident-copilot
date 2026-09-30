import { useState } from 'react'
import { CLOSE_CODES, GROUPS, postJson } from '../api'
import type { IncidentDetail } from '../api'

// What a dispatcher can do with a live ticket: assign it, log work, resolve it.
export function TicketActions({ t, onChanged }: { t: IncidentDetail; onChanged: () => void }) {
  const [group, setGroup] = useState(t.assignment_group ?? GROUPS[0])
  const [note, setNote] = useState('')
  const [closeCode, setCloseCode] = useState<string>(CLOSE_CODES[1])
  const [closeNotes, setCloseNotes] = useState('')
  const [busy, setBusy] = useState<string>()
  const [error, setError] = useState<string>()

  async function act(action: string, path: string, body: unknown) {
    setBusy(action)
    setError(undefined)
    try {
      await postJson(`/api/tickets/${t.number}/${path}`, body)
      setNote('')
      setCloseNotes('')
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(undefined)
    }
  }

  if (t.resolved_at) return null
  return (
    <div className="card kb-editor">
      <h2>Work this ticket</h2>
      <label>
        Assignment group
        <div className="assign-row">
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {GROUPS.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
          <button
            type="button"
            className="ghost"
            disabled={!!busy || group === t.assignment_group}
            onClick={() => void act('assign', 'assign', { group })}
          >
            {t.assignment_group ? 'Reassign' : 'Assign'}
          </button>
        </div>
      </label>
      <label>
        Work note
        <textarea rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <button
        type="button"
        className="ghost"
        disabled={!!busy || !note.trim()}
        onClick={() => void act('note', 'notes', { text: note })}
      >
        Add note
      </button>
      <label>
        Resolve
        <select value={closeCode} onChange={(e) => setCloseCode(e.target.value)}>
          {CLOSE_CODES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <textarea
        rows={2}
        maxLength={4000}
        placeholder="Close notes: what fixed it"
        aria-label="Close notes"
        value={closeNotes}
        onChange={(e) => setCloseNotes(e.target.value)}
      />
      <button
        type="button"
        className="primary"
        disabled={!!busy || closeNotes.trim().length < 5}
        onClick={() => void act('resolve', 'resolve', { close_code: closeCode, close_notes: closeNotes })}
      >
        {busy === 'resolve' ? 'Resolving…' : 'Resolve ticket'}
      </button>
      {error && (
        <div className="banner" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}
