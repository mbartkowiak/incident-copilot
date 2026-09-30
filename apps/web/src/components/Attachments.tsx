import { useRef } from 'react'
import type { AttachmentReadResponse } from '../api'
import { ACCEPT, SAMPLES } from '../attachments'

function formatBytes(n: number): string {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function AttachmentPicker(props: {
  files: File[]
  onAdd: (files: File[]) => void
  onRemove: (name: string) => void
  onSample: (sample: (typeof SAMPLES)[number]) => void
  onRead: () => void
  reading: boolean
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <div className="attachments">
      <div className="attachments-head">
        <span className="field-label">Attachments</span>
        <span className="subtle">Screenshots, photos or PDFs · up to 3 files, 5 MB each · never stored</span>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          props.onAdd([...(e.target.files ?? [])])
          e.target.value = ''
        }}
      />
      {props.files.length > 0 && (
        <ul className="file-list">
          {props.files.map((f) => (
            <li key={f.name}>
              <span className="file-name">{f.name}</span>
              <span className="subtle num">{formatBytes(f.size)}</span>
              <button type="button" className="link-button" onClick={() => props.onRemove(f.name)} aria-label={`Remove ${f.name}`}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="attachment-actions">
        <button type="button" className="ghost" onClick={() => input.current?.click()}>
          Add files…
        </button>
        <button type="button" className="ghost" disabled={props.files.length === 0 || props.reading} onClick={props.onRead}>
          {props.reading ? 'Reading…' : 'Read attachments with AI'}
        </button>
      </div>
      <div className="sample-row">
        <span className="subtle">Or attach a sample:</span>
        {SAMPLES.map((s) => (
          <button key={s.file} type="button" className="chip" onClick={() => props.onSample(s)}>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function AttachmentFactsCard(props: {
  result: AttachmentReadResponse
  onApply: () => void
  onDismiss: () => void
  applied: boolean
}) {
  const f = props.result.facts
  const facts: [string, string][] = [
    ['Device or asset', f.device_or_asset],
    ['Application', f.application],
    ['Site', f.site],
    ['Who is affected', f.scope === 'unknown' ? '' : f.scope],
    ['Started', f.first_seen],
  ]
  const shown = facts.filter(([, v]) => v)
  return (
    <div className="card summary">
      <h2>From the attachments</h2>
      <p className="draft-summary">{f.attachment_summary}</p>
      {f.error_messages.length > 0 && (
        <>
          <h3>Error text</h3>
          <ul className="questions error-text">
            {f.error_messages.map((m) => (
              <li key={m}>
                <code>{m}</code>
              </li>
            ))}
          </ul>
        </>
      )}
      {shown.length > 0 && (
        <dl className="facts compact-facts">
          {shown.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <h3>Suggested for the ticket</h3>
      <p>
        <strong>{f.suggested_short_description}</strong>
      </p>
      <p className="subtle">{f.description_addendum}</p>
      {f.sensitive_data.length > 0 && (
        <div className="review-flag" role="status">
          <span aria-hidden="true">⚠</span> The attachments contain {f.sensitive_data.join(', ')}. These were left out of
          the suggested text; don't paste them into the ticket.
        </div>
      )}
      {props.applied ? (
        <div className="banner banner-info" role="status">
          Added to the ticket. Triage results below use the enriched text.
        </div>
      ) : (
        <div className="draft-actions">
          <button type="button" className="primary" onClick={props.onApply}>
            Add to ticket &amp; triage
          </button>
          <button type="button" className="ghost" onClick={props.onDismiss}>
            Dismiss
          </button>
        </div>
      )}
      <div className="model-note">
        {props.result.files.map((x) => x.name).join(', ')} · {props.result.model} ·{' '}
        {props.result.latency_s.toFixed(0)} s · ${props.result.cost_usd.toFixed(3)}
      </div>
    </div>
  )
}
