import { useEffect, useState } from 'react'
import { parseRoute } from './incidents'
import { GetHelpPage } from './pages/GetHelpPage'
import { IncidentPage } from './pages/IncidentPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { MajorIncidentPage, MajorIncidentsPage } from './pages/MajorIncidentsPage'
import { OverviewPage } from './pages/OverviewPage'
import { ProblemPage, ProblemsPage } from './pages/ProblemsPage'
import { QualityPage } from './pages/QualityPage'
import { TriagePage } from './pages/TriagePage'

// In lifecycle order: overview, report, triage, work, escalate, prevent, measure.
const PAGES = [
  { id: 'overview', label: 'Overview' },
  { id: 'get-help', label: 'Get help' },
  { id: 'triage', label: 'Triage' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'major-incidents', label: 'Major incidents' },
  { id: 'problems', label: 'Problems' },
  { id: 'quality', label: 'Quality' },
] as const
type PageId = (typeof PAGES)[number]['id']

function routeFromHash(): { page: PageId; id?: string } {
  const route = parseRoute(window.location.hash)
  const page = PAGES.find((p) => p.id === route.page)?.id ?? 'overview'
  return { page, id: route.number }
}

function App() {
  const [route, setRoute] = useState(routeFromHash)
  const { page, id } = route

  useEffect(() => {
    const onHash = () => {
      setRoute(routeFromHash())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <div className="page">
      <header className="page-head">
        <h1>Incident Intelligence Copilot</h1>
        <nav className="tabs" aria-label="Pages">
          {PAGES.map((p) => (
            <a key={p.id} href={`#/${p.id}`} aria-current={page === p.id ? 'page' : undefined}>
              {p.label}
            </a>
          ))}
        </nav>
      </header>
      {page === 'overview' && <OverviewPage />}
      {page === 'get-help' && <GetHelpPage />}
      {page === 'triage' && <TriagePage />}
      {page === 'incidents' && (
        <>
          {/* The list stays mounted under a ticket so its filters survive the round trip. */}
          <div className="stack" hidden={id !== undefined}>
            <IncidentsPage />
          </div>
          {id && <IncidentPage number={id} />}
        </>
      )}
      {page === 'major-incidents' && (id ? <MajorIncidentPage id={id} /> : <MajorIncidentsPage />)}
      {page === 'problems' && (id ? <ProblemPage id={id} /> : <ProblemsPage />)}
      {page === 'quality' && <QualityPage />}
    </div>
  )
}

export default App
