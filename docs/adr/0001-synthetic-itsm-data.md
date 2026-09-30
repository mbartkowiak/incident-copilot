# 0001: Deterministic, archetype-based synthetic ITSM data

**Status:** Accepted, 2026-09-29

## Context
The app needs realistic incident and knowledge data with free text (for RAG), routing labels (for the classifier), and discoverable patterns (for analytics). Real ServiceNow data can't be published. The public UCI ServiceNow event log has realistic distributions but no free-text fields.

## Decision
Generate data from a hand-curated catalog of ~30 incident archetypes (`tools/datagen/datagen/archetypes.json`) for a fictional logistics company. Each archetype defines its true resolver group, typical misroutes, severity, phrasing variants with slots, resolutions, and a KB article. The generator is stdlib-only and deterministic per `--seed`, and it plants:

- **Patterns:** weekday/hour seasonality, mild growth, month-end ERP load, a 6-week VPN regression, and four outage bursts.
- **Defects:** duplicate rows, missing short descriptions, resolved-before-opened timestamps, and PII in free text, for the silver layer to catch.
- **Ground truth:** true group, initial (mis)route, event membership, and defects, kept separate from the ingest folders so the pipeline never sees labels.

## Consequences
- Evals and demo scenarios can assert against known answers: "what caused the March 10 spike?" has a correct answer.
- Text diversity is lower than real tickets, so classifier scores will be optimistic. An optional LLM paraphrase pass can be added later if the evals need harder data.

## Amendment (2026-09-29): vague tickets
The first routing model scored 100% on the held-out months, because every archetype's wording was unique to its team. Real service desks get "can't log in", "everything is slow" and "printer not working", which several teams could own. The generator now rewrites 15% of eligible tickets with generic wording shared across a *family* of look-alike archetypes (login, slowness, access, printing, email, app-down), and records `is_vague` in the ground truth. Accuracy dropped to a credible 95%, the errors cluster where a human dispatcher would also hesitate, and low model confidence now means something.
- The shape mirrors the ServiceNow Table API, so swapping in a live instance extract means changing only the ingest source.
