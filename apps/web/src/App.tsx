import { useEffect, useState } from 'react'
import { ROLE_LABELS, STAFF, hasRole, signOut, useAuth } from './auth'
import type { AuthConfig, Role, User } from './auth'
import { parseRoute } from './incidents'
import { GetHelpPage } from './pages/GetHelpPage'
import { IncidentPage } from './pages/IncidentPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { MajorIncidentPage, MajorIncidentsPage } from './pages/MajorIncidentsPage'
import { OverviewPage } from './pages/OverviewPage'
import { ProblemPage, ProblemsPage } from './pages/ProblemsPage'
import { QualityPage } from './pages/QualityPage'
import { DemoAccountButton, SignInPage } from './pages/SignInPage'
import { TriagePage } from './pages/TriagePage'

// In lifecycle order: overview, report, triage, work, escalate, prevent, measure. Each page is
// shown to the roles whose API calls it makes; the API enforces the same rules.
const PAGES: { id: string; label: string; roles: Role[] }[] = [
  { id: 'overview', label: 'Overview', roles: STAFF },
  { id: 'get-help', label: 'Get help', roles: ['employee'] },
  { id: 'triage', label: 'Triage', roles: ['dispatcher'] },
  { id: 'incidents', label: 'Incidents', roles: STAFF },
  { id: 'major-incidents', label: 'Major incidents', roles: STAFF },
  { id: 'problems', label: 'Problems', roles: STAFF },
  { id: 'quality', label: 'Quality', roles: STAFF },
]

function routeFromHash(): { page: string; id?: string } {
  const route = parseRoute(window.location.hash)
  return { page: route.page, id: route.number }
}

function App() {
  const auth = useAuth()
  if (auth.status === 'loading') return <div className="page" aria-busy="true" />
  if (auth.status === 'signed-out') {
    return (
      <div className="page">
        <header className="page-head">
          <h1>Incident Intelligence Copilot</h1>
        </header>
        <SignInPage config={auth.config} />
      </div>
    )
  }
  return <SignedIn user={auth.user} config={auth.config} />
}

function UserMenu({ user, config }: { user: User; config: AuthConfig }) {
  const [error, setError] = useState<string>()
  if (!config.enabled) return null
  const role = user.roles.map((r) => ROLE_LABELS[r]).join(', ') || 'No role'
  return (
    <details className="user-menu">
      <summary>
        {user.name} · {role}
      </summary>
      <div className="card user-menu-panel">
        {config.demo_accounts.length > 0 && (
          <>
            <p className="subtle">Switch to another demo account:</p>
            <div className="role-grid compact">
              {config.demo_accounts
                .filter((a) => a.name !== user.name)
                .map((a) => (
                  <DemoAccountButton key={a.username} account={a} onError={setError} />
                ))}
            </div>
            {error && <p className="banner">{error}</p>}
          </>
        )}
        <button type="button" className="ghost" onClick={signOut}>
          Sign out
        </button>
      </div>
    </details>
  )
}

function SignedIn({ user, config }: { user: User; config: AuthConfig }) {
  const [route, setRoute] = useState(routeFromHash)
  const pages = PAGES.filter((p) => hasRole(user, ...p.roles))
  // An unknown page, or one this role can't open, falls back to the role's first page.
  const page = pages.find((p) => p.id === route.page)?.id ?? pages[0]?.id
  const { id } = route

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
        <UserMenu key={user.name} user={user} config={config} />
        <nav className="tabs" aria-label="Pages">
          {pages.map((p) => (
            <a key={p.id} href={`#/${p.id}`} aria-current={page === p.id ? 'page' : undefined}>
              {p.label}
            </a>
          ))}
        </nav>
      </header>
      {page === 'overview' && <OverviewPage />}
      {page === 'get-help' && <GetHelpPage key={user.name} />}
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
      {page === undefined && <p className="banner">This account has no role in the copilot yet.</p>}
    </div>
  )
}

export default App
