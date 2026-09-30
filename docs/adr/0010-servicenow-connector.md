# 0010: Sync live tickets with ServiceNow, the system of record

**Status:** Accepted, 2026-09-30

## Context
Live tickets (ADR 0009) made the app a working service desk, but enterprises already run one: ServiceNow. For a copilot to be adoptable it has to work where tickets actually live. It should pick up incidents raised there, add its triage, and keep both sides in step, without either system blocking the other.

## Decision
A connector in the API (`app/services/servicenow.py`, `app/services/sync.py`), talking to the REST Table API with a dedicated integration user. It is off unless `SERVICENOW_*` is configured.

- **Outbound:** a ticket submitted in the app is created as a ServiceNow incident. Caller, location and assignment group become real references, looked up by name and cached. Impact, urgency, category and channel are set, and ServiceNow computes the same priority from its own matrix. `correlation_id` holds the app's number, and the AI triage is written as a work note. Assign, note and resolve in the app are sent as PATCHes, with notes going to the work-notes journal.
- **Inbound:** a background poller (every 60 s, plus **Sync now**) does three things.
  - **Import:** it pulls active incidents raised in ServiceNow within the last 24 hours that aren't linked yet, triages them, and writes back an AI work note (routing confidence, closest precedent). When the model is confident it also sets the assignment group and category, but only where nobody has chosen one: an empty group, the form's default "inquiry" category.
  - **Push:** app tickets that never reached ServiceNow are sent with their current assignment and state.
  - **Changes back:** state and assignment changes made in ServiceNow flow back to the app, where ServiceNow wins. The app's own updates come back as echoes that change nothing, so they are ignored.
- **Resolution codes:** the app uses the classic codes. The connector reads the instance's close-code choices and maps to the label the instance offers ("Solved (Permanently)" becomes "Solution provided" on newer releases).
- **Time windows are relative** (`RELATIVEGT@hour@ago@24`), so the app never compares its clock with the instance's time zone.
- **Failure isolation:** tickets are saved in the app first. ServiceNow errors are logged, counted and shown on the Triage tab, and unlinked tickets are pushed on the next sync.
- **Seed:** `python -m app.servicenow_seed` idempotently creates the assignment groups, sites and demo employees the mapping needs, reusing records that exist.

## Consequences
- Verified against a personal developer instance on 2026-09-30:
  - An app ticket appeared as INC0010001 with correct references and P2 priority.
  - A phone incident raised in ServiceNow (INC0010003) was imported, triaged at 97%, and assigned to Warehouse Systems with a work note.
  - A resolution made in ServiceNow flowed back.
  - A dispatcher's note and resolution in the app appeared in ServiceNow, with the close code mapped to the newer vocabulary.
  - Echoes were ignored.
- Live testing caught two bugs the unit tests hadn't: catch-up pushes used creation-time triage instead of the dispatcher's assignment, and imports left the default category. Both are fixed and now covered by tests.
- Polling is simple and needs no inbound network path from ServiceNow, but it adds up to a minute of latency. The next step is a Business Rule on incident insert in a ServiceNow scoped app (built with the ServiceNow SDK) that calls the copilot directly. The same app could add a Copilot panel to the incident form.
- Work notes added in ServiceNow aren't copied into the app's journal; only state and assignment changes are.
- The integration user needs only `itil`; the seed needs admin rights once, removed afterwards. Verified with `itil` alone: reference lookups, incident reads and writes all work. `itil` can't read the choice table (HTTP 403). The connector therefore learns the resolution-code vocabulary from resolved incidents instead, treating it as all-or-nothing, since a release uses one vocabulary. On a new instance where no incident has a newer label yet, it sends the classic labels. A read ACL on `sys_choice` for the integration user removes that gap.
- **Production:** the instance and user are plain task-definition variables. The password is in Secrets Manager (`incident-copilot/servicenow-password`), created from the local `.env` without being displayed and checked by fingerprint, and the task's execution role can read it. Verified live on 2026-09-30:
  - The production poller imported an email incident raised in ServiceNow (INC0010004) within a minute, categorized it, and queued it for review at 56%.
  - The dispatcher's reassignment on the live site appeared in ServiceNow with its work note.
