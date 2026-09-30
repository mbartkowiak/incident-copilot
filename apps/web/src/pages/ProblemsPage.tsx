import type { Evidence, ProblemCandidate, ProblemDetail, ProblemRecord } from '../api'
import { AiDraftCard, Bullets } from '../components/AiDraftCard'
import { ColumnChart } from '../components/ColumnChart'
import { Fact, Stat } from '../components/Facts'
import { IncidentTable } from '../components/IncidentTable'
import { describeSubcategory, formatCount, formatHours, formatPercent, formatWeek } from '../format'
import { useApi } from '../useApi'

const EVIDENCE: Record<Evidence, { tone?: 'good' | 'bad'; label: string; explain: string }> = {
  strong: {
    tone: 'good',
    label: 'Strong evidence',
    explain: 'One fix explains most of the surge, far more than usual: a single underlying cause is likely.',
  },
  moderate: {
    label: 'Moderate evidence',
    explain: 'One fix is more common than usual during the surge, but other causes are also involved.',
  },
  weak: {
    tone: 'bad',
    label: 'Weak evidence',
    explain: 'No fix stands out during the surge. It may be noise or several unrelated causes.',
  },
}

export function ProblemsPage() {
  const list = useApi<ProblemCandidate[]>('/api/problems')
  return (
    <>
      <p className="subtle page-sub">
        Problem candidates: subcategories whose weekly volume ran at least 2.5× their 12-week baseline. Each one is
        ranked by tickets above baseline and graded by how much a single fix explains the surge.
      </p>
      {list.error && (
        <div className="banner" role="alert">
          Couldn't load problems: {list.error}
        </div>
      )}
      {!list.data && !list.error && <div className="card empty">Loading…</div>}
      <div className="record-grid">
        {list.data?.map((p) => (
          <a key={p.problem_id} className="card record-card" href={`#/problems/${p.problem_id}`}>
            <div className="record-meta">
              <span className="num">{p.problem_id}</span>
              <span className="badge" data-tone={EVIDENCE[p.evidence].tone}>
                {EVIDENCE[p.evidence].label}
              </span>
            </div>
            <h2>{describeSubcategory(p.subcategory)}</h2>
            <p className="subtle">
              {surgeLabel(p)}
              {p.major_incident ? ' · triggered by a major incident' : ' · no single outage'}
            </p>
            <div className="record-stats">
              <Stat value={formatCount(p.excess_tickets ?? 0)} label="tickets above baseline" />
              <Stat value={formatHours(p.hours_to_resolve)} label="spent resolving" />
              <Stat value={shareLabel(p)} label="explained by top fix" />
            </div>
          </a>
        ))}
      </div>
    </>
  )
}

export function ProblemPage({ id }: { id: string }) {
  const detail = useApi<ProblemDetail>(`/api/problems/${id}`)
  const d = detail.data?.problem.problem_id === id ? detail.data : undefined
  return (
    <>
      <a className="back" href="#/problems">
        ← All problems
      </a>
      {detail.error && (
        <div className="banner" role="alert">
          {detail.error}
        </div>
      )}
      {!d && !detail.error && <div className="card empty">Loading {id}…</div>}
      {d && <ProblemView d={d} />}
    </>
  )
}

function ProblemView({ d }: { d: ProblemDetail }) {
  const p = d.problem
  const evidence = EVIDENCE[p.evidence]
  return (
    <>
      <header className="card ticket-head">
        <div className="ticket-id">
          <span className="num">{p.problem_id}</span>
          <span className="badge" data-tone={evidence.tone}>
            {evidence.label}
          </span>
        </div>
        <h2 className="ticket-title">{describeSubcategory(p.subcategory)}</h2>
        <dl className="facts">
          <Fact label="Surge" value={surgeLabel(p)} />
          <Fact label="Tickets" value={`${p.tickets} (${p.excess_tickets ?? 0} above baseline)`} />
          <Fact label="Baseline" value={`${(p.baseline_weekly ?? 0).toFixed(1)} a week`} />
          <Fact label="Resolution time spent" value={formatHours(p.hours_to_resolve)} />
          <Fact label="SLA breaches" value={String(p.sla_breaches)} />
          <Fact label="Resolving teams" value={p.resolving_groups.join(', ')} />
        </dl>
        {p.major_incident && (
          <div className="links">
            <a className="badge" data-tone="bad" href={`#/major-incidents/${p.major_incident}`}>
              Triggered by major incident {p.major_incident}
            </a>
          </div>
        )}
      </header>

      <div className="ticket">
        <div className="ticket-main">
          <AiDraftCard<ProblemRecord>
            title="Problem record"
            description="Claude drafts the record from the surge statistics, the dominant fix and sample tickets: problem statement, root-cause hypothesis with its confidence, evidence, workaround and permanent fix."
            action="Draft problem record"
            path={`/api/problems/${p.problem_id}/record`}
            render={(r) => (
              <>
                <p className="draft-summary">{r.title}</p>
                <p className="subtle">{r.problem_statement}</p>
                <h3>Root-cause hypothesis</h3>
                <p>{r.root_cause_hypothesis}</p>
                <h3>Evidence</h3>
                <Bullets items={r.evidence} />
                <h3>Workaround (known error)</h3>
                <p>{r.workaround}</p>
                <h3>Permanent fix</h3>
                <p>{r.permanent_fix}</p>
                <h3>Next steps</h3>
                <Bullets items={r.next_steps} ordered />
              </>
            )}
          />
          <div className="card">
            <h2>Tickets in the surge</h2>
            <IncidentTable incidents={d.tickets} showGroup={p.resolving_groups.length > 1} />
          </div>
        </div>
        <aside className="ticket-side">
          <div className="card">
            <h2>Weekly tickets</h2>
            <p className="subtle">Surge weeks highlighted, with 12 weeks before and 8 after.</p>
            <ColumnChart
              label={`Weekly ${p.subcategory} tickets around the surge; ${p.tickets} during it.`}
              columns={d.weekly.map((w, i) => ({
                key: w.week,
                axisLabel: i % 4 === 0 ? formatWeek(w.week) : undefined,
                value: w.tickets,
                highlight: w.week >= p.first_week && w.week <= p.last_week,
                tooltip: `Week of ${formatWeek(w.week)}: ${w.tickets} tickets`,
              }))}
            />
          </div>
          <div className="card">
            <h2>Root-cause evidence</h2>
            <p className="fix">{p.top_fix ?? 'No resolution recorded.'}</p>
            <p className="subtle">
              This fix resolved <strong>{shareLabel(p)}</strong> of surge tickets, against{' '}
              {p.top_fix_usual_share === null ? 'an unknown share' : formatPercent(p.top_fix_usual_share, 0)} of this
              subcategory's tickets at other times.
            </p>
            <p className="subtle">{evidence.explain}</p>
          </div>
        </aside>
      </div>
    </>
  )
}

function surgeLabel(p: ProblemCandidate): string {
  const weeks = p.weeks === 1 ? '1 week' : `${p.weeks} weeks`
  return p.weeks === 1 ? `Week of ${formatWeek(p.first_week)}` : `${weeks} from ${formatWeek(p.first_week)}`
}

function shareLabel(p: ProblemCandidate): string {
  return p.top_fix_share === null ? '—' : formatPercent(p.top_fix_share, 0)
}
