# 0011: Sign in with Cognito, enforce roles in the API, keep the demo one click away

**Status:** Accepted, 2026-10-04

## Context
Until now the site was open: anyone could submit tickets as any persona, resolve tickets, and approve knowledge drafts. ADR 0006 called out the worst consequence: approved drafts become text the triage agent retrieves, so an anonymous approval was a prompt-injection path. Journals recorded every action as "Dispatcher", so there was no audit trail. An enterprise copilot needs identity from the company's own sign-on, roles that match the jobs, and a record of who decided what.

The constraint is the audience: recruiters and interviewers have to try the app in one click, without an account.

## Decision
- **Amazon Cognito is the identity provider the app trusts** (`infra/terraform/auth.tf`). A user pool with three groups, which are the roles: `employee`, `dispatcher` and `knowledge_manager`. Self sign-up is off. Federating Okta or Entra ID into the pool over SAML or OIDC is configuration, with no code change.
- **Two ways in, both ending in ordinary Cognito ID tokens:**
  - **Hosted login with OIDC authorization code and PKCE** for real accounts. The single-page app is a public client, so it holds no client secret.
  - **One-click demo accounts.** The sign-in page offers "Try as employee / dispatcher / knowledge manager", and the user menu switches between six demo accounts (the four Get help personas, a dispatcher and a knowledge manager). `POST /api/auth/demo` signs in on the visitor's behalf. The demo password lives only in Secrets Manager and the API, and demo sign-ins are rate-limited.
- **Demo visitors get only the ID token.** Cognito's access token can call self-service APIs (change attributes, delete the user), and a refresh token can be swapped for one. Handing either to visitors would let anyone rename or delete a shared demo account. So the API keeps them, and an expired demo session signs in again. The app client also refuses attribute writes other than email, and site and the demo flag are custom attributes users can't change.
- **The API enforces everything** (`app/auth.py`). It verifies the token's RS256 signature against the pool's published keys and checks issuer, audience and `token_use`; unknown Cognito groups grant nothing. Each route declares the roles it admits:

  | Role | Can |
  |---|---|
  | employee | Get help: chat with the virtual agent, read attachments, submit a ticket |
  | dispatcher | Triage (routing, search, the agent), approve agent drafts, assign, note and resolve tickets, sync ServiceNow |
  | knowledge manager | Approve or reject knowledge drafts |
  | dispatcher or knowledge manager | Read analytics, queues, tickets, incidents and problems; generate AI summaries, reviews, problem records and knowledge drafts |
  | ServiceNow (shared secret) | Read a ticket and its summary, for the Copilot form button |

  Only `/health`, `GET /api/auth/config`, `POST /api/auth/demo` and the ServiceNow event push (its own shared secret) are open.
- **Identity comes from the token, not the request.** A ticket's caller and site are the signed-in user's, whatever the request body says. Journal entries carry the user's name. Agent-draft and knowledge decisions record `decided_by` in Delta, and telemetry records the user on every decision.
- **The web app shows each role what it can use.** Tabs and actions follow the same rules (an employee sees only Get help; a dispatcher sees a knowledge draft but not its approve button), but the API is the enforcement point.
- **Auth is off without a user pool.** Local development and the unit tests run as one local user holding every role, so nothing else had to change.
- **Secrets stay out of Terraform state.** Terraform creates the demo users and an empty secret; `infra/scripts/set-demo-password.sh` generates the password, stores it, and sets it on each demo user.

## Consequences
- The prompt-injection path from ADR 0006 now needs a knowledge-manager account, and every approval names its approver.
- Sign-in is one click for visitors, but they can't take over the shared accounts.
- Anyone can still use the demo knowledge-manager account. A real deployment would map the role to a directory group and remove the demo accounts.
- Signing in also keeps crawlers from waking the SQL warehouse, since every data endpoint now needs a token.
- In-process verification caches the pool's signing keys for an hour. Disabling a user takes effect when their ID token expires (at most 60 minutes) or, for hosted-login users, when their refresh token is revoked.
- Cost: Cognito's free tier covers this usage. The new secret is $0.40 a month.
