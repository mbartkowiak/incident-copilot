import { useState } from 'react'
import { ROLE_LABELS, signInAsDemo, signInWithHostedLogin } from '../auth'
import type { AuthConfig, DemoAccount, Role } from '../auth'

const ROLE_BLURBS: Record<Role, string> = {
  employee: 'Report a problem to the virtual agent and get a triaged ticket.',
  dispatcher: 'Triage with the model and the Claude agent, work and resolve tickets, review incidents.',
  knowledge_manager: 'Review AI-drafted knowledge articles before they reach the agent’s search.',
}

export function DemoAccountButton({ account, onError }: { account: DemoAccount; onError: (e: string) => void }) {
  const [busy, setBusy] = useState(false)
  return (
    <button
      type="button"
      className="role-card"
      disabled={busy}
      onClick={() => {
        setBusy(true)
        signInAsDemo(account.username)
          .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)))
          .finally(() => setBusy(false))
      }}
    >
      <span className="role-card-role">{busy ? 'Signing in…' : `Try as ${ROLE_LABELS[account.role].toLowerCase()}`}</span>
      <span className="role-card-name">{account.name}</span>
      <span className="subtle">{account.title}</span>
      <span className="role-card-blurb">{ROLE_BLURBS[account.role]}</span>
    </button>
  )
}

export function SignInPage({ config }: { config: AuthConfig }) {
  const [error, setError] = useState<string>()
  // One button per role; the other employee personas are a click away once signed in.
  const featured = (['employee', 'dispatcher', 'knowledge_manager'] as Role[])
    .map((role) => config.demo_accounts.find((a) => a.role === role))
    .filter((a): a is DemoAccount => a !== undefined)

  return (
    <main className="sign-in">
      <p className="subtle">
        AI-assisted incident management on Databricks and Claude. Each role sees what it needs and can do only what
        its job allows, enforced by the API.
      </p>
      {featured.length > 0 && (
        <div className="role-grid">
          {featured.map((a) => (
            <DemoAccountButton key={a.username} account={a} onError={setError} />
          ))}
        </div>
      )}
      {error && (
        <p className="banner" role="alert">
          {error}
        </p>
      )}
      {config.domain && (
        <p className="subtle">
          Have an account?{' '}
          <button type="button" className="link" onClick={() => void signInWithHostedLogin()}>
            Sign in with your organization account
          </button>{' '}
          (OpenID Connect through Amazon Cognito).
        </p>
      )}
    </main>
  )
}
