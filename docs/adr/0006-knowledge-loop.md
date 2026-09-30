# 0006: Close the loop from resolved tickets to the knowledge base

**Status:** Accepted, 2026-09-30

## Context
Resolved tickets hold fixes that the knowledge base often lacks: 45% of close notes cite no KB article, and some fixes (a failed motherboard behind a BitLocker prompt) add causes that the closest article doesn't mention. The triage agent retrieves KB articles, so every undocumented fix is a fix it can't suggest. This is ITIL's knowledge step between resolution and review.

## Decision
- **One structured call, not an agent.** `POST /api/incidents/{number}/kb-draft` searches the KB index with the ticket's problem *and* fix, gives Claude the top three articles in full, and gets back one of three actions: `none` (already documented, names the article), `update` (the complete revised article), or `new` (a new article). Claude Opus 5.5 at low effort: about 1-1.5¢ and 3-9 s.
- **Grounding check.** `none` and `update` must name an article Claude was shown, and `update`/`new` must contain article content; otherwise the API returns 502 instead of a plausible-looking draft.
- **A person approves.** The engineer edits the fields and approves or rejects. `POST /api/knowledge/drafts` validates the fields, takes the article's team and category from the ticket on record rather than the request, renders the markdown in the same shape as the source articles, and appends a row to `kb_drafts`. Rejections are kept for measuring draft quality.
- **Merge, don't mutate.** The refresh job builds `kb_docs` from the source articles plus approved new drafts (`KBD-<id prefix>`), overlaying each article's latest approved revision. The source articles stay untouched, and deleting a `kb_drafts` row and refreshing reverts a revision. The merge now rewrites only articles whose text changed, so a sync re-embeds just those.
- `kb_drafts` is the service principal's second writable table (MODIFY on that table only).

## Consequences
- Verified end to end on 2026-09-30: approving the INC0018308 revision of KB0010011, then running `refresh-lakehouse`, made semantic search return the revised article.
- Approved articles reach search only at the next refresh, which is run by hand. That is a second human gate.
- This is a public demo without sign-in, so anyone can approve a draft. Everything they approve goes into text the agent retrieves: that is a prompt-injection path. The mitigations are the rate limits, field validation, the manual refresh, and the agent's instruction to treat retrieved text as data. A real deployment needs authenticated approvers with a knowledge-manager role.
