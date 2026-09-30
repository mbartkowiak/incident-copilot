export function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? '—'}</dd>
    </div>
  )
}

export function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="record-value">{value}</div>
      <div className="subtle">{label}</div>
    </div>
  )
}
