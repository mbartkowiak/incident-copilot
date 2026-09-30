import { useEffect, useState } from 'react'
import { parseRoute } from './incidents'
import type { Route } from './incidents'
import { IncidentPage } from './pages/IncidentPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { OverviewPage } from './pages/OverviewPage'
import { QualityPage } from './pages/QualityPage'
import { TriagePage } from './pages/TriagePage'

const PAGES = [
  { id: 'overview', label: 'Overview' },
  { id: 'triage', label: 'Triage' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'quality', label: 'Quality' },
] as const
type PageId = (typeof PAGES)[number]['id']

function routeFromHash(): { page: PageId; number?: string } {
  const route: Route = parseRoute(window.location.hash)
  const page = PAGES.find((p) => p.id === route.page)?.id ?? 'overview'
  return { page, number: page === 'incidents' ? route.number : undefined }
}

function App() {
  const [route, setRoute] = useState(routeFromHash)
  const { page, number } = route

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
      {page === 'triage' && <TriagePage />}
      {page === 'incidents' && (
        <>
          {/* The list stays mounted under a ticket so its filters survive the round trip. */}
          <div className="stack" hidden={number !== undefined}>
            <IncidentsPage />
          </div>
          {number && <IncidentPage number={number} />}
        </>
      )}
      {page === 'quality' && <QualityPage />}
    </div>
  )
}

export default App
