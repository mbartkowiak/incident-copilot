// Sign-in with Amazon Cognito. Two ways in, both ending in ordinary Cognito tokens the API
// verifies: a one-click demo account (the API signs in on the visitor's behalf, so no password
// ships in this bundle), or the hosted OIDC login with PKCE, where an organization's own
// identity provider (Okta, Entra ID) can be federated. With auth off (local development),
// everyone holds every role.
import { useSyncExternalStore } from 'react'
import { API_URL } from './api-url'

export type Role = 'employee' | 'dispatcher' | 'knowledge_manager'
export const STAFF: Role[] = ['dispatcher', 'knowledge_manager']
const ALL_ROLES: Role[] = ['employee', 'dispatcher', 'knowledge_manager']
export const ROLE_LABELS: Record<Role, string> = {
  employee: 'Employee',
  dispatcher: 'Dispatcher',
  knowledge_manager: 'Knowledge manager',
}

export type DemoAccount = { username: string; name: string; title: string; role: Role }
export type AuthConfig = {
  enabled: boolean
  region: string
  client_id: string
  domain: string
  demo_accounts: DemoAccount[]
}
export type User = { name: string; site: string; roles: Role[]; demo: boolean }
// A demo session holds no refresh token (see the API's services/cognito.py): when its ID token
// expires it signs in to the same demo account again.
type Session = { idToken: string; refreshToken: string; demoUsername?: string; expiresAt: number; user: User }
type Tokens = { id_token: string; refresh_token?: string; expires_in: number }

const SESSION_KEY = 'copilot.session'
const PKCE_KEY = 'copilot.pkce'
const LOCAL_USER: User = { name: 'Local developer', site: '', roles: ALL_ROLES, demo: false }

// --- store ------------------------------------------------------------------------------------

let config: AuthConfig | undefined
let session: Session | undefined = load()
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

function load(): Session | undefined {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Session) : undefined
  } catch {
    return undefined
  }
}

function save(next: Session | undefined) {
  session = next
  try {
    if (next) sessionStorage.setItem(SESSION_KEY, JSON.stringify(next))
    else sessionStorage.removeItem(SESSION_KEY)
  } catch {
    // Storage blocked: the session lasts until the page reloads.
  }
  emit()
}

export type AuthState =
  | { status: 'loading' }
  | { status: 'signed-out'; config: AuthConfig }
  | { status: 'signed-in'; config: AuthConfig; user: User }

let state: AuthState = { status: 'loading' }

function recompute() {
  if (!config) state = { status: 'loading' }
  else if (!config.enabled) state = { status: 'signed-in', config, user: LOCAL_USER }
  else if (session) state = { status: 'signed-in', config, user: session.user }
  else state = { status: 'signed-out', config }
}
listeners.add(recompute)

export function useAuth(): AuthState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => state,
  )
}

export function hasRole(user: User, ...roles: Role[]): boolean {
  return user.roles.some((r) => roles.includes(r))
}

/** Whether the signed-in user holds any of `roles`, for showing only the actions they can take. */
export function useCan(...roles: Role[]): boolean {
  const auth = useAuth()
  return auth.status === 'signed-in' && hasRole(auth.user, ...roles)
}

// --- tokens -----------------------------------------------------------------------------------

/** Reads the ID token's claims for display. The API verifies the signature; this doesn't. */
export function userFromIdToken(idToken: string): User {
  const payload = idToken.split('.')[1] ?? ''
  const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(payload.length / 4) * 4, '='))
  const claims = JSON.parse(new TextDecoder().decode(Uint8Array.from(json, (c) => c.charCodeAt(0)))) as Record<
    string,
    unknown
  >
  const groups = Array.isArray(claims['cognito:groups']) ? (claims['cognito:groups'] as string[]) : []
  return {
    name: String(claims.name ?? claims.email ?? 'Signed-in user'),
    site: String(claims['custom:site'] ?? ''),
    roles: ALL_ROLES.filter((r) => groups.includes(r)),
    demo: claims['custom:demo'] === 'true',
  }
}

function start(tokens: Tokens, refreshToken = tokens.refresh_token ?? '', demoUsername?: string) {
  save({
    idToken: tokens.id_token,
    refreshToken,
    demoUsername,
    expiresAt: Date.now() + tokens.expires_in * 1000,
    user: userFromIdToken(tokens.id_token),
  })
}

let refreshing: Promise<void> | undefined

async function refresh(current: Session): Promise<void> {
  if (!config) return
  if (current.demoUsername) {
    await signInAsDemo(current.demoUsername).catch(() => save(undefined))
    return
  }
  const res = await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
    },
    body: JSON.stringify({
      AuthFlow: 'REFRESH_TOKEN_AUTH',
      ClientId: config.client_id,
      AuthParameters: { REFRESH_TOKEN: current.refreshToken },
    }),
  })
  const body = (await res.json().catch(() => null)) as {
    AuthenticationResult?: { IdToken: string; ExpiresIn: number }
  } | null
  const result = body?.AuthenticationResult
  if (!res.ok || !result) {
    save(undefined) // the refresh token expired or was revoked: sign in again
    return
  }
  start({ id_token: result.IdToken, expires_in: result.ExpiresIn }, current.refreshToken)
}

/** Headers for an API call, refreshing the ID token when it is about to expire. */
export async function authHeaders(): Promise<Record<string, string>> {
  if (!config?.enabled || !session) return {}
  if (session.expiresAt - Date.now() < 60_000) {
    refreshing ??= refresh(session).finally(() => (refreshing = undefined))
    await refreshing
  }
  return session ? { Authorization: `Bearer ${session.idToken}` } : {}
}

/** The API refused the token (expired, revoked): back to the sign-in page. */
export function onUnauthorized() {
  if (config?.enabled && session) save(undefined)
}

// --- sign-in flows ----------------------------------------------------------------------------

export async function initAuth(): Promise<void> {
  try {
    const res = await fetch(`${API_URL}/api/auth/config`)
    config = res.ok ? ((await res.json()) as AuthConfig) : undefined
  } catch {
    config = undefined
  }
  // Can't reach the API: behave as if auth were off, and let each page report the outage.
  config ??= { enabled: false, region: '', client_id: '', domain: '', demo_accounts: [] }
  if (config.enabled) await completeHostedLogin(config)
  emit()
}

export async function signInAsDemo(username: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/auth/demo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Sign-in failed (HTTP ${res.status})`)
  }
  start((await res.json()) as Tokens, '', username)
}

function redirectUri(): string {
  return `${window.location.origin}/`
}

function base64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

/** Starts the hosted OIDC login (authorization code with PKCE). */
export async function signInWithHostedLogin(): Promise<void> {
  if (!config?.domain) return
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)))
  const challenge = base64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))))
  const stateParam = base64Url(crypto.getRandomValues(new Uint8Array(16)))
  sessionStorage.setItem(PKCE_KEY, JSON.stringify({ verifier, state: stateParam, hash: window.location.hash }))
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.client_id,
    redirect_uri: redirectUri(),
    scope: 'openid email profile',
    code_challenge_method: 'S256',
    code_challenge: challenge,
    state: stateParam,
  })
  window.location.assign(`${config.domain}/oauth2/authorize?${params}`)
}

async function completeHostedLogin(cfg: AuthConfig): Promise<void> {
  const url = new URL(window.location.href)
  const code = url.searchParams.get('code')
  if (!code) return
  let saved: { verifier: string; state: string; hash: string } | undefined
  try {
    saved = JSON.parse(sessionStorage.getItem(PKCE_KEY) ?? 'null') ?? undefined
    sessionStorage.removeItem(PKCE_KEY)
  } catch {
    saved = undefined
  }
  window.history.replaceState(null, '', `${url.pathname}${saved?.hash ?? ''}`)
  if (!saved || url.searchParams.get('state') !== saved.state) return
  const res = await fetch(`${cfg.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: cfg.client_id,
      code,
      redirect_uri: redirectUri(),
      code_verifier: saved.verifier,
    }),
  })
  if (res.ok) start((await res.json()) as Tokens)
}

export function signOut() {
  const wasHosted = session && !session.user.demo
  save(undefined)
  if (wasHosted && config?.domain) {
    const params = new URLSearchParams({ client_id: config.client_id, logout_uri: redirectUri() })
    window.location.assign(`${config.domain}/logout?${params}`)
  }
}
