import { useEffect, useState } from 'react'
import { OverviewPage } from './pages/OverviewPage'
import { TriagePage } from './pages/TriagePage'

const PAGES = [
  { id: 'overview', label: 'Overview' },
  { id: 'triage', label: 'Triage' },
] as const
type PageId = (typeof PAGES)[number]['id']

function pageFromHash(): PageId {
  return window.location.hash === '#/triage' ? 'triage' : 'overview'
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
      {page === 'overview' ? <OverviewPage /> : <TriagePage />}
    </div>
  )
}

export default App
