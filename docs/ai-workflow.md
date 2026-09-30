# How this project was built with AI coding tools

This project was built with Claude Code as the main pair-programmer, from the first scaffold to the AWS deployment. This document describes the working method: what the tool did, what stayed a human decision, and the checks that kept the speed from costing quality.

## Working agreement
- **`CLAUDE.md` is the contract.** It records the layout, the commands, and the rules the agent follows: every change ships with tests, external services sit behind interfaces with fakes in tests, the agent never executes free-form SQL, secrets only come from the environment, and architecture decisions get an ADR.
- **Small verified increments.** Each step ended with lint, type checks and tests locally, then a push that CI re-checked before deploying. The commit history reads as a sequence of working states.
- **Humans own direction and anything irreversible.** Choosing the project, account setup (Databricks, AWS, GitHub, Anthropic), key rotation, spending money on evals, and making the repo public were explicit decisions by me. Claude Code proposed and executed; it asked before actions with cost or blast radius.

## Where verification caught real problems
AI-generated code is only as good as the checks around it. Examples from this build:

| What happened | How it was caught | Fix |
|---|---|---|
| First routing model scored **100%** | Treated as a red flag, not a win; the synthetic tickets used unique wording per team | Added realistic vague tickets shared across teams; accuracy settled at a credible 95% ([ADR 0001](adr/0001-synthetic-itsm-data.md)) |
| Vector search returned five copies of the same incident, and embedding was rate-limited to ~25 rows/min | Looked at live results, measured indexing rate | Indexed distinct problem statements instead: 77% less embedding, more varied results ([ADR 0003](adr/0003-precedent-level-vector-index.md)) |
| A precedent paired "Service Desk" with a fix that belongs to Identity & Access | Reviewing the live Triage page | Team, fix and KB now come from the same example ticket |
| Agent runner shared per-run state on a singleton | Self-review before running it | Rewrote so all run state lives in the call; safe under concurrent requests |
| GitHub deploys couldn't assume the AWS role | CI failure; inspected the repo's OIDC subject format | Trust policy now matches GitHub's immutable owner/repo-ID subject |
| Production bundle might call `localhost` | Grepped the built JS before uploading | Production builds default to the same-origin API |
| Agent asked clarifying questions on 45% of clear tickets | The eval suite measured it | One scoped prompt change took it to 0% with no regressions; a ceiling is now part of the gate |
| Get help page rendered blank in Chrome | Clicking through the page after unit tests and the build passed | A one-line React effect returned `scrollIntoView()`'s value, which this browser returns as a Promise; effects now never return a value |
| A trained SLA-breach model looked like the obvious feature | Scoring it against a two-column lookup on urgent tickets | The lookup won (AUC 0.69 vs 0.62), so it ships instead ([ADR 0005](adr/0005-sla-risk-lookup-over-classifier.md)) |

## Security habits
- The Claude API key and the Databricks service-principal secret were moved into AWS Secrets Manager without being printed into the session; fingerprints were compared instead of values.
- A secret scan runs over staged files before every commit.
- The API's Databricks identity has read access to one schema and write access to three tables only: live tickets, dispatcher feedback and knowledge drafts.
- When a key was accidentally placed in a committed template file, it was caught before any commit, moved to the git-ignored `.env`, and replaced with a new key.

## What I'd tell a team adopting this
1. Write the conventions down (`CLAUDE.md`) so every session starts from the same rules.
2. Make verification cheap and automatic: types, tests, evals and CI do the reviewing at the pace the code is written.
3. Be suspicious of good-looking numbers. The most useful moments in this project were the ones where a result looked too good or too uniform.
4. Keep irreversible and costly actions as explicit human decisions.
