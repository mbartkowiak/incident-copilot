# Demo video script (~4 minutes)

The video follows one incident through its lifecycle: an employee reports it, it lands in ServiceNow, the copilot triages it, a dispatcher works and resolves it, the fix becomes knowledge, and the patterns across tickets become major-incident and problem records.

## Before recording
- Open the Overview page once so the data warehouse is awake, and run one Triage scenario so the routing model is warm.
- Sign in to the ServiceNow developer instance in a second browser tab, with the incident list filtered to today. Check that the bar on the Triage tab shows ServiceNow connected and no sync error.
- Rehearse once end to end. The demo creates real tickets in the app and in ServiceNow, and the rehearsal shows which resolved ticket gives the best knowledge-base draft (an `update` or `new` reads better on camera than `none`).
- Record the live site full-screen at 1080p.

## 0:00 – 0:20 · The problem
**Screen:** Overview page; hover the March orange bar.
> "About a quarter of IT tickets go to the wrong team first, and urgent tickets that are misrouted miss their SLA 70% of the time, against 11% when they go to the right team. I spent years building on ServiceNow, so I built the copilot I wanted as a dispatcher, on the stack this role uses: Databricks, a trained model, Claude, FastAPI and React on AWS."

*Proves:* product thinking, data pipelines, dashboards.

## 0:20 – 1:00 · An employee reports a problem
**Screen:** Get help, signed in as Priya Shah. Type "VPN won't connect since this morning" and attach `vpn-error.png`.
> "Employees just describe the problem. Claude runs the virtual agent: it already knows who and where they are, reads the screenshot for the exact error code, and asks at most two questions. The server enforces that limit."

**Screen:** answer the question, review the ticket, submit. Pause on the number, priority and assignment.
> "The employee reviews the ticket before it's submitted, and priority comes from ServiceNow's own impact-by-urgency matrix. On submit, the routing model assigns it straight away because it's confident. Anything under 85% waits in a dispatcher's review queue instead."

*Proves:* conversational AI, multimodal document understanding, guardrails.

## 1:00 – 1:30 · It lives in ServiceNow
**Screen:** ServiceNow tab: the new incident, with the correlation ID and the AI work note.
> "Enterprises don't replace their system of record, so the copilot works on top of it. The ticket was created in ServiceNow with real caller, location and group references, plus the AI's reasoning as a work note."

**Screen:** raise a new incident in ServiceNow, leaving the assignment group empty. Wait for it to appear on the app's Incidents tab, then click the **Copilot** button on the ServiceNow form.
> "It works the other way too. A scoped app I built with the ServiceNow SDK pushes new incidents to the copilot, which triages them in about twenty seconds and fills the group only if nobody has chosen one. The Copilot button brings the triage, SLA risk and a Claude summary into the form agents already use."

*Proves:* enterprise integration, ServiceNow platform depth, event-driven design.

## 1:30 – 2:15 · Triage and the agent
**Screen:** Triage → "Scanners down at Memphis".
> "Every ticket gets two things instantly. A routing model trained in Databricks and registered in Unity Catalog predicts the team: 95% accurate on months it never saw, against 76% for human dispatchers. Databricks Vector Search finds how similar incidents were fixed."

**Screen:** Draft with AI. Let the timeline stream, then click Save edits & approve.
> "For harder tickets, a Claude agent investigates with read-only tools and returns a structured draft. The server checks that every source it cites was actually retrieved. Nothing is written until a person approves it, and approved drafts feed back into search."

*Proves:* ML in production, RAG, agentic workflows, human in the loop.

## 2:15 – 2:50 · Work, resolve, and turn the fix into knowledge
**Screen:** Incidents → the ticket you created. Point at the SLA clock and the routing check, then click Summarize.
> "The ticket page has what a dispatcher needs: the SLA clock, how often tickets like this one breached, and a routing check that flags a misroute, which is the strongest early sign of a breach. I tested a breach classifier against that and the lookup won, so no classifier ships."

**Screen:** resolve the ticket (or open the rehearsed resolved ticket), then click Check knowledge base and show the draft.
> "When a ticket is resolved, Claude compares the fix with the knowledge base and proposes nothing, an update or a new article. Almost half of close notes cite no article. Once approved, the next refresh makes the fix searchable for the agent."

*Proves:* ITSM lifecycle, measured model decisions, a knowledge loop.

## 2:50 – 3:25 · Major incidents and problems
**Screen:** Major incidents → the Chicago core switch outage → Draft review.
> "Patterns across tickets are found with plain SQL in the lakehouse: it finds all four planted outages, with 99% precision on which tickets belong to them. Claude drafts the post-incident review from those figures."

**Screen:** Problems → the GlobalProtect regression, with its Strong evidence label → Draft problem record.
> "Problem management looks for slow surges, like a bad VPN client release. Every candidate is graded on its evidence, and the drafted record states how confident its root-cause guess is. On the weak candidates it says so."

*Proves:* analytics engineering, explainable detection, ITIL depth.

## 3:25 – 3:45 · Quality
**Screen:** Quality page.
> "Every change is measured. Thirty golden tickets with known answers gate the agent: one prompt fix cut needless questions on clear tickets from 45% to zero with no regressions. And when Claude was benchmarked against the trained model for routing, the model won on accuracy, speed and cost, so Claude does the reasoning work instead."

*Proves:* evaluation, choosing the right tool.

## 3:45 – 4:05 · How it ships
**Screen:** GitHub repo: the green Actions run, then `docs/ai-workflow.md`.
> "Every push runs tests for every component and deploys through GitHub Actions to ECS and CloudFront with keyless OIDC, all defined in Terraform, with structured telemetry in CloudWatch. I built it with Claude Code as my pair programmer, and tests and evals kept that speed honest. Thanks for watching."

*Proves:* CI/CD, IaC, AWS, observability, AI-native engineering.

## Recording tips
- Keep the cursor still while the agent streams; the timeline is the interesting part.
- If an AI call takes longer than usual, keep talking; every one shows progress.
- The ServiceNow event push usually lands in about 20 seconds. If it's slow, click **Sync now** on the Triage tab.
- Mention the numbers; they are what reviewers remember.
- For a shorter cut (~2:30), drop the major incidents and problems section and the Triage paste box, and keep Get help → ServiceNow → ticket page → Quality.
