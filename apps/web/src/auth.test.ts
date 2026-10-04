import { describe, expect, it } from 'vitest'
import { hasRole, userFromIdToken } from './auth'

function idToken(claims: Record<string, unknown>): string {
  const b64 = (o: unknown) => {
    const bytes = new TextEncoder().encode(JSON.stringify(o))
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  }
  return `${b64({ alg: 'RS256' })}.${b64(claims)}.signature`
}

describe('userFromIdToken', () => {
  it('reads name, site, roles and the demo flag from Cognito claims', () => {
    const user = userFromIdToken(
      idToken({
        name: 'Zoë Ó Briain',
        'custom:site': 'Remote',
        'custom:demo': 'true',
        'cognito:groups': ['employee', 'admins'],
      }),
    )
    expect(user).toEqual({ name: 'Zoë Ó Briain', site: 'Remote', roles: ['employee'], demo: true })
  })

  it('falls back to the email and no roles', () => {
    const user = userFromIdToken(idToken({ email: 'sam@example.com' }))
    expect(user).toEqual({ name: 'sam@example.com', site: '', roles: [], demo: false })
  })
})

describe('hasRole', () => {
  const sam = { name: 'Sam Rivera', site: '', roles: ['dispatcher' as const], demo: true }
  it('admits any listed role', () => {
    expect(hasRole(sam, 'dispatcher', 'knowledge_manager')).toBe(true)
    expect(hasRole(sam, 'employee')).toBe(false)
  })
})
