# 0009: Conversational intake and live tickets, not a ServiceNow replacement

**Status:** Accepted, 2026-09-30

## Context
Until now every AI feature worked on pasted text or historical tickets: triage produced suggestions but no ticket existed afterwards. A real service desk starts with an employee reporting a problem, gets a ticket with a number, priority, owner and SLA, and works it to resolution. Building a full ITSM tool (forms engine, workflows, notifications, roles, CMDB) was considered and rejected. It is months of work that shows business-software skill rather than AI engineering, and enterprises adopt AI on top of their system of record, not instead of it.

## Decision
Build the thin slice of ITSM the AI story needs:

- **Get help (employee side):** a chat with the virtual agent. Caller and site come from the signed-in persona, standing in for SSO, so they are never asked. Each turn is one structured Claude Opus 5.5 call: a reply, `ready`, and the ticket as understood so far (summary, third-person description, impact, urgency, CI).
  - **Question budget:** the agent asks at most two questions. The server enforces the cap: on the third employee message it tells the model to propose the ticket, and marks it ready regardless.
  - **Attachments:** they go through the attachment reader (ADR 0008). Only the extracted facts join the conversation.
  - **Review before submit:** the employee reviews and edits the ticket; priority follows ServiceNow's impact × urgency matrix.
  - The server keeps no conversation state. The client sends the transcript each turn.
- **`tickets` table:** a writable Delta table in company local time, with the work-note journal in the same format as the extract. The `incident_queue` view unions it with `gold_incident_facts` and computes live SLA fields against the company clock at query time. The queue, ticket pages, summaries and the knowledge loop therefore work on new tickets unchanged.
- **Numbering:** `INC1000001` upward, allocated by an in-process counter seeded from the table. One API task writes tickets.
- **Triage on creation:** the routing model sets the team, and the closest precedent (match ≥ 0.6) sets category and subcategory. At ≥ 85% confidence the ticket is assigned at once; below that it waits in the **review queue** on the Triage tab. The journal records who decided what: virtual agent, routing model, or dispatcher.
- **Dispatcher actions on live tickets:** assign or reassign (in the history's wording, so reassignment counts and timelines work), add a work note (New → In Progress), and resolve with a close code and notes. Resolving makes the ticket eligible for the knowledge check.
- AI output about a ticket is cached per version (journal length and state), so a new note or state gets a fresh summary.

## Consequences
- The loop is complete in one app: report, triage, work, resolve, document. Verified locally against Databricks and Claude on 2026-09-30:
  - The label printer chat took two turns and one question. The virtual agent set P3 and captured the CI. The ticket was auto-assigned to Warehouse Systems at 93% and categorized from a precedent.
  - The "everything is slow" ticket went to the review queue at 71%.
  - About 1¢ per chat turn.
- The paste box on the Triage tab remains as a sandbox for trying arbitrary text.
- Live tickets aren't in the lakehouse pipeline yet, so major-incident and problem detection see only history.
- The next step is a ServiceNow connector that syncs the same record with a developer instance. It turns the app into a copilot on the real system of record without changing any of this.
- Warehouse writes take 1-3 s (more when the serverless warehouse is cold). That is acceptable for a ticket submission; a busier desk would put an OLTP store (for example Lakebase) in front.
