import { useEffect, useState } from 'react'
import { OverviewPage } from './pages/OverviewPage'
import { QualityPage } from './pages/QualityPage'
import { TriagePage } from './pages/TriagePage'

const PAGES = [
  { id: 'overview', label: 'Overview' },
  { id: 'triage', label: 'Triage' },
  { id: 'quality', label: 'Quality' },
] as const
type PageId = (typeof PAGES)[number]['id']

function pageFromHash(): PageId {
  const id = window.location.hash.replace('#/', '')
  return PAGES.find((p) => p.id === id)?.id ?? 'overview'
}

function App() {
  const [page, setPage] = useState<PageId>(pageFromHash)

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
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
      {page === 'quality' && <QualityPage />}
    </div>
  )
}

export default App
