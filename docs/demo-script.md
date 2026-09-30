# Demo video script (~3 minutes)

Record the live site full-screen at 1080p. Before recording, open the Overview page once so the data warehouse is awake, and run one Triage scenario so the routing model is warm.

## 0:00 – 0:20 · The problem
**Screen:** Overview page.
> "About a quarter of IT tickets go to the wrong team first, and every hop adds hours. I spent years building on ServiceNow, so I built the tool I wanted as a dispatcher, on the stack this role uses: Databricks, a trained model, a Claude agent, FastAPI and React on AWS."

## 0:20 – 0:50 · Data and analytics
**Screen:** hover the January and March orange bars, then the "Where misrouted tickets land" table.
> "Incident data lands in a Databricks medallion pipeline with data-quality rules and PII scrubbing. The gold tables drive this dashboard: spike detection found every planted outage, like the Chicago core switch failure. The table shows where misrouted tickets end up, which is the gap the rest of the app closes."

*Proves:* data pipelines, Lakehouse, dashboards, product thinking.

## 0:50 – 1:30 · Instant triage (ML + RAG)
**Screen:** Triage → "Scanners down at Memphis".
> "A new ticket gets two things instantly and for free. A routing model, trained and registered in Unity Catalog with MLflow, predicts the team: 95% accurate on months it never saw, against 76% for first-time human routing. And Databricks Vector Search finds how similar incidents were fixed, plus the right KB article."

**Screen:** "Vague: can't log in".
> "When the ticket is vague, the model says so: low confidence, a review flag, and the plausible alternatives."

*Proves:* ML model endpoints, RAG, semantic search, enterprise UX.

## 1:30 – 2:20 · The agent
**Screen:** back to the scanner ticket → Draft with AI. Let the timeline stream.
> "The Claude agent investigates with read-only tools: the routing model, both searches, and a check for a wider outage. You can watch each step stream in. It returns a structured draft: team, priority, likely cause, steps, and sources. The server checks that every citation is something it actually retrieved; these ticks mean grounded."

**Screen:** change the priority, click Save edits & approve.
> "Nothing is written without a person. The dispatcher edits and approves, and approved drafts flow back into search, so the system learns from its users."

*Proves:* agentic workflows, conversational/AI features in production, human-in-the-loop design.

## 2:20 – 2:50 · Quality and operations
**Screen:** Quality page.
> "Every change is measured. Thirty golden tickets with known answers gate the agent. The baseline caught it asking callers pointless questions on clear tickets; one prompt fix took that from 45% to zero with no regressions. And I benchmarked Claude against the trained model for routing: the model won on accuracy, speed and cost, so Claude does the reasoning work instead."

*Proves:* evaluation, choosing the right tool, engineering discipline.

## 2:50 – 3:10 · How it ships
**Screen:** GitHub repo: the green Actions run, then `docs/ai-workflow.md`.
> "Every push runs tests for every component and deploys through GitHub Actions to ECS and CloudFront with keyless OIDC, all defined in Terraform. I built it with Claude Code as my pair programmer; the workflow doc covers how tests and evals kept that speed honest. Thanks for watching."

*Proves:* CI/CD, IaC, AWS, AI-native engineering.

## Recording tips
- Keep the cursor still while the agent streams; the timeline is the interesting part.
- If the agent takes longer than usual, keep talking over it; the stream shows progress.
- Mention the numbers; they are what reviewers remember.
