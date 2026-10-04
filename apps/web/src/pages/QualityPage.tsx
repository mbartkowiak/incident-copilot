import { StatTile } from '../components/StatTile'
import { formatPercent } from '../format'
import { useApi } from '../useApi'

type Summary = {
  cases: number
  team_accuracy_clear: number | null
  team_accuracy_vague: number | null
  grounded_rate: number | null
  expected_kb_cited_rate_clear: number | null
  questions_on_vague_rate: number | null
  questions_on_clear_rate: number | null
  error_rate: number
  mean_cost_usd: number
  p50_latency_s: number
}

type Case = {
  id: string
  is_vague: boolean
  true_group: string
  predicted_group: string | null
  team_correct: boolean
  grounded: boolean
  asked_questions: boolean
  cost_usd: number
  latency_s: number
}

type Report = { run_at: string; summary: Summary; passed: boolean; failures: string[]; thresholds: Record<string, number>; cases: Case[] }

const pct = (v: number | null) => (v === null ? 'n/a' : formatPercent(v, 0))

const COMPARE: { key: keyof Summary; label: string; lowerIsBetter?: boolean }[] = [
  { key: 'team_accuracy_clear', label: 'Right team, clear tickets' },
  { key: 'team_accuracy_vague', label: 'Right team, vague tickets' },
  { key: 'grounded_rate', label: 'Citations grounded in retrieved data' },
  { key: 'expected_kb_cited_rate_clear', label: 'Expected KB article cited' },
  { key: 'questions_on_vague_rate', label: 'Clarifying questions on vague tickets' },
  { key: 'questions_on_clear_rate', label: 'Clarifying questions on clear tickets', lowerIsBetter: true },
]

type FeatureSummary = Record<string, number>
type FeatureReport = {
  run_at: string
  summary: Record<string, FeatureSummary>
  passed: boolean
  failures: string[]
  thresholds: Record<string, number>
  total_cost_usd: number
}

// Every check the feature evals run, in reading order. Rates are over the cases a check applies to.
const FEATURES: { id: string; name: string; checks: [string, string][] }[] = [
  {
    id: 'summary',
    name: 'Ticket summaries',
    checks: [
      ['flags_breach', 'Flags an SLA breach'],
      ['flags_misroute', 'Flags a misroute'],
      ['flags_reopen', 'Flags a reopen'],
      ['no_invented_ids', 'No invented ticket, article or asset IDs'],
      ['resisted_injection', 'Ignores instructions hidden in the ticket'],
    ],
  },
  {
    id: 'kb',
    name: 'Knowledge drafts',
    checks: [
      ['grounded', 'Names only articles it was shown'],
      ['right_article', 'Picks the right article'],
      ['no_personal_data', 'No contact details, ticket numbers or asset tags'],
      ['resisted_injection', 'Ignores instructions hidden in close notes'],
    ],
  },
  {
    id: 'review',
    name: 'Post-incident reviews',
    checks: [
      ['numbers_grounded', 'Every figure comes from the data'],
      ['timeline_shape', 'Timeline of 3-6 timed entries'],
      ['resisted_injection', 'Ignores instructions hidden in tickets'],
    ],
  },
  {
    id: 'problem',
    name: 'Problem records',
    checks: [
      ['numbers_grounded', 'Every figure comes from the data'],
      ['confidence_matches_evidence', 'Confidence matches the evidence grade'],
      ['evidence_cites_numbers', 'Evidence bullets cite numbers'],
      ['resisted_injection', 'Ignores instructions hidden in tickets'],
    ],
  },
  {
    id: 'attachments',
    name: 'Attachment reading',
    checks: [
      ['error_verbatim', 'Copies the error text verbatim'],
      ['no_guessed_site', "Doesn't guess a site"],
      ['no_contact_details', 'No contact details in ticket fields'],
      ['resisted_injection', 'Ignores instructions in a screenshot'],
    ],
  },
  {
    id: 'intake',
    name: 'Virtual agent',
    checks: [
      ['no_questions_on_clear', 'No questions when the report is clear'],
      ['asks_on_vague', 'Asks when the report is vague'],
      ['within_budget', 'At most two questions'],
      ['resisted_injection', "Ignores instructions in the employee's message"],
    ],
  },
]

function FeatureEvals() {
  const { data, error } = useApi<{ latest: FeatureReport; baseline: FeatureReport | null }>(
    '/api/quality/feature-evals',
  )
  if (error) return <div className="banner" role="alert">Couldn't load feature eval results: {error}</div>
  if (!data) return null
  const { latest, baseline } = data
  const cases = Object.values(latest.summary).reduce((n, f) => n + f.cases, 0)

  return (
    <div className="card">
      <h2>Every other AI feature</h2>
      <p className="subtle">
        {cases} cases across six single-call features, including adversarial ones: instructions to the AI hidden in
        ticket text, close notes, sample tickets, a screenshot and an employee's message. The before column found two
        defects: reviews stated durations and times the model had computed itself, once wrongly (4.5 h for 4.4 h), and a
        phishing note's email address was copied into a ticket. The prompt now states those figures, and contact details
        are removed from attachment fields in code. Run on {new Date(latest.run_at).toLocaleDateString()} for $
        {latest.total_cost_usd.toFixed(2)}; inputs are snapshots, so runs are reproducible.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Feature</th>
              <th>Check</th>
              {baseline && <th className="num">Before</th>}
              <th className="num">After</th>
              <th className="num">Floor</th>
            </tr>
          </thead>
          <tbody>
            {FEATURES.flatMap((f) =>
              f.checks.map(([key, label], i) => {
                const after = latest.summary[f.id]?.[key]
                const floor = latest.thresholds[`${f.id}.${key}`]
                const before = baseline?.summary[f.id]?.[key]
                return (
                  <tr key={`${f.id}.${key}`}>
                    <td>{i === 0 ? <strong>{f.name}</strong> : ''}</td>
                    <td>{label}</td>
                    {baseline && <td className="num">{before === undefined ? 'n/a' : pct(before)}</td>}
                    <td className="num">
                      {after === undefined ? 'n/a' : (floor === undefined || after >= floor ? '' : '✗ ') + pct(after)}
                    </td>
                    <td className="num subtle">{floor === undefined ? '—' : pct(floor)}</td>
                  </tr>
                )
              }),
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function QualityPage() {
  const { data, error } = useApi<{ latest: Report; baseline: Report | null }>('/api/quality/agent-evals')

  if (error) return <div className="banner" role="alert">Couldn't load eval results: {error}</div>
  if (!data) return <div className="card empty">Loading…</div>

  const { latest, baseline } = data
  const s = latest.summary

  return (
    <>
      <p className="subtle page-sub">
        How the triage agent is measured: {s.cases} golden tickets from months the routing model never trained on, scored
        with deterministic checks against known answers. Run on {new Date(latest.run_at).toLocaleDateString()}.
      </p>

      <div className={latest.passed ? 'banner banner-info' : 'banner'} role="status">
        <strong>{latest.passed ? '✓ Passes' : '✗ Fails'}</strong> every threshold in the eval gate
        {latest.failures.length > 0 && <>: {latest.failures.join('; ')}</>}
      </div>

      <section className="tiles">
        <StatTile label="Right team, clear tickets" value={pct(s.team_accuracy_clear)} note="threshold ≥ 90%" />
        <StatTile label="Right team, vague tickets" value={pct(s.team_accuracy_vague)} note="humans misroute these too" />
        <StatTile label="Grounded citations" value={pct(s.grounded_rate)} note="only cites what it retrieved" />
        <StatTile
          label="Cost and speed per ticket"
          value={`$${s.mean_cost_usd.toFixed(3)}`}
          note={`${s.p50_latency_s.toFixed(0)} s median, streamed live`}
        />
      </section>

      <section className="split">
        {baseline && (
          <div className="card">
            <h2>Eval-driven prompt fix</h2>
            <p className="subtle">
              The baseline showed the agent quizzing callers on clear tickets. One scoped prompt change fixed it with no
              regressions.
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th className="num">Before</th>
                    <th className="num">After</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARE.map((m) => (
                    <tr key={m.key}>
                      <td>{m.label}</td>
                      <td className="num">{pct(baseline.summary[m.key] as number | null)}</td>
                      <td className="num">
                        <strong>{pct(s[m.key] as number | null)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="card">
          <h2>Routing: trained model vs Claude</h2>
          <p className="subtle">Same 200 held-out tickets. The trained model routes; Claude does the reasoning work.</p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Approach</th>
                  <th className="num">Accuracy</th>
                  <th className="num">Latency</th>
                  <th className="num">Cost / 1k</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Human first assignment</td>
                  <td className="num">75.6%</td>
                  <td className="num">—</td>
                  <td className="num">—</td>
                </tr>
                <tr>
                  <td>
                    <strong>TF-IDF + logistic regression</strong>
                  </td>
                  <td className="num">
                    <strong>95.5%</strong>
                  </td>
                  <td className="num">2 ms</td>
                  <td className="num">~$0</td>
                </tr>
                <tr>
                  <td>Claude Opus 5, zero-shot</td>
                  <td className="num">91.5%</td>
                  <td className="num">1.8 s</td>
                  <td className="num">$5.19</td>
                </tr>
                <tr>
                  <td>Claude Haiku 4.5, zero-shot</td>
                  <td className="num">87.0%</td>
                  <td className="num">0.7 s</td>
                  <td className="num">$0.61</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <FeatureEvals />

      <div className="card">
        <h2>Every golden ticket</h2>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Type</th>
                <th>Correct team</th>
                <th>Agent's team</th>
                <th>Grounded</th>
                <th>Asked questions</th>
                <th className="num">Cost</th>
                <th className="num">Time</th>
              </tr>
            </thead>
            <tbody>
              {latest.cases.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.is_vague ? 'vague' : 'clear'}</td>
                  <td>{c.true_group}</td>
                  <td>
                    {c.team_correct ? '✓' : '✗'} {c.predicted_group ?? '(no draft)'}
                  </td>
                  <td>{c.grounded ? '✓' : '✗'}</td>
                  <td>{c.asked_questions ? 'yes' : 'no'}</td>
                  <td className="num">${c.cost_usd.toFixed(3)}</td>
                  <td className="num">{c.latency_s.toFixed(0)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
